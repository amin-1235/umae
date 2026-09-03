"""Price structure features: breakout, consolidation, support/resistance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from umae.config.settings import get_settings
from umae.domain.enums import FeatureGroup
from umae.domain.models import FeatureDefinition
from umae.features.base import FeatureCalculator

if TYPE_CHECKING:
    import pandas as pd


class PriceStructureFeatures(FeatureCalculator):
    """Price structure feature calculator.

    Computes:
    - Breakout detection (up/down)
    - Consolidation detection
    - Support/resistance levels
    - Price position relative to S/R
    - Range compression
    """

    @property
    def group(self) -> FeatureGroup:
        return FeatureGroup.PRICE_STRUCTURE

    @property
    def definitions(self) -> list[FeatureDefinition]:
        settings = get_settings()
        return [
            FeatureDefinition(
                name="structure_breakout_up",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Bullish breakout detected",
                min_candles_required=settings.features.sr_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_breakout_down",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Bearish breakout detected",
                min_candles_required=settings.features.sr_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_consolidation",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Consolidation pattern detected",
                min_candles_required=settings.features.structure_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_range_pct",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Current range as % of lookback range",
                min_candles_required=settings.features.structure_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_price_near_support",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Price near support level",
                min_candles_required=settings.features.sr_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_price_near_resistance",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Price near resistance level",
                min_candles_required=settings.features.sr_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_support_level",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Nearest support level",
                min_candles_required=settings.features.sr_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_resistance_level",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Nearest resistance level",
                min_candles_required=settings.features.sr_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_distance_to_support",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Distance to support as % of price",
                min_candles_required=settings.features.sr_lookback + 1,
            ),
            FeatureDefinition(
                name="structure_distance_to_resistance",
                group=FeatureGroup.PRICE_STRUCTURE,
                description="Distance to resistance as % of price",
                min_candles_required=settings.features.sr_lookback + 1,
            ),
        ]

    def compute(self, df: pd.DataFrame) -> dict[str, float]:
        settings = get_settings()
        close = df["close"]
        high = df["high"]
        low = df["low"]

        features: dict[str, float] = {}
        current_price = close.iloc[-1]

        # Support and Resistance levels
        sr_lookback = settings.features.sr_lookback
        support, resistance = _find_sr_levels(high, low, close, sr_lookback)

        features["structure_support_level"] = support
        features["structure_resistance_level"] = resistance

        # Distance to S/R
        features["structure_distance_to_support"] = (
            (current_price - support) / current_price * 100.0 if current_price > 0 else 0.0
        )
        features["structure_distance_to_resistance"] = (
            (resistance - current_price) / current_price * 100.0 if current_price > 0 else 0.0
        )

        # Near S/R detection (within 1.5%)
        features["structure_price_near_support"] = (
            1.0 if abs(current_price - support) / current_price * 100.0 < 1.5 else 0.0
        )
        features["structure_price_near_resistance"] = (
            1.0 if abs(resistance - current_price) / current_price * 100.0 < 1.5 else 0.0
        )

        # Breakout detection
        structure_lookback = settings.features.structure_lookback
        features["structure_breakout_up"] = _detect_breakout(close, high, structure_lookback, "up")
        features["structure_breakout_down"] = _detect_breakout(
            close, low, structure_lookback, "down"
        )

        # Consolidation detection
        features["structure_consolidation"] = _detect_consolidation(high, low, structure_lookback)

        # Range percentage
        features["structure_range_pct"] = _range_pct(high, low, structure_lookback)

        return features


def _find_sr_levels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int,
) -> tuple[float, float]:
    """Find nearest support and resistance levels.

    Uses pivot points from recent swing highs and lows.
    """
    if len(close) < lookback + 1:
        return float(close.iloc[-1] * 0.98), float(close.iloc[-1] * 1.02)

    recent_high = high.iloc[-lookback:]
    recent_low = low.iloc[-lookback:]
    current = close.iloc[-1]

    # Find resistance: lowest swing high above current price
    swing_highs = _find_pivot_highs(recent_high, recent_low)
    above = [h for h in swing_highs if h > current]
    resistance = min(above) if above else recent_high.max()

    # Find support: highest swing low below current price
    swing_lows = _find_pivot_lows(recent_high, recent_low)
    below = [sl for sl in swing_lows if sl < current]
    support = max(below) if below else recent_low.min()

    return support, resistance


def _find_pivot_highs(high: pd.Series, low: pd.Series, window: int = 5) -> list[float]:
    """Find pivot high values."""
    pivots: list[float] = []
    highs_arr = high.values
    for i in range(window, len(highs_arr) - window):
        if highs_arr[i] == max(highs_arr[i - window : i + window + 1]):
            pivots.append(float(highs_arr[i]))
    return pivots


def _find_pivot_lows(high: pd.Series, low: pd.Series, window: int = 5) -> list[float]:
    """Find pivot low values."""
    pivots: list[float] = []
    lows_arr = low.values
    for i in range(window, len(lows_arr) - window):
        if lows_arr[i] == min(lows_arr[i - window : i + window + 1]):
            pivots.append(float(lows_arr[i]))
    return pivots


def _detect_breakout(
    close: pd.Series,
    level_series: pd.Series,
    lookback: int,
    direction: str,
) -> float:
    """Detect breakout above/below recent range.

    Returns 1.0 if breakout detected, 0.0 otherwise.
    """
    if len(close) < lookback + 1:
        return 0.0

    # Get previous range
    if direction == "up":
        prev_range = level_series.iloc[-lookback - 1 : -1]
        range_level = prev_range.max()
        return 1.0 if close.iloc[-1] > range_level and close.iloc[-2] <= range_level else 0.0
    else:
        prev_range = level_series.iloc[-lookback - 1 : -1]
        range_level = prev_range.min()
        return 1.0 if close.iloc[-1] < range_level and close.iloc[-2] >= range_level else 0.0


def _detect_consolidation(high: pd.Series, low: pd.Series, lookback: int) -> float:
    """Detect consolidation pattern.

    Returns 1.0 if price is consolidating, 0.0 otherwise.
    Consolidation: range is narrowing and price is within a tight band.
    """
    if len(high) < lookback + 1:
        return 0.0

    recent_range = high.iloc[-lookback:] - low.iloc[-lookback:]
    avg_range = recent_range.mean()

    if avg_range == 0:
        return 0.0

    # Check if current range is significantly smaller than average
    current_range = high.iloc[-1] - low.iloc[-1]
    range_ratio = current_range / avg_range

    # Also check if price has been moving sideways (low directional movement)
    mid = (high + low) / 2.0
    price_change = abs(mid.iloc[-1] - mid.iloc[-lookback]) / avg_range

    if range_ratio < 0.8 and price_change < 1.5:
        return 1.0
    return 0.0


def _range_pct(high: pd.Series, low: pd.Series, lookback: int) -> float:
    """Calculate current range as percentage of lookback range."""
    if len(high) < lookback + 1:
        return 0.0

    lookback_high = high.iloc[-lookback:].max()
    lookback_low = low.iloc[-lookback:].min()
    lookback_range = lookback_high - lookback_low

    if lookback_range == 0:
        return 0.0

    current_range = high.iloc[-1] - low.iloc[-1]
    return float(current_range / lookback_range * 100.0)
