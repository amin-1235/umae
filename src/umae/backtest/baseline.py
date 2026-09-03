"""Baseline trading strategies for comparison."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from umae.domain.enums import SignalType

if TYPE_CHECKING:
    from datetime import datetime

    from umae.domain.models import Candle


def _candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    rows = []
    for c in candles:
        rows.append(
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
            }
        )
    return pd.DataFrame(rows).set_index("timestamp")


class BaselineStrategies:
    """Collection of simple baseline strategies for benchmarking."""

    @staticmethod
    def buy_and_hold(candles: list[Candle]) -> dict[datetime, SignalType]:
        """Buy on first candle, hold until end.

        Returns UP on first candle, NEUTRAL on last candle.
        """
        if not candles:
            return {}
        return {
            candles[0].timestamp: SignalType.UP,
            candles[-1].timestamp: SignalType.NEUTRAL,
        }

    @staticmethod
    def ma_crossover(
        candles: list[Candle],
        fast_period: int = 9,
        slow_period: int = 21,
    ) -> dict[datetime, SignalType]:
        """Moving average crossover strategy.

        Generates UP when fast MA crosses above slow MA, DOWN on cross below.
        """
        if len(candles) < slow_period + 1:
            return {}

        df = _candles_to_df(candles)
        fast = df["close"].ewm(span=fast_period, adjust=False).mean()
        slow = df["close"].ewm(span=slow_period, adjust=False).mean()

        signals: dict[datetime, SignalType] = {}
        prev_fast = fast.iloc[0]
        prev_slow = slow.iloc[0]

        for i in range(1, len(df)):
            ts = df.index[i]
            cur_fast = fast.iloc[i]
            cur_slow = slow.iloc[i]

            if prev_fast <= prev_slow and cur_fast > cur_slow:
                signals[ts] = SignalType.UP
            elif prev_fast >= prev_slow and cur_fast < cur_slow:
                signals[ts] = SignalType.DOWN

            prev_fast = cur_fast
            prev_slow = cur_slow

        return signals

    @staticmethod
    def rsi_mean_reversion(
        candles: list[Candle],
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
    ) -> dict[datetime, SignalType]:
        """RSI mean-reversion strategy.

        Generates UP when RSI crosses above oversold, DOWN on cross below overbought.
        """
        if len(candles) < rsi_period + 1:
            return {}

        df = _candles_to_df(candles)
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)

        avg_gain = gain.ewm(alpha=1 / rsi_period, min_periods=rsi_period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / rsi_period, min_periods=rsi_period, adjust=False).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50.0)

        signals: dict[datetime, SignalType] = {}
        prev_rsi = rsi.iloc[0]

        for i in range(1, len(df)):
            ts = df.index[i]
            cur_rsi = rsi.iloc[i]

            if prev_rsi <= oversold and cur_rsi > oversold:
                signals[ts] = SignalType.UP
            elif prev_rsi >= overbought and cur_rsi < overbought:
                signals[ts] = SignalType.DOWN

            prev_rsi = cur_rsi

        return signals

    @classmethod
    def all_baselines(
        cls,
        candles: list[Candle],
    ) -> dict[str, dict[datetime, SignalType]]:
        """Generate signals for all baseline strategies.

        Returns:
            Dict mapping strategy name to its signals.
        """
        return {
            "buy_and_hold": cls.buy_and_hold(candles),
            "ma_crossover": cls.ma_crossover(candles),
            "rsi_mean_reversion": cls.rsi_mean_reversion(candles),
        }
