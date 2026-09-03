"""Volume features: relative volume, volume expansion."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from umae.config.settings import get_settings
from umae.domain.enums import FeatureGroup
from umae.domain.models import FeatureDefinition
from umae.features.base import FeatureCalculator

if TYPE_CHECKING:
    import pandas as pd


class VolumeFeatures(FeatureCalculator):
    """Volume-based feature calculator.

    Computes:
    - Relative volume (current volume / average volume)
    - Volume MA
    - Volume expansion (recent vs historical volume)
    - Volume trend
    """

    @property
    def group(self) -> FeatureGroup:
        return FeatureGroup.VOLUME

    @property
    def definitions(self) -> list[FeatureDefinition]:
        settings = get_settings()
        return [
            FeatureDefinition(
                name="volume_relative",
                group=FeatureGroup.VOLUME,
                description=f"Relative volume vs MA({settings.features.volume_period})",
                parameters={"period": settings.features.volume_period},
                min_candles_required=settings.features.volume_period + 1,
            ),
            FeatureDefinition(
                name="volume_ma",
                group=FeatureGroup.VOLUME,
                description=f"Volume MA({settings.features.volume_period})",
                parameters={"period": settings.features.volume_period},
                min_candles_required=settings.features.volume_period + 1,
            ),
            FeatureDefinition(
                name="volume_expansion",
                group=FeatureGroup.VOLUME,
                description=f"Volume expansion ratio over {settings.features.volume_expansion_period} periods",
                parameters={"period": settings.features.volume_expansion_period},
                min_candles_required=settings.features.volume_expansion_period + 1,
            ),
            FeatureDefinition(
                name="volume_trend",
                group=FeatureGroup.VOLUME,
                description="Volume trend: 1=increasing, -1=decreasing, 0=flat",
                min_candles_required=settings.features.volume_period + 3,
            ),
            FeatureDefinition(
                name="volume_spike",
                group=FeatureGroup.VOLUME,
                description="Volume spike: 1 if volume > 2x average",
                min_candles_required=settings.features.volume_period + 1,
            ),
        ]

    def compute(self, df: pd.DataFrame) -> dict[str, float]:
        settings = get_settings()
        volume = df["volume"]

        features: dict[str, float] = {}

        # Volume MA
        vol_ma = volume.rolling(window=settings.features.volume_period).mean()
        vol_ma_value = vol_ma.iloc[-1] if not np.isnan(vol_ma.iloc[-1]) else 1.0
        features["volume_ma"] = vol_ma_value

        # Relative volume
        features["volume_relative"] = volume.iloc[-1] / vol_ma_value if vol_ma_value > 0 else 0.0

        # Volume expansion: recent volume avg / historical volume avg
        exp_period = settings.features.volume_expansion_period
        if len(volume) > exp_period + 1:
            recent_avg = volume.iloc[-exp_period:].mean()
            historical_avg = volume.iloc[-settings.features.volume_period : -exp_period].mean()
            features["volume_expansion"] = (
                recent_avg / historical_avg if historical_avg > 0 else 1.0
            )
        else:
            features["volume_expansion"] = 1.0

        # Volume trend: slope over last 5 periods
        features["volume_trend"] = _volume_trend(volume)

        # Volume spike detection
        features["volume_spike"] = 1.0 if features["volume_relative"] > 2.0 else 0.0

        return features


def _volume_trend(volume: pd.Series) -> float:
    """Determine volume trend direction.

    Returns 1.0 if volume is increasing, -1.0 if decreasing, 0.0 if flat.
    """
    if len(volume) < 6:
        return 0.0

    recent = volume.iloc[-3:].mean()
    previous = volume.iloc[-6:-3].mean()

    if previous == 0.0:
        return 0.0

    change_pct = (recent - previous) / previous

    if change_pct > 0.1:
        return 1.0
    if change_pct < -0.1:
        return -1.0
    return 0.0
