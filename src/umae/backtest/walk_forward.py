"""Walk-forward validation for time-series strategy evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from umae.backtest.engine import BacktestConfig, Backtester, BacktestTrade
from umae.backtest.metrics import BacktestMetrics, MetricsCalculator
from umae.domain.enums import SignalType
from umae.domain.models import Candle


@dataclass
class WindowResult:
    """Result for a single walk-forward window."""

    window_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_trades: list[BacktestTrade] = field(default_factory=list)
    test_trades: list[BacktestTrade] = field(default_factory=list)
    train_metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    test_metrics: BacktestMetrics = field(default_factory=BacktestMetrics)


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward results."""

    windows: list[WindowResult] = field(default_factory=list)
    aggregated_test_metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    overfitting_score: float = 0.0
    train_test_correlation: float = 0.0


SignalGenerator = Callable[
    [list[Candle], list[Candle]],
    dict[datetime, SignalType],
]


class WalkForwardValidator:
    """Time-series walk-forward evaluation with sliding window."""

    def __init__(
        self,
        train_days: int = 365,
        test_days: int = 180,
        step_days: int = 90,
        config: BacktestConfig | None = None,
    ) -> None:
        self.train_days = train_days
        self.test_days = test_days
        self.step_days = step_days
        self.engine = Backtester(config)
        self.calculator = MetricsCalculator()

    def validate(
        self,
        candles: list[Candle],
        signal_fn: SignalGenerator,
    ) -> WalkForwardResult:
        """Run walk-forward validation over candles.

        Args:
            candles: Full chronologically sorted candle dataset.
            signal_fn: Callable(train_candles, test_candles) -> {timestamp: SignalType}.

        Returns:
            WalkForwardResult with per-window and aggregated metrics.
        """
        if not candles:
            return WalkForwardResult()

        timestamps = [c.timestamp for c in candles]
        start = timestamps[0]
        end = timestamps[-1]

        windows: list[WindowResult] = []
        idx = 0
        current = start

        while current + timedelta(days=self.train_days + self.test_days) <= end:
            train_start = current
            train_end = current + timedelta(days=self.train_days)
            test_start = train_end
            test_end = train_end + timedelta(days=self.test_days)

            train_candles = [c for c in candles if train_start <= c.timestamp < train_end]
            test_candles = [c for c in candles if test_start <= c.timestamp < test_end]

            if not train_candles or not test_candles:
                current += timedelta(days=self.step_days)
                continue

            signals = signal_fn(train_candles, test_candles)

            train_signals = {ts: sig for ts, sig in signals.items() if ts < train_end}
            test_signals = {ts: sig for ts, sig in signals.items() if ts >= test_start}

            train_trades_list, train_eq = self.engine.run(train_candles, train_signals)
            test_trades_list, test_eq = self.engine.run(test_candles, test_signals)

            train_metrics = self.calculator.calculate(
                [self._trade_to_dict(t) for t in train_trades_list], train_eq
            )
            test_metrics = self.calculator.calculate(
                [self._trade_to_dict(t) for t in test_trades_list], test_eq
            )

            windows.append(
                WindowResult(
                    window_index=idx,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                    train_trades=train_trades_list,
                    test_trades=test_trades_list,
                    train_metrics=train_metrics,
                    test_metrics=test_metrics,
                )
            )

            idx += 1
            current += timedelta(days=self.step_days)

        aggregated = self._aggregate_test_metrics(windows)
        overfitting = self._detect_overfitting(windows)
        correlation = self._train_test_correlation(windows)

        return WalkForwardResult(
            windows=windows,
            aggregated_test_metrics=aggregated,
            overfitting_score=overfitting,
            train_test_correlation=correlation,
        )

    def _aggregate_test_metrics(self, windows: list[WindowResult]) -> BacktestMetrics:
        """Aggregate test metrics across all windows."""
        if not windows:
            return BacktestMetrics()

        all_trades: list[dict[str, float | int | str | datetime]] = []
        for w in windows:
            all_trades.extend([self._trade_to_dict(t) for t in w.test_trades])

        if not all_trades:
            return BacktestMetrics()

        return self.calculator.calculate(all_trades)

    def _detect_overfitting(self, windows: list[WindowResult]) -> float:
        """Score 0-1 indicating overfitting (1 = severe overfitting).

        Compares train vs test performance degradation across windows.
        """
        if len(windows) < 2:
            return 0.0

        train_sharpes = [w.train_metrics.sharpe_ratio for w in windows]
        test_sharpes = [w.test_metrics.sharpe_ratio for w in windows]

        train_arr = np.array(train_sharpes)
        test_arr = np.array(test_sharpes)

        train_mean = np.mean(train_arr) if len(train_arr) else 0
        test_mean = np.mean(test_arr) if len(test_arr) else 0

        if train_mean == 0:
            return 0.0

        degradation = max(0.0, (train_mean - test_mean) / abs(train_mean))
        return min(1.0, float(degradation))

    def _train_test_correlation(self, windows: list[WindowResult]) -> float:
        """Pearson correlation between train and test Sharpe ratios."""
        if len(windows) < 2:
            return 0.0

        train_arr = np.array([w.train_metrics.sharpe_ratio for w in windows])
        test_arr = np.array([w.test_metrics.sharpe_ratio for w in windows])

        if np.std(train_arr) == 0 or np.std(test_arr) == 0:
            return 0.0

        corr = np.corrcoef(train_arr, test_arr)[0, 1]
        return float(corr) if not np.isnan(corr) else 0.0

    @staticmethod
    def _trade_to_dict(trade: BacktestTrade) -> dict[str, float | int | str | datetime]:
        return {
            "pnl": trade.pnl,
            "pnl_pct": trade.pnl_pct,
            "side": trade.side.value,
            "entry_time": trade.entry_time,
            "exit_time": trade.exit_time,
            "exit_reason": trade.exit_reason,
            "fee": trade.fee,
            "size": trade.size,
        }
