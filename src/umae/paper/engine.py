"""Paper trading engine for simulated live trading."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from umae.domain.enums import OrderSide, SignalType
from umae.domain.models import Candle, CompositeSignal, FeeModel

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaperTrade:
    """Single paper trade record."""

    entry_time: datetime
    exit_time: datetime
    side: OrderSide
    symbol: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    fee: float
    exit_reason: str


@dataclass
class Position:
    """Open position state."""

    symbol: str
    side: OrderSide
    entry_price: float
    size: float
    entry_time: datetime
    entry_fee: float = 0.0


@dataclass
class PerformanceMetrics:
    """Running performance metrics for the paper portfolio."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0

    def update(self, trade: PaperTrade, current_equity: float) -> None:
        """Update metrics with a completed trade."""
        self.total_trades += 1
        self.total_pnl += trade.pnl
        self.total_fees += trade.fee

        if trade.pnl > 0:
            self.winning_trades += 1
        elif trade.pnl < 0:
            self.losing_trades += 1

        self.win_rate = self.winning_trades / self.total_trades if self.total_trades else 0.0

        self.avg_win = trade.pnl if trade.pnl > 0 else self.avg_win
        self.avg_loss = trade.pnl if trade.pnl < 0 else self.avg_loss

        gross_profit = self.total_pnl if self.total_pnl > 0 else 0.0
        gross_loss = abs(self.total_pnl) if self.total_pnl < 0 else 0.0
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        self.peak_equity = max(self.peak_equity, current_equity)
        if self.peak_equity > 0:
            dd = (self.peak_equity - current_equity) / self.peak_equity
            self.max_drawdown = max(self.max_drawdown, dd)


@dataclass
class PaperPortfolio:
    """Paper trading portfolio state."""

    initial_capital: float = 10_000.0
    cash: float = 10_000.0
    positions: dict[str, Position] = field(default_factory=dict)
    closed_trades: list[PaperTrade] = field(default_factory=list)
    equity_curve: list[dict[str, float | int | datetime]] = field(default_factory=list)
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)

    @property
    def equity(self) -> float:
        """Total portfolio equity (cash + unrealized position value)."""
        return self.cash

    def add_position_value(self, value: float) -> None:
        """Adjust cash for open position value changes."""
        self.cash += value

    def snapshot(self, timestamp: datetime, unrealized: float = 0.0) -> None:
        """Record equity curve snapshot."""
        self.equity_curve.append(
            {
                "timestamp": timestamp,
                "equity": self.cash + unrealized,
                "position_count": len(self.positions),
            }
        )


