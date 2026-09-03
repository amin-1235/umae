"""Volatility features: ATR, volatility expansion, candle range."""

from __future__ import annotations

import numpy as np
import pandas as pd

from umae.config.settings import get_settings
from umae.domain.enums import FeatureGroup
from umae.domain.models import FeatureDefinition
from umae.features.base import FeatureCalculator


class VolatilityFeatures(FeatureCalculator):
    """Volatility-based feature calculator.

    Computes:
    - ATR (Average True Range)
    - ATR percentage (ATR / close)
    - Volatility expansion (recent vs historical volatility)
    - Candle range (high - low)
    - Candle range relative to ATR
    """

    @property
    def group(self) -> FeatureGroup:
        return FeatureGroup.VOLATILITY

    @property
    def definitions(self) -> list[FeatureDefinition]:
        settings = get_settings()
        return [
            FeatureDefinition(
                name="volatility_atr",
                group=FeatureGroup.VOLATILITY,
                description=f"ATR({settings.features.atr_period})",
                parameters={"period": settings.features.atr_period},
                min_candles_required=settings.features.atr_period + 1,
            ),
            FeatureDefinition(
                name="volatility_atr_pct",
                group=FeatureGroup.VOLATILITY,
                description="ATR as percentage of close",
                min_candles_required=settings.features.atr_period + 1,
            ),
            FeatureDefinition(
                name="volatility_expansion",
                group=FeatureGroup.VOLATILITY,
                description="Volatility expansion ratio",
                parameters={"period": settings.features.volatility_period},
                min_candles_required=settings.features.volatility_period + 1,
            ),
            FeatureDefinition(
                name="volatility_candle_range",
                group=FeatureGroup.VOLATILITY,
                description="Candle range (high - low)",
                min_candles_required=2,
            ),
            FeatureDefinition(
                name="volatility_candle_range_atr",
                group=FeatureGroup.VOLATILITY,
                description="Candle range relative to ATR",
                min_candles_required=settings.features.atr_period + 1,
            ),
            FeatureDefinition(
                name="volatility_regime",
                group=FeatureGroup.VOLATILITY,
                description="Volatility regime: 1=high, -1=low, 0=normal",
                min_candles_required=settings.features.volatility_period + 1,
            ),
        ]

    def compute(self, df: pd.DataFrame) -> dict[str, float]:
        settings = get_settings()
        close = df["close"]
        high = df["high"]
        low = df["low"]

        features: dict[str, float] = {}

        # True Range
        tr = _true_range(high, low, close)

        # ATR
        atr_period = settings.features.atr_period
        atr = tr.ewm(alpha=1.0 / atr_period, min_periods=atr_period, adjust=False).mean()
        atr_value = atr.iloc[-1] if not np.isnan(atr.iloc[-1]) else 0.0
        features["volatility_atr"] = atr_value

        # ATR as percentage of close
        close_value = close.iloc[-1]
        features["volatility_atr_pct"] = (
            (atr_value / close_value * 100.0) if close_value > 0 else 0.0
        )

        # Candle range
        candle_range = high.iloc[-1] - low.iloc[-1]
        features["volatility_candle_range"] = candle_range

        # Candle range relative to ATR
        features["volatility_candle_range_atr"] = (
            (candle_range / atr_value) if atr_value > 0 else 0.0
        )

        # Volatility expansion: recent volatility / historical volatility
        vol_period = settings.features.volatility_period
        recent_window = min(vol_period // 5, len(close) - 1) if len(close) > 1 else 10
        recent_window = max(recent_window, 10)  # minimum 10 candles for recent window
        if len(close) > vol_period:
            recent_returns = close.iloc[-recent_window:].pct_change().dropna()
            historical_returns = close.iloc[-vol_period:].pct_change().dropna()

            recent_vol = recent_returns.std() if len(recent_returns) > 1 else 0.0
            hist_vol = historical_returns.std() if len(historical_returns) > 1 else 0.0

            features["volatility_expansion"] = recent_vol / hist_vol if hist_vol > 0 else 1.0
        else:
            features["volatility_expansion"] = 1.0

        # Volatility regime
        if features["volatility_expansion"] > 1.5:
            features["volatility_regime"] = 1.0  # high volatility
        elif features["volatility_expansion"] < 0.5:
            features["volatility_regime"] = -1.0  # low volatility
        else:
            features["volatility_regime"] = 0.0  # normal

        return features


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Calculate True Range.

    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # First candle has no prev_close, use high - low
    tr.iloc[0] = high.iloc[0] - low.iloc[0]

    return tr
