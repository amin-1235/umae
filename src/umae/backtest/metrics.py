"""Performance metrics calculator for backtest results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class BacktestMetrics:
    """Aggregated performance metrics."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    expected_return: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    longest_losing_streak: int = 0
    trade_frequency: float = 0.0  # trades per period
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0


@dataclass
class SegmentMetrics:
    """Metrics for a specific segment (timeframe, asset, regime)."""

    segment_key: str
    metrics: BacktestMetrics = field(default_factory=BacktestMetrics)
    sample_size: int = 0


class MetricsCalculator:
    """Calculate performance metrics from backtest trades."""

    def calculate(
        self,
        trades: list[dict[str, Any]],
        equity_curve: pd.DataFrame | None = None,
    ) -> BacktestMetrics:
        """Compute all metrics from a list of trade dictionaries.

        Each trade dict must contain: pnl, pnl_pct, side, entry_time, exit_time.
        """
        if not trades:
            return BacktestMetrics()

        pnls = np.array([t["pnl"] for t in trades])
        pnl_pcts = np.array([t["pnl_pct"] for t in trades])
        sides = [t["side"] for t in trades]

        wins = pnls > 0
        losses = pnls < 0

        total = len(trades)
        n_wins = int(wins.sum())
        n_losses = int(losses.sum())

        accuracy = n_wins / total if total else 0.0
        win_rate = accuracy

        # precision / recall / F1 for long signals
        long_mask = np.array([s.value == "long" for s in sides])
        tp = int((wins & long_mask).sum())
        fp = int((losses & long_mask).sum())
        fn = int((wins & ~long_mask).sum())

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        avg_win = float(pnls[wins].mean()) if n_wins else 0.0
        avg_loss = float(pnls[losses].mean()) if n_losses else 0.0

        gross_profit = float(pnls[wins].sum()) if n_wins else 0.0
        gross_loss = float(abs(pnls[losses].sum())) if n_losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss else float("inf")

        expected_return = float(pnl_pcts.mean())

        # longest losing streak
        streak = 0
        max_streak = 0
        for p in pnls:
            if p < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        # max drawdown from equity curve
        max_dd = 0.0
        if equity_curve is not None and "equity" in equity_curve.columns:
            eq = equity_curve["equity"].values
            peak = np.maximum.accumulate(eq)
            dd = (peak - eq) / peak
            max_dd = float(dd.max())

        # trade frequency (trades per 100 candles approximation)
        if equity_curve is not None and len(equity_curve) > 1:
            trade_frequency = total / len(equity_curve) * 100
        else:
            trade_frequency = 0.0

        # Sharpe ratio (annualized, using 252 trading days proxy)
        sharpe = 0.0
        if len(pnl_pcts) > 1:
            mean_ret = np.mean(pnl_pcts)
            std_ret = np.std(pnl_pcts, ddof=1)
            if std_ret > 0:
                sharpe = float(mean_ret / std_ret * np.sqrt(252))

        return BacktestMetrics(
            total_trades=total,
            winning_trades=n_wins,
            losing_trades=n_losses,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1=f1,
            expected_return=expected_return,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            avg_win=avg_win,
            avg_loss=avg_loss,
            longest_losing_streak=max_streak,
            trade_frequency=trade_frequency,
            sharpe_ratio=sharpe,
            win_rate=win_rate,
        )

    def segment_analysis(
        self,
        trades: list[dict[str, Any]],
        equity_curve: pd.DataFrame | None = None,
        by: str = "timeframe",
    ) -> list[SegmentMetrics]:
        """Compute metrics segmented by timeframe, asset, or regime.

        Args:
            trades: List of trade dicts (must include the grouping key).
            equity_curve: Full equity curve.
            by: Grouping key - "timeframe", "asset", or "regime".

        Returns:
            List of SegmentMetrics per group.
        """
        if not trades:
            return []

        groups: dict[str, list[dict[str, Any]]] = {}
        for t in trades:
            key = str(t.get(by, "unknown"))
            groups.setdefault(key, []).append(t)

        results: list[SegmentMetrics] = []
        for key, group_trades in groups.items():
            metrics = self.calculate(group_trades, equity_curve)
            results.append(
                SegmentMetrics(segment_key=key, metrics=metrics, sample_size=len(group_trades))
            )

        return results
