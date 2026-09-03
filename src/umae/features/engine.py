"""Feature engine combining all feature groups."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from umae.domain.enums import FeatureGroup
from umae.domain.models import CandleSet, FeatureDefinition, FeatureSet
from umae.features.base import FeatureCalculator, candleset_to_dataframe
from umae.features.momentum import MomentumFeatures
from umae.features.price_structure import PriceStructureFeatures
from umae.features.trend import TrendFeatures
from umae.features.volatility import VolatilityFeatures
from umae.features.volume import VolumeFeatures

logger = logging.getLogger(__name__)


class FeatureEngine:
    """Main feature engine that orchestrates all feature calculators.

    Combines trend, momentum, volume, volatility, and price structure
    features into a single FeatureSet.
    """

    def __init__(self, groups: list[FeatureGroup] | None = None) -> None:
        """Initialize the feature engine.

        Args:
            groups: Feature groups to compute. If None, computes all groups.
        """
        self._calculators: list[FeatureCalculator] = self._create_calculators(groups)

    @staticmethod
    def _create_calculators(groups: list[FeatureGroup] | None) -> list[FeatureCalculator]:
        """Create feature calculators for specified groups."""
        all_calculators = {
            FeatureGroup.TREND: TrendFeatures(),
            FeatureGroup.MOMENTUM: MomentumFeatures(),
            FeatureGroup.VOLUME: VolumeFeatures(),
            FeatureGroup.VOLATILITY: VolatilityFeatures(),
            FeatureGroup.PRICE_STRUCTURE: PriceStructureFeatures(),
        }

        if groups is None:
            return list(all_calculators.values())

        return [all_calculators[g] for g in groups if g in all_calculators]

    @property
    def enabled_groups(self) -> list[FeatureGroup]:
        """Get list of enabled feature groups."""
        return [c.group for c in self._calculators]

    @property
    def all_definitions(self) -> list[FeatureDefinition]:
        """Get all feature definitions from all calculators."""
        defs: list[FeatureDefinition] = []
        for calc in self._calculators:
            defs.extend(calc.definitions)
        return defs

    @property
    def min_candles_required(self) -> int:
        """Minimum candles needed across all calculators."""
        if not self._calculators:
            return 0
        return max(c.min_candles_required for c in self._calculators)

    def compute(self, candle_set: CandleSet) -> FeatureSet:
        """Compute all features for a CandleSet.

        Args:
            candle_set: CandleSet with OHLCV data

        Returns:
            FeatureSet with all computed features
        """
        if not candle_set.candles:
            return FeatureSet(
                timestamp=candle_set.end or candle_set.start or pd.Timestamp.now().to_pydatetime(),
                symbol=candle_set.symbol,
                timeframe=candle_set.timeframe,
                features={},
            )

        df = candleset_to_dataframe(candle_set)

        if len(df) < self.min_candles_required:
            logger.debug(
                "Insufficient candles for feature engine: need %d, got %d",
                self.min_candles_required,
                len(df),
            )
            return FeatureSet(
                timestamp=candle_set.end or pd.Timestamp.now().to_pydatetime(),
                symbol=candle_set.symbol,
                timeframe=candle_set.timeframe,
                features={},
            )

        all_features: dict[str, float] = {}

        for calculator in self._calculators:
            try:
                features = calculator.compute(df)
                all_features.update(features)
            except Exception:
                logger.exception("Error computing %s features", calculator.group.value)

        return FeatureSet(
            timestamp=candle_set.end or pd.Timestamp.now().to_pydatetime(),
            symbol=candle_set.symbol,
            timeframe=candle_set.timeframe,
            features=all_features,
        )

    def compute_group(
        self,
        candle_set: CandleSet,
        group: FeatureGroup,
    ) -> dict[str, float]:
        """Compute features for a single group only.

        Args:
            candle_set: CandleSet with OHLCV data
            group: Feature group to compute

        Returns:
            Dictionary of feature_name -> value
        """
        if not candle_set.candles:
            return {}

        df = candleset_to_dataframe(candle_set)

        for calculator in self._calculators:
            if calculator.group == group:
                if len(df) < calculator.min_candles_required:
                    return {}
                try:
                    return calculator.compute(df)
                except Exception:
                    logger.exception("Error computing %s features", group.value)
                    return {}

        return {}

    def get_definitions_by_group(self, group: FeatureGroup) -> list[FeatureDefinition]:
        """Get feature definitions for a specific group."""
        for calculator in self._calculators:
            if calculator.group == group:
                return calculator.definitions
        return []

    def summary(self) -> dict[str, Any]:
        """Get a summary of the feature engine configuration."""
        return {
            "enabled_groups": [g.value for g in self.enabled_groups],
            "total_features": len(self.all_definitions),
            "min_candles_required": self.min_candles_required,
            "feature_groups": {
                g.value: len(self.get_definitions_by_group(g)) for g in self.enabled_groups
            },
        }
