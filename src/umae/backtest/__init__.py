"""UMAE backtest package."""

from umae.backtest.baseline import BaselineStrategies
from umae.backtest.engine import BacktestConfig, Backtester, BacktestTrade
from umae.backtest.metrics import BacktestMetrics, MetricsCalculator, SegmentMetrics
from umae.backtest.walk_forward import WalkForwardResult, WalkForwardValidator, WindowResult

__all__ = [
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestTrade",
    "Backtester",
    "BaselineStrategies",
    "MetricsCalculator",
    "SegmentMetrics",
    "WalkForwardResult",
    "WalkForwardValidator",
    "WindowResult",
]
