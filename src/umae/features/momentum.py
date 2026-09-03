"""Momentum features: RSI, MACD, ROC."""

from __future__ import annotations

from typing import TYPE_CHECKING

from umae.config.settings import get_settings
from umae.domain.enums import FeatureGroup
from umae.domain.models import FeatureDefinition
from umae.features.base import FeatureCalculator

if TYPE_CHECKING:
    import pandas as pd


class MomentumFeatures(FeatureCalculator):
    """Momentum-based feature calculator.

    Computes:
    - RSI with overbought/oversold zones
    - MACD line, signal, histogram
    - ROC (Rate of Change)
    """

    @property
    def group(self) -> FeatureGroup:
        return FeatureGroup.MOMENTUM

    @property
    def definitions(self) -> list[FeatureDefinition]:
        settings = get_settings()
        return [
            FeatureDefinition(
                name="momentum_rsi",
                group=FeatureGroup.MOMENTUM,
                description=f"RSI({settings.features.rsi_period})",
                parameters={"period": settings.features.rsi_period},
                min_candles_required=settings.features.rsi_period + 1,
            ),
            FeatureDefinition(
                name="momentum_rsi_zone",
                group=FeatureGroup.MOMENTUM,
                description="RSI zone: 1=overbought, -1=oversold, 0=neutral",
                min_candles_required=settings.features.rsi_period + 1,
            ),
            FeatureDefinition(
                name="momentum_macd_line",
                group=FeatureGroup.MOMENTUM,
                description="MACD line",
                parameters={
                    "fast": settings.features.macd_fast,
                    "slow": settings.features.macd_slow,
                    "signal": settings.features.macd_signal,
                },
                min_candles_required=settings.features.macd_slow
                + settings.features.macd_signal
                + 1,
            ),
            FeatureDefinition(
                name="momentum_macd_signal",
                group=FeatureGroup.MOMENTUM,
                description="MACD signal line",
                min_candles_required=settings.features.macd_slow
                + settings.features.macd_signal
                + 1,
            ),
            FeatureDefinition(
                name="momentum_macd_histogram",
                group=FeatureGroup.MOMENTUM,
                description="MACD histogram (line - signal)",
                min_candles_required=settings.features.macd_slow
                + settings.features.macd_signal
                + 1,
            ),
            FeatureDefinition(
                name="momentum_macd_cross",
                group=FeatureGroup.MOMENTUM,
                description="MACD crossover signal",
                min_candles_required=settings.features.macd_slow
                + settings.features.macd_signal
                + 2,
            ),
            FeatureDefinition(
                name="momentum_roc",
                group=FeatureGroup.MOMENTUM,
                description=f"ROC({settings.features.roc_period})",
                parameters={"period": settings.features.roc_period},
                min_candles_required=settings.features.roc_period + 1,
            ),
        ]

    def compute(self, df: pd.DataFrame) -> dict[str, float]:
        settings = get_settings()
        close = df["close"]

        features: dict[str, float] = {}

        # RSI
        rsi = _rsi(close, settings.features.rsi_period)
        features["momentum_rsi"] = rsi

        # RSI zone
        if rsi >= settings.features.rsi_overbought:
            features["momentum_rsi_zone"] = 1.0
        elif rsi <= settings.features.rsi_oversold:
            features["momentum_rsi_zone"] = -1.0
        else:
            features["momentum_rsi_zone"] = 0.0

        # MACD
        macd_line, macd_signal_line, macd_histogram = _macd(
            close,
            settings.features.macd_fast,
            settings.features.macd_slow,
            settings.features.macd_signal,
        )

        features["momentum_macd_line"] = macd_line
        features["momentum_macd_signal"] = macd_signal_line
        features["momentum_macd_histogram"] = macd_histogram

        # MACD crossover
        features["momentum_macd_cross"] = _macd_cross(
            close,
            settings.features.macd_fast,
            settings.features.macd_slow,
            settings.features.macd_signal,
        )

        # ROC
        features["momentum_roc"] = _roc(close, settings.features.roc_period)

        return features


def _rsi(close: pd.Series, period: int) -> float:
    """Calculate RSI for the latest candle using Wilder's smoothing.

    Uses exponential moving average for gain/loss smoothing.
    """
    if len(close) < period + 1:
        return 50.0  # neutral default

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain.iloc[-1] / avg_loss.iloc[-1] if avg_loss.iloc[-1] != 0 else 100.0
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def _macd(
    close: pd.Series,
    fast: int,
    slow: int,
    signal_period: int,
) -> tuple[float, float, float]:
    """Calculate MACD line, signal, and histogram for the latest candle."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return (
        macd_line.iloc[-1],
        signal_line.iloc[-1],
        histogram.iloc[-1],
    )


def _macd_cross(
    close: pd.Series,
    fast: int,
    slow: int,
    signal_period: int,
) -> float:
    """Detect MACD crossover: 1=bullish, -1=bearish, 0=none."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

    if len(macd_line) < 2:
        return 0.0

    curr_diff = macd_line.iloc[-1] - signal_line.iloc[-1]
    prev_diff = macd_line.iloc[-2] - signal_line.iloc[-2]

    if prev_diff <= 0 and curr_diff > 0:
        return 1.0
    if prev_diff >= 0 and curr_diff < 0:
        return -1.0
    return 0.0


def _roc(close: pd.Series, period: int) -> float:
    """Calculate Rate of Change for the latest candle."""
    if len(close) < period + 1:
        return 0.0

    past_close = close.iloc[-period - 1]
    if past_close == 0.0:
        return 0.0

    return float((close.iloc[-1] - past_close) / past_close * 100.0)
