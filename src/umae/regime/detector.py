"""Market regime detector using ADX-like logic, ATR percentile, and price structure."""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from umae.domain.enums import MarketRegime
from umae.domain.models import CandleSet, RegimeResult
from umae.features.base import candleset_to_dataframe

logger = logging.getLogger(__name__)

_MIN_CANDLES = 30


class MarketRegimeDetector:
    """Classifies market regime using trend strength, volatility, and price structure.

    Regimes: trending_up, trending_down, ranging, high_volatility,
    low_volatility, breakout, uncertain.
    """

    def __init__(
        self,
        adx_period: int = 14,
        atr_period: int = 14,
        atr_percentile_window: int = 100,
        breakout_atr_mult: float = 2.0,
        trend_adx_threshold: float = 25.0,
        vol_high_percentile: float = 80.0,
        vol_low_percentile: float = 20.0,
    ) -> None:
        self._adx_period = adx_period
        self._atr_period = atr_period
        self._atr_percentile_window = atr_percentile_window
        self._breakout_atr_mult = breakout_atr_mult
        self._trend_adx_threshold = trend_adx_threshold
        self._vol_high_percentile = vol_high_percentile
        self._vol_low_percentile = vol_low_percentile

    @property
    def min_candles_required(self) -> int:
        return _MIN_CANDLES

    def detect(self, candle_set: CandleSet) -> RegimeResult:
        """Detect market regime for a CandleSet.

        Args:
            candle_set: CandleSet with OHLCV data.

        Returns:
            RegimeResult with classified regime, confidence, and indicators.
        """
        if not candle_set.candles:
            return self._uncertain_result(candle_set)

        df = candleset_to_dataframe(candle_set)

        if len(df) < self.min_candles_required:
            return self._uncertain_result(candle_set)

        indicators = self._compute_indicators(df)
        regime, confidence = self._classify(indicators)

        return RegimeResult(
            timestamp=candle_set.end or datetime.utcnow(),
            symbol=candle_set.symbol,
            timeframe=candle_set.timeframe,
            regime=regime,
            confidence=confidence,
            indicators=indicators,
        )

    def _uncertain_result(self, candle_set: CandleSet) -> RegimeResult:
        return RegimeResult(
            timestamp=candle_set.end or datetime.utcnow(),
            symbol=candle_set.symbol,
            timeframe=candle_set.timeframe,
            regime=MarketRegime.UNCERTAIN,
            confidence=0.0,
        )

    def _compute_indicators(self, df: pd.DataFrame) -> dict[str, float]:
        close = df["close"]
        high = df["high"]
        low = df["low"]

        tr = self._true_range(high, low, close)

        adx_value, di_plus, di_minus = self._adx(high, low, close, tr)
        atr_value = self._atr(tr)
        atr_pct = (atr_value / close.iloc[-1] * 100.0) if close.iloc[-1] > 0 else 0.0
        atr_percentile = self._atr_percentile(tr, atr_value)
        expansion = self._volatility_expansion(close)
        structure = self._price_structure(high, low)

        return {
            "adx": adx_value,
            "di_plus": di_plus,
            "di_minus": di_minus,
            "atr": atr_value,
            "atr_pct": atr_pct,
            "atr_percentile": atr_percentile,
            "volatility_expansion": expansion,
            "structure_hh": structure["hh"],
            "structure_hl": structure["hl"],
            "structure_lh": structure["lh"],
            "structure_ll": structure["ll"],
            "structure_score": structure["score"],
        }

    def _classify(self, ind: dict[str, float]) -> tuple[MarketRegime, float]:
        adx = ind["adx"]
        di_plus = ind["di_plus"]
        di_minus = ind["di_minus"]
        atr_pctile = ind["atr_percentile"]
        expansion = ind["volatility_expansion"]
        struct_score = ind["structure_score"]

        # Breakout: high volatility expansion + strong directional move
        if expansion > 2.0 and adx > 20.0:
            conf = min(1.0, (expansion - 2.0) * 0.5 + (adx - 20.0) / 30.0)
            return MarketRegime.BREAKOUT, conf

        # High volatility: ATR percentile above threshold, no clear trend
        if atr_pctile >= self._vol_high_percentile and adx < self._trend_adx_threshold:
            conf = min(1.0, (atr_pctile - self._vol_high_percentile) / 20.0 + 0.3)
            return MarketRegime.HIGH_VOLATILITY, conf

        # Low volatility: ATR percentile below threshold, no clear trend
        if atr_pctile <= self._vol_low_percentile and adx < self._trend_adx_threshold:
            conf = min(1.0, (self._vol_low_percentile - atr_pctile) / 20.0 + 0.3)
            return MarketRegime.LOW_VOLATILITY, conf

        # Trending up: strong ADX + DI+ > DI- + bullish structure
        if adx >= self._trend_adx_threshold and di_plus > di_minus:
            base_conf = min(1.0, (adx - self._trend_adx_threshold) / 25.0 + 0.3)
            if struct_score > 0:
                base_conf = min(1.0, base_conf + 0.15)
            return MarketRegime.TRENDING_UP, base_conf

        # Trending down: strong ADX + DI- > DI+ + bearish structure
        if adx >= self._trend_adx_threshold and di_minus > di_plus:
            base_conf = min(1.0, (adx - self._trend_adx_threshold) / 25.0 + 0.3)
            if struct_score < 0:
                base_conf = min(1.0, base_conf + 0.15)
            return MarketRegime.TRENDING_DOWN, base_conf

        # Ranging: weak ADX, normal volatility
        if adx < self._trend_adx_threshold:
            conf = min(1.0, (self._trend_adx_threshold - adx) / 15.0 + 0.3)
            return MarketRegime.RANGING, conf

        return MarketRegime.UNCERTAIN, 0.2

    def _true_range(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        tr.iloc[0] = high.iloc[0] - low.iloc[0]
        return tr

    def _atr(self, tr: pd.Series) -> float:
        atr = tr.ewm(
            alpha=1.0 / self._atr_period, min_periods=self._atr_period, adjust=False
        ).mean()
        return float(atr.iloc[-1])

    def _adx(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        tr: pd.Series,
    ) -> tuple[float, float, float]:
        """Compute ADX, +DI, -DI using Wilder's smoothing."""
        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = pd.Series(
            np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
        )
        minus_dm = pd.Series(
            np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
        )

        alpha = 1.0 / self._adx_period
        atr_smooth = tr.ewm(alpha=alpha, min_periods=self._adx_period, adjust=False).mean()
        plus_dm_smooth = plus_dm.ewm(alpha=alpha, min_periods=self._adx_period, adjust=False).mean()
        minus_dm_smooth = minus_dm.ewm(
            alpha=alpha, min_periods=self._adx_period, adjust=False
        ).mean()

        di_plus = (plus_dm_smooth / atr_smooth * 100.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        di_minus = (
            (minus_dm_smooth / atr_smooth * 100.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        )

        dx = ((di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan) * 100.0).fillna(
            0.0
        )
        adx = dx.ewm(alpha=alpha, min_periods=self._adx_period, adjust=False).mean()

        return adx.iloc[-1], di_plus.iloc[-1], di_minus.iloc[-1]

    def _atr_percentile(self, tr: pd.Series, current_atr: float) -> float:
        window = min(self._atr_percentile_window, len(tr))
        if window < 10:
            return 50.0
        recent = tr.iloc[-window:]
        count_below = (recent < current_atr).sum()
        return float(count_below / window * 100.0)

    def _volatility_expansion(self, close: pd.Series) -> float:
        if len(close) < 30:
            return 1.0
        recent = close.iloc[-10:].pct_change().dropna()
        historical = close.iloc[-30:].pct_change().dropna()
        recent_vol = recent.std() if len(recent) > 1 else 0.0
        hist_vol = historical.std() if len(historical) > 1 else 0.0
        return recent_vol / hist_vol if hist_vol > 0 else 1.0

    def _price_structure(self, high: pd.Series, low: pd.Series) -> dict[str, float]:
        lookback = 20
        if len(high) < lookback + 2:
            return {"hh": 0.0, "hl": 0.0, "lh": 0.0, "ll": 0.0, "score": 0.0}

        swing_high = high.rolling(window=5, center=True).max()
        swing_low = low.rolling(window=5, center=True).min()

        recent_sh = swing_high.iloc[-5:].dropna()
        recent_sl = swing_low.iloc[-5:].dropna()
        prev_sh = swing_high.iloc[-lookback:-5].dropna()
        prev_sl = swing_low.iloc[-lookback:-5].dropna()

        if recent_sh.empty or recent_sl.empty or prev_sh.empty or prev_sl.empty:
            return {"hh": 0.0, "hl": 0.0, "lh": 0.0, "ll": 0.0, "score": 0.0}

        last_high = recent_sh.iloc[-1]
        prev_high = prev_sh.iloc[-1]
        last_low = recent_sl.iloc[-1]
        prev_low = prev_sl.iloc[-1]

        hh = 1.0 if last_high > prev_high else 0.0
        hl = 1.0 if last_low > prev_low else 0.0
        lh = 1.0 if last_high < prev_high else 0.0
        ll = 1.0 if last_low < prev_low else 0.0

        score = 0.0
        if hh and not lh:
            score += 0.5
        if hl and not ll:
            score += 0.5
        if lh and not hh:
            score -= 0.5
        if ll and not hl:
            score -= 0.5

        return {"hh": hh, "hl": hl, "lh": lh, "ll": ll, "score": score}
