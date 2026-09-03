"""Trend features: EMA, SMA, MA slope, market structure (HH/HL/LH/LL)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from umae.config.settings import get_settings
from umae.domain.enums import FeatureGroup
from umae.domain.models import FeatureDefinition
from umae.features.base import FeatureCalculator

if TYPE_CHECKING:
    import pandas as pd


class TrendFeatures(FeatureCalculator):
    """Trend-based feature calculator.

    Computes:
    - EMA fast/slow/trend crossovers
    - SMA long
    - MA slope (rate of change of EMAs)
    - Market structure: Higher Highs, Higher Lows, Lower Highs, Lower Lows
    - Price relative to EMAs
    """

    @property
    def group(self) -> FeatureGroup:
        return FeatureGroup.TREND

    @property
    def definitions(self) -> list[FeatureDefinition]:
        settings = get_settings()
        return [
            FeatureDefinition(
                name="trend_ema_fast",
                group=FeatureGroup.TREND,
                description=f"EMA({settings.features.ema_fast_period})",
                parameters={"period": settings.features.ema_fast_period},
                min_candles_required=settings.features.ema_fast_period + 1,
            ),
            FeatureDefinition(
                name="trend_ema_slow",
                group=FeatureGroup.TREND,
                description=f"EMA({settings.features.ema_slow_period})",
                parameters={"period": settings.features.ema_slow_period},
                min_candles_required=settings.features.ema_slow_period + 1,
            ),
            FeatureDefinition(
                name="trend_ema_trend",
                group=FeatureGroup.TREND,
                description=f"EMA({settings.features.ema_trend_period})",
                parameters={"period": settings.features.ema_trend_period},
                min_candles_required=settings.features.ema_trend_period + 1,
            ),
            FeatureDefinition(
                name="trend_sma_long",
                group=FeatureGroup.TREND,
                description=f"SMA({settings.features.sma_long_period})",
                parameters={"period": settings.features.sma_long_period},
                min_candles_required=settings.features.sma_long_period + 1,
            ),
            FeatureDefinition(
                name="trend_ema_cross_fast_slow",
                group=FeatureGroup.TREND,
                description="EMA fast vs slow crossover signal",
                min_candles_required=settings.features.ema_slow_period + 1,
            ),
            FeatureDefinition(
                name="trend_ema_cross_slow_trend",
                group=FeatureGroup.TREND,
                description="EMA slow vs trend crossover signal",
                min_candles_required=settings.features.ema_trend_period + 1,
            ),
            FeatureDefinition(
                name="trend_slope_ema_fast",
                group=FeatureGroup.TREND,
                description="Slope of EMA fast (rate of change)",
                min_candles_required=settings.features.ema_fast_period + 5,
            ),
            FeatureDefinition(
                name="trend_slope_ema_slow",
                group=FeatureGroup.TREND,
                description="Slope of EMA slow (rate of change)",
                min_candles_required=settings.features.ema_slow_period + 5,
            ),
            FeatureDefinition(
                name="trend_price_vs_ema_trend",
                group=FeatureGroup.TREND,
                description="Close relative to EMA trend",
                min_candles_required=settings.features.ema_trend_period + 1,
            ),
            FeatureDefinition(
                name="trend_price_vs_sma_long",
                group=FeatureGroup.TREND,
                description="Close relative to SMA long",
                min_candles_required=settings.features.sma_long_period + 1,
            ),
            FeatureDefinition(
                name="trend_structure_hh",
                group=FeatureGroup.TREND,
                description="Higher High detected",
                min_candles_required=settings.features.structure_lookback + 2,
            ),
            FeatureDefinition(
                name="trend_structure_hl",
                group=FeatureGroup.TREND,
                description="Higher Low detected",
                min_candles_required=settings.features.structure_lookback + 2,
            ),
            FeatureDefinition(
                name="trend_structure_lh",
                group=FeatureGroup.TREND,
                description="Lower High detected",
                min_candles_required=settings.features.structure_lookback + 2,
            ),
            FeatureDefinition(
                name="trend_structure_ll",
                group=FeatureGroup.TREND,
                description="Lower Low detected",
                min_candles_required=settings.features.structure_lookback + 2,
            ),
            FeatureDefinition(
                name="trend_structure_score",
                group=FeatureGroup.TREND,
                description="Market structure score (-1 to 1)",
                min_candles_required=settings.features.structure_lookback + 2,
            ),
        ]

    def compute(self, df: pd.DataFrame) -> dict[str, float]:
        settings = get_settings()
        close = df["close"]
        high = df["high"]
        low = df["low"]

        features: dict[str, float] = {}

        # EMAs
        ema_fast = close.ewm(span=settings.features.ema_fast_period, adjust=False).mean()
        ema_slow = close.ewm(span=settings.features.ema_slow_period, adjust=False).mean()
        ema_trend = close.ewm(span=settings.features.ema_trend_period, adjust=False).mean()
        sma_long = close.rolling(window=settings.features.sma_long_period).mean()

        # Current values
        features["trend_ema_fast"] = ema_fast.iloc[-1]
        features["trend_ema_slow"] = ema_slow.iloc[-1]
        features["trend_ema_trend"] = ema_trend.iloc[-1]
        features["trend_sma_long"] = sma_long.iloc[-1] if not np.isnan(sma_long.iloc[-1]) else 0.0

        # Crossover signals: 1 = bullish cross, -1 = bearish cross, 0 = no cross
        features["trend_ema_cross_fast_slow"] = _crossover_signal(ema_fast, ema_slow)
        features["trend_ema_cross_slow_trend"] = _crossover_signal(ema_slow, ema_trend)

        # Slopes: rate of change over 5 periods
        features["trend_slope_ema_fast"] = _slope(ema_fast, 5)
        features["trend_slope_ema_slow"] = _slope(ema_slow, 5)

        # Price relative to MAs (normalized distance)
        features["trend_price_vs_ema_trend"] = _relative_distance(
            close.iloc[-1], ema_trend.iloc[-1]
        )
        features["trend_price_vs_sma_long"] = _relative_distance(close.iloc[-1], sma_long.iloc[-1])

        # Market structure (HH/HL/LH/LL)
        lookback = settings.features.structure_lookback
        hh, hl, lh, ll = _detect_structure(high, low, lookback)
        features["trend_structure_hh"] = hh
        features["trend_structure_hl"] = hl
        features["trend_structure_lh"] = lh
        features["trend_structure_ll"] = ll

        # Structure score: +1 bullish, -1 bearish, 0 neutral
        score = 0.0
        if hh and not lh:
            score += 0.5
        if hl and not ll:
            score += 0.5
        if lh and not hh:
            score -= 0.5
        if ll and not hl:
            score -= 0.5
        features["trend_structure_score"] = score

        return features


def _crossover_signal(fast: pd.Series, slow: pd.Series) -> float:
    """Detect crossover between two series using only past data.

    Returns 1.0 if fast just crossed above slow, -1.0 if crossed below, 0.0 otherwise.
    """
    if len(fast) < 2 or len(slow) < 2:
        return 0.0

    curr_diff = fast.iloc[-1] - slow.iloc[-1]
    prev_diff = fast.iloc[-2] - slow.iloc[-2]

    if prev_diff <= 0 and curr_diff > 0:
        return 1.0
    if prev_diff >= 0 and curr_diff < 0:
        return -1.0
    return 0.0


def _slope(series: pd.Series, periods: int) -> float:
    """Calculate slope (rate of change) of a series over N periods."""
    if len(series) < periods + 1:
        return 0.0

    current = series.iloc[-1]
    past = series.iloc[-periods - 1]

    if past == 0.0:
        return 0.0

    return float((current - past) / past * 100.0)


def _relative_distance(price: float, ma_value: float) -> float:
    """Calculate normalized distance of price from moving average."""
    if ma_value == 0.0:
        return 0.0
    return (price - ma_value) / ma_value * 100.0


def _detect_structure(
    high: pd.Series,
    low: pd.Series,
    lookback: int,
) -> tuple[float, float, float, float]:
    """Detect market structure patterns (HH/HL/LH/LL) using only past data.

    Compares the most recent swing points to previous swing points.
    Returns (hh, hl, lh, ll) as 1.0/0.0 flags.
    """
    if len(high) < lookback + 2:
        return 0.0, 0.0, 0.0, 0.0

    # Find local highs and lows using rolling window
    swing_high = high.rolling(window=5, center=True).max()
    swing_low = low.rolling(window=5, center=True).min()

    # Get the most recent two swing highs and two swing lows (from the past)
    recent_sh = swing_high.iloc[-5:].dropna()
    recent_sl = swing_low.iloc[-5:].dropna()
    prev_sh = swing_high.iloc[-lookback:-5].dropna()
    prev_sl = swing_low.iloc[-lookback:-5].dropna()

    if recent_sh.empty or recent_sl.empty or prev_sh.empty or prev_sl.empty:
        return 0.0, 0.0, 0.0, 0.0

    last_high = recent_sh.iloc[-1]
    prev_high = prev_sh.iloc[-1]
    last_low = recent_sl.iloc[-1]
    prev_low = prev_sl.iloc[-1]

    hh = 1.0 if last_high > prev_high else 0.0
    hl = 1.0 if last_low > prev_low else 0.0
    lh = 1.0 if last_high < prev_high else 0.0
    ll = 1.0 if last_low < prev_low else 0.0

    return hh, hl, lh, ll