class PaperTradingEngine:
    """Simulate live trading without real execution.

    Tracks portfolio, generates signals from candles, simulates order
    execution, and calculates P&L and performance metrics.
    """

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        fee_model: FeeModel | None = None,
        spread: float = 0.001,
        slippage: float = 0.0005,
        position_size_pct: float = 0.02,
        max_position_pct: float = 0.10,
        stop_loss_pct: float = 0.02,
        take_profit_pct: float = 0.04,
    ) -> None:
        self._fee_model = fee_model or FeeModel()
        self._spread = spread
        self._slippage = slippage
        self._position_size_pct = position_size_pct
        self._max_position_pct = max_position_pct
        self._stop_loss_pct = stop_loss_pct
        self._take_profit_pct = take_profit_pct

        self._portfolio = PaperPortfolio(initial_capital=initial_capital)
        self._candle_buffer: dict[str, list[Candle]] = {}

    @property
    def portfolio(self) -> PaperPortfolio:
        """Get current portfolio state."""
        return self._portfolio

    def feed_candle(self, symbol: str, candle: Candle) -> None:
        """Ingest a new candle into the buffer for a symbol.

        Args:
            symbol: Asset symbol.
            candle: New OHLCV candle.
        """
        self._candle_buffer.setdefault(symbol, []).append(candle)

    def generate_signal(
        self,
        symbol: str,
        composite: CompositeSignal,
    ) -> SignalType:
        """Evaluate composite signal and decide action.

        Args:
            symbol: Asset symbol.
            composite: CompositeSignal from analysis pipeline.

        Returns:
            SignalType to execute (UP -> long, DOWN -> short, else NO_SIGNAL).
        """
        return composite.signal

    def execute_signal(
        self,
        symbol: str,
        signal: SignalType,
        price: float,
        timestamp: datetime,
    ) -> PaperTrade | None:
        """Simulate order execution based on signal.

        Args:
            symbol: Asset symbol.
            signal: Signal direction.
            price: Current price for execution.
            timestamp: Execution timestamp.

        Returns:
            Completed PaperTrade if a position was closed, else None.
        """
        trade: PaperTrade | None = None

        # Check stop-loss / take-profit on existing position
        if symbol in self._portfolio.positions:
            pos = self._portfolio.positions[symbol]
            sl_tp_trade = self._check_exits(symbol, price, timestamp)
            if sl_tp_trade is not None:
                trade = sl_tp_trade

        # Process new signal
        if signal in (SignalType.UP, SignalType.DOWN):
            new_side = OrderSide.LONG if signal == SignalType.UP else OrderSide.SHORT

            # Close opposite position if exists
            if symbol in self._portfolio.positions:
                pos = self._portfolio.positions[symbol]
                if pos.side != new_side:
                    close_trade = self._close_position(symbol, price, timestamp, "signal")
                    if close_trade is not None:
                        trade = close_trade

            # Open new position if none exists
            if symbol not in self._portfolio.positions:
                self._open_position(symbol, new_side, price, timestamp)

        elif signal == SignalType.NEUTRAL:
            if symbol in self._portfolio.positions:
                close_trade = self._close_position(symbol, price, timestamp, "signal")
                if close_trade is not None:
                    trade = close_trade

        # Record equity snapshot
        unrealized = self._unrealized_pnl(price)
        self._portfolio.snapshot(timestamp, unrealized)

        if trade is not None:
            self._portfolio.metrics.update(trade, self._portfolio.equity)

        return trade

    def get_candles(self, symbol: str, limit: int = 200) -> list[Candle]:
        """Get buffered candles for a symbol.

        Args:
            symbol: Asset symbol.
            limit: Maximum candles to return.

        Returns:
            List of buffered candles.
        """
        candles = self._candle_buffer.get(symbol, [])
        return candles[-limit:]

    def reset(self) -> None:
        """Reset the paper trading engine."""
        capital = self._portfolio.initial_capital
        self._portfolio = PaperPortfolio(initial_capital=capital)
        self._candle_buffer.clear()

    def summary(self) -> dict[str, float | int]:
        """Get a summary of paper trading performance."""
        m = self._portfolio.metrics
        return {
            "initial_capital": self._portfolio.initial_capital,
            "current_equity": self._portfolio.equity,
            "total_pnl": m.total_pnl,
            "total_fees": m.total_fees,
            "total_trades": m.total_trades,
            "winning_trades": m.winning_trades,
            "losing_trades": m.losing_trades,
            "win_rate": round(m.win_rate, 4),
            "max_drawdown": round(m.max_drawdown, 4),
            "profit_factor": round(m.profit_factor, 4),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_cost(self, price: float, side: OrderSide, is_entry: bool) -> float:
        """Apply spread and slippage to fill price."""
        cost = self._spread + self._slippage
        if is_entry:
            return price * (1 + cost) if side == OrderSide.LONG else price * (1 - cost)
        return price * (1 - cost) if side == OrderSide.LONG else price * (1 + cost)

    def _calc_fee(self, trade_value: float) -> float:
        """Calculate trading fee."""
        fee_decimal = self._fee_model.calculate_fee(Decimal(str(trade_value)))
        return float(fee_decimal)

    def _position_value(self) -> float:
        """Calculate position size based on portfolio equity."""
        raw = self._portfolio.equity * self._position_size_pct
        cap = self._portfolio.equity * self._max_position_pct
        return min(raw, cap)

    def _open_position(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        timestamp: datetime,
    ) -> None:
        """Open a new position."""
        fill_price = self._apply_cost(price, side, is_entry=True)
        size = self._position_value()
        fee = self._calc_fee(size)

        self._portfolio.cash -= size + fee
        self._portfolio.positions[symbol] = Position(
            symbol=symbol,
            side=side,
            entry_price=fill_price,
            size=size,
            entry_time=timestamp,
            entry_fee=fee,
        )

        logger.debug(
            "Opened %s %s at %.4f, size=%.2f, fee=%.4f",
            side.value,
            symbol,
            fill_price,
            size,
            fee,
        )

    def _close_position(
        self,
        symbol: str,
        exit_price: float,
        timestamp: datetime,
        reason: str,
    ) -> PaperTrade | None:
        """Close an existing position and return the trade record."""
        if symbol not in self._portfolio.positions:
            return None

        pos = self._portfolio.positions.pop(symbol)
        fill_price = self._apply_cost(exit_price, pos.side, is_entry=False)

        if pos.side == OrderSide.LONG:
            pnl = (fill_price - pos.entry_price) * (pos.size / pos.entry_price)
        else:
            pnl = (pos.entry_price - fill_price) * (pos.size / pos.entry_price)

        pnl_pct = (fill_price - pos.entry_price) / pos.entry_price
        if pos.side == OrderSide.SHORT:
            pnl_pct = -pnl_pct

        fee = self._calc_fee(pos.size)
        total_fee = pos.entry_fee + fee

        self._portfolio.cash += pos.size + pnl - fee

        trade = PaperTrade(
            entry_time=pos.entry_time,
            exit_time=timestamp,
            side=pos.side,
            symbol=symbol,
            entry_price=pos.entry_price,
            exit_price=fill_price,
            size=pos.size,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fee=total_fee,
            exit_reason=reason,
        )
        self._portfolio.closed_trades.append(trade)

        logger.debug(
            "Closed %s %s: pnl=%.4f, reason=%s",
            pos.side.value,
            symbol,
            pnl,
            reason,
        )

        return trade

    def _check_exits(
        self,
        symbol: str,
        current_price: float,
        timestamp: datetime,
    ) -> PaperTrade | None:
        """Check stop-loss and take-profit for an open position."""
        if symbol not in self._portfolio.positions:
            return None

        pos = self._portfolio.positions[symbol]

        if pos.side == OrderSide.LONG:
            sl_price = pos.entry_price * (1 - self._stop_loss_pct)
            tp_price = pos.entry_price * (1 + self._take_profit_pct)
            if current_price <= sl_price:
                return self._close_position(symbol, sl_price, timestamp, "stop_loss")
            if current_price >= tp_price:
                return self._close_position(symbol, tp_price, timestamp, "take_profit")
        else:
            sl_price = pos.entry_price * (1 + self._stop_loss_pct)
            tp_price = pos.entry_price * (1 - self._take_profit_pct)
            if current_price >= sl_price:
                return self._close_position(symbol, sl_price, timestamp, "stop_loss")
            if current_price <= tp_price:
                return self._close_position(symbol, tp_price, timestamp, "take_profit")

        return None

    def _unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L across all open positions."""
        total = 0.0
        for pos in self._portfolio.positions.values():
            if pos.side == OrderSide.LONG:
                total += (current_price - pos.entry_price) * (pos.size / pos.entry_price)
            else:
                total += (pos.entry_price - current_price) * (pos.size / pos.entry_price)
        return total
