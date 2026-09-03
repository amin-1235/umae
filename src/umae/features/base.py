"""Base feature calculator for UMAE feature engine."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pandas as pd

from umae.domain.models import CandleSet, FeatureDefinition, FeatureSet

if TYPE_CHECKING:
    from umae.domain.enums import FeatureGroup

logger = logging.getLogger(__name__)


class FeatureCalculator(ABC):
    """Abstract base class for all feature calculators.

    Each calculator operates on a pandas DataFrame of OHLCV data
    and returns a dict of feature_name -> value for the latest candle.
    All features use ONLY past data (no lookahead).
    """

    @property
    @abstractmethod
    def group(self) -> FeatureGroup:
        """Feature group this calculator belongs to."""

    @property
    @abstractmethod
    def definitions(self) -> list[FeatureDefinition]:
        """List of features this calculator produces."""

    @property
    def min_candles_required(self) -> int:
        """Minimum number of candles needed to compute features."""
        return max(d.min_candles_required for d in self.definitions)

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> dict[str, float]:
        """Compute features from an OHLCV DataFrame.

        Args:
            df: DataFrame with columns [timestamp, open, high, low, close, volume].
                Sorted ascending by timestamp. Uses only past data.

        Returns:
            Dictionary of feature_name -> value for the latest candle.
            Returns empty dict if insufficient data.
        """

    def compute_for_candleset(self, candle_set: CandleSet) -> FeatureSet:
        """Compute features for a CandleSet.

        Args:
            candle_set: CandleSet with OHLCV data

        Returns:
            FeatureSet with computed features, or empty if insufficient data
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
                "Insufficient candles for %s: need %d, got %d",
                self.group.value,
                self.min_candles_required,
                len(df),
            )
            return FeatureSet(
                timestamp=candle_set.end or pd.Timestamp.now().to_pydatetime(),
                symbol=candle_set.symbol,
                timeframe=candle_set.timeframe,
                features={},
            )

        features = self.compute(df)

        return FeatureSet(
            timestamp=candle_set.end or pd.Timestamp.now().to_pydatetime(),
            symbol=candle_set.symbol,
            timeframe=candle_set.timeframe,
            features=features,
        )


def candleset_to_dataframe(candle_set: CandleSet) -> pd.DataFrame:
    """Convert a CandleSet to a pandas DataFrame.

    Args:
        candle_set: CandleSet to convert

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume]
    """
    if not candle_set.candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    records = [
        {
            "timestamp": c.timestamp,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume),
        }
        for c in candle_set.candles
    ]

    df = pd.DataFrame(records)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df
