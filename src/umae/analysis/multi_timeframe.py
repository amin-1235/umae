"""Multi-timeframe analysis combining HTF, MTF, and LTF signals."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

import numpy as np
import pandas as pd  # noqa: TC002 — used at runtime for DataFrame operations

from umae.domain.enums import AssetType, MarketRegime, SignalType, Timeframe
from umae.domain.models import (
    CandleSet,
    CompositeSignal,
    FeatureSet,
    SignalScore,
    TimeframeSignal,
)
from umae.features.base import candleset_to_dataframe
from umae.regime.detector import MarketRegimeDetector

logger = logging.getLogger(__name__)

_HTF_TIMEFRAMES = {Timeframe.H4, Timeframe.H6, Timeframe.H12, Timeframe.D1, Timeframe.W1}
_MTF_TIMEFRAMES = {Timeframe.M15, Timeframe.M20, Timeframe.M30, Timeframe.H1, Timeframe.H2}
_LTF_TIMEFRAMES = {Timeframe.M1, Timeframe.M3, Timeframe.M5}

_DEFAULT_MIN_CONFLUENCE = 2


class MultiTimeframeAnalyzer:
    """Combines signals across timeframes into a composite signal.

    HTF (4h, 6h, 12h, 1D, 1W) = context
    MTF (15m, 20m, 30m, 1h, 2h) = bias
    LTF (1m, 3m, 5m) = timing
    """

    def __init__(
        self,
        min_confluence: int = _DEFAULT_MIN_CONFLUENCE,
        regime_detector: MarketRegimeDetector | None = None,
    ) -> None:
        self._min_confluence = min_confluence
        self._regime_detector = regime_detector or MarketRegimeDetector()

    def analyze(
        self,
        symbol: str,
        asset_type: AssetType,
        exchange: str,
        price: float,
        candle_sets: dict[Timeframe, CandleSet],
        feature_sets: dict[Timeframe, FeatureSet] | None = None,
    ) -> CompositeSignal:
        """Analyze multiple timeframes and produce a composite signal.

        Args:
            symbol: Asset symbol.
            asset_type: Type of asset.
            exchange: Exchange name.
            price: Current price.
            candle_sets: Mapping of timeframe to CandleSet.
            feature_sets: Optional pre-computed FeatureSets per timeframe.

        Returns:
            CompositeSignal combining all timeframe analyses.
        """
        now = datetime.utcnow()
        feature_sets = feature_sets or {}

        timeframe_signals: dict[Timeframe, TimeframeSignal] = {}
        for tf, candle_set in sorted(candle_sets.items(), key=lambda x: x[0].minutes):
            ts_signal = self._analyze_timeframe(tf, candle_set, feature_sets.get(tf))
            if ts_signal is not None:
                timeframe_signals[tf] = ts_signal

        composite = self._compose(
            symbol=symbol,
            asset_type=asset_type,
            exchange=exchange,
            price=Decimal(str(price)),
            timeframe_signals=timeframe_signals,
            now=now,
        )

        return composite

    def _analyze_timeframe(
        self,
        tf: Timeframe,
        candle_set: CandleSet,
        feature_set: FeatureSet | None,
    ) -> TimeframeSignal | None:
        if not candle_set.candles:
            return None

        df = candleset_to_dataframe(candle_set)
        if len(df) < 20:
            return None

        features = feature_set.features if feature_set else {}
        regime = self._regime_detector.detect(candle_set)

        signal_type, score, reason_codes = self._score_timeframe(df, features, tf)

        return TimeframeSignal(
            timestamp=candle_set.end or datetime.utcnow(),
            symbol=candle_set.symbol,
            timeframe=tf,
            signal=signal_type,
            score=SignalScore(raw_score=score),
            features_used=features,
            regime=regime,
            reason_codes=reason_codes,
        )

    def _score_timeframe(
        self,
        df: pd.DataFrame,
        features: dict[str, float],
        tf: Timeframe,
    ) -> tuple[SignalType, float, list[str]]:
        from umae.config.settings import get_settings

        settings = get_settings()
        close = df["close"]

        reasons: list[str] = []
        score = 0.0

        # Trend score from EMAs - use settings for consistency with FeatureEngine
        ema_fast = close.ewm(span=settings.features.ema_fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=settings.features.ema_slow_period, adjust=False).mean()
        ema_trend = close.ewm(span=settings.features.ema_trend_period, adjust=False).mean()

        if ema_fast.iloc[-1] > ema_slow.iloc[-1] > ema_trend.iloc[-1]:
            score += 0.3
            reasons.append("ema_bullish_alignment")
        elif ema_fast.iloc[-1] < ema_slow.iloc[-1] < ema_trend.iloc[-1]:
            score -= 0.3
            reasons.append("ema_bearish_alignment")

        # Price vs trend EMA
        price_vs_trend = features.get("trend_price_vs_ema_trend", 0.0)
        if price_vs_trend > 0:
            score += 0.1
            reasons.append("price_above_ema_trend")
        elif price_vs_trend < 0:
            score -= 0.1
            reasons.append("price_below_ema_trend")

        # RSI
        rsi = features.get("momentum_rsi", 50.0)
        if rsi > 70:
            score -= 0.15
            reasons.append("rsi_overbought")
        elif rsi < 30:
            score += 0.15
            reasons.append("rsi_oversold")

        # MACD
        macd_hist = features.get("momentum_macd_histogram", 0.0)
        if macd_hist > 0:
            score += 0.1
            reasons.append("macd_bullish")
        elif macd_hist < 0:
            score -= 0.1
            reasons.append("macd_bearish")

        # Structure score
        struct_score = features.get("trend_structure_score", 0.0)
        score += struct_score * 0.2
        if struct_score > 0:
            reasons.append("bullish_structure")
        elif struct_score < 0:
            reasons.append("bearish_structure")

        # Volume confirmation
        vol_spike = features.get("volume_spike", 0.0)
        if vol_spike > 0:
            score *= 1.2
            reasons.append("volume_spike")

        # ATR-based volatility context
        atr_pct = features.get("volatility_atr_pct", 0.0)
        if atr_pct > 3.0:
            score *= 0.8
            reasons.append("high_atr_caution")

        # Determine signal type
        signal_type = SignalType.NEUTRAL
        if score > 0.15:
            signal_type = SignalType.UP
        elif score < -0.15:
            signal_type = SignalType.DOWN

        return signal_type, np.clip(score, -1.0, 1.0), reasons

    def _compose(
        self,
        symbol: str,
        asset_type: AssetType,
        exchange: str,
        price: Decimal,
        timeframe_signals: dict[Timeframe, TimeframeSignal],
        now: datetime,
    ) -> CompositeSignal:
        if not timeframe_signals:
            return CompositeSignal(
                timestamp=now,
                symbol=symbol,
                asset_type=asset_type,
                exchange=exchange,
                price=Decimal(str(price)),
                signal=SignalType.NO_SIGNAL,
                score=SignalScore(raw_score=0.0),
                regime=MarketRegime.UNCERTAIN,
                reason_codes=["no_timeframe_data"],
            )

        htf_signals = {tf: s for tf, s in timeframe_signals.items() if tf in _HTF_TIMEFRAMES}
        mtf_signals = {tf: s for tf, s in timeframe_signals.items() if tf in _MTF_TIMEFRAMES}
        ltf_signals = {tf: s for tf, s in timeframe_signals.items() if tf in _LTF_TIMEFRAMES}

        # HTF context: strongest timeframe gets most weight
        htf_direction = self._aggregate_direction(
            htf_signals,
            weights={
                Timeframe.W1: 3.0,
                Timeframe.D1: 2.5,
                Timeframe.H12: 2.0,
                Timeframe.H6: 1.5,
                Timeframe.H4: 1.0,
            },
        )
        mtf_direction = self._aggregate_direction(
            mtf_signals,
            weights={
                Timeframe.H2: 1.5,
                Timeframe.H1: 1.2,
                Timeframe.M30: 1.0,
                Timeframe.M20: 0.8,
                Timeframe.M15: 0.6,
            },
        )
        ltf_direction = self._aggregate_direction(
            ltf_signals, weights={Timeframe.M5: 1.0, Timeframe.M3: 0.8, Timeframe.M1: 0.5}
        )

        # Confluence check
        directions = [d for d in [htf_direction, mtf_direction, ltf_direction] if d is not None]
        if len(directions) < self._min_confluence:
            return CompositeSignal(
                timestamp=now,
                symbol=symbol,
                asset_type=asset_type,
                exchange=exchange,
                price=Decimal(str(price)),
                signal=SignalType.NO_SIGNAL,
                score=SignalScore(raw_score=0.0),
                timeframe_signals=timeframe_signals,
                regime=self._dominant_regime(timeframe_signals),
                reason_codes=["insufficient_confluence"],
            )

        # Weighted composite score
        htf_weight = 3.0
        mtf_weight = 2.0
        ltf_weight = 1.0

        htf_score = self._weighted_score(htf_signals, htf_weight)
        mtf_score = self._weighted_score(mtf_signals, mtf_weight)
        ltf_score = self._weighted_score(ltf_signals, ltf_weight)

        total_weight = htf_weight + mtf_weight + ltf_weight
        composite_score = (htf_score + mtf_score + ltf_score) / total_weight

        # Determine signal
        if composite_score > 0.15:
            signal_type = SignalType.UP
        elif composite_score < -0.15:
            signal_type = SignalType.DOWN
        else:
            signal_type = SignalType.NEUTRAL

        # Reason codes from dominant timeframes
        all_reasons: list[str] = []
        for tf in sorted(timeframe_signals.keys(), key=lambda x: x.minutes, reverse=True):
            all_reasons.extend(f"{tf.value}:{r}" for r in timeframe_signals[tf].reason_codes[:2])

        return CompositeSignal(
            timestamp=now,
            symbol=symbol,
            asset_type=asset_type,
            exchange=exchange,
            price=Decimal(str(price)),
            signal=signal_type,
            score=SignalScore(raw_score=round(composite_score, 4)),
            timeframe_signals=timeframe_signals,
            regime=self._dominant_regime(timeframe_signals),
            reason_codes=all_reasons[:10],
            contributing_factors={
                "htf_score": round(htf_score, 4),
                "mtf_score": round(mtf_score, 4),
                "ltf_score": round(ltf_score, 4),
                "htf_direction": htf_direction,
                "mtf_direction": mtf_direction,
                "ltf_direction": ltf_direction,
            },
        )

    def _aggregate_direction(
        self,
        signals: dict[Timeframe, TimeframeSignal],
        weights: dict[Timeframe, float],
    ) -> str | None:
        if not signals:
            return None

        score = 0.0
        total_weight = 0.0
        for tf, sig in signals.items():
            w = weights.get(tf, 1.0)
            score += sig.score.raw_score * w
            total_weight += w

        if total_weight == 0:
            return None

        avg = score / total_weight
        if avg > 0.1:
            return "bullish"
        if avg < -0.1:
            return "bearish"
        return None

    def _weighted_score(
        self,
        signals: dict[Timeframe, TimeframeSignal],
        base_weight: float,
    ) -> float:
        if not signals:
            return 0.0

        total = 0.0
        count = 0
        for sig in signals.values():
            total += sig.score.raw_score * base_weight
            count += 1

        return total / count if count > 0 else 0.0

    def _dominant_regime(self, signals: dict[Timeframe, TimeframeSignal]) -> MarketRegime:
        regime_counts: dict[MarketRegime, float] = {}
        for tf, sig in signals.items():
            if sig.regime is None:
                continue
            w = tf.minutes
            regime_counts[sig.regime.regime] = regime_counts.get(sig.regime.regime, 0.0) + w

        if not regime_counts:
            return MarketRegime.UNCERTAIN

        return max(regime_counts, key=lambda k: regime_counts[k])
