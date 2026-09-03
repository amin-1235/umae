"""Backtesting engine for UMAE signal evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

import pandas as pd

from umae.domain.enums import OrderSide, PositionSizing, SignalType
from umae.domain.models import Candle, FeeModel

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True)
class BacktestTrade:
    """Single completed trade record."""

    entry_time: datetime
    exit_time: datetime
    side: OrderSide
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    fee: float
    exit_reason: str  # "signal", "stop_loss", "take_profit", "end_of_data"


@dataclass
class BacktestConfig:
    """Runtime configuration for a backtest run."""

    initial_capital: float = 10_000.0
    fee_model: FeeModel = field(default_factory=FeeModel)
    spread: float = 0.001
    slippage: float = 0.0005
    position_sizing: PositionSizing = PositionSizing.PERCENTAGE
    position_size: float = 0.02
    max_position: float = 0.10
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04


class Backtester:
    """Run backtest simulation with candles and signals."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(
        self,
        candles: list[Candle],
        signals: dict[datetime, SignalType],
    ) -> tuple[list[BacktestTrade], pd.DataFrame]:
        """Execute backtest and return trades plus equity curve.

        Args:
            candles: Chronologically sorted candle data.
            signals: Mapping of candle timestamp -> signal direction.

        Returns:
            Tuple of (list of completed trades, equity DataFrame).
        """
        if not candles:
            return [], pd.DataFrame()

        df = self._candles_to_df(candles)
        trades, equity = self._simulate(df, signals)
        return trades, equity

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _candles_to_df(self, candles: list[Candle]) -> pd.DataFrame:
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

    def _apply_cost(self, price: float, side: OrderSide, is_entry: bool) -> float:
        """Apply spread and slippage to a fill price."""
        cost = self.config.spread + self.config.slippage
        if is_entry:
            return price * (1 + cost) if side == OrderSide.LONG else price * (1 - cost)
        return price * (1 - cost) if side == OrderSide.LONG else price * (1 + cost)

    def _calc_fee(self, trade_value: float) -> float:
        fee_decimal = self.config.fee_model.calculate_fee(Decimal(str(trade_value)))
        return float(fee_decimal)

    def _position_value(self, capital: float) -> float:
        if self.config.position_sizing == PositionSizing.FIXED:
            return self.config.position_size
        raw = capital * self.config.position_size
        cap = capital * self.config.max_position
        return min(raw, cap)

    def _close_position(
        self,
        side: OrderSide,
        entry_price: float,
        exit_price: float,
        size: float,
    ) -> tuple[float, float, float]:
        """Return (pnl, pnl_pct, fee) for a closed position."""
        if side == OrderSide.LONG:
            pnl = (exit_price - entry_price) * (size / entry_price)
        else:
            pnl = (entry_price - exit_price) * (size / entry_price)

        pnl_pct = (exit_price - entry_price) / entry_price
        if side == OrderSide.SHORT:
            pnl_pct = -pnl_pct

        trade_value = size
        fee = self._calc_fee(trade_value)
        return pnl, pnl_pct, fee

    def _check_exits(
        self,
        side: OrderSide,
        entry_price: float,
        high: float,
        low: float,
    ) -> tuple[float | None, str]:
        """Return (exit_price, reason) if stop-loss or take-profit hit."""
        sl = self.config.stop_loss_pct
        tp = self.config.take_profit_pct

        if side == OrderSide.LONG:
            sl_price = entry_price * (1 - sl)
            tp_price = entry_price * (1 + tp)
            if low <= sl_price:
                return sl_price, "stop_loss"
            if high >= tp_price:
                return tp_price, "take_profit"
        else:
            sl_price = entry_price * (1 + sl)
            tp_price = entry_price * (1 - tp)
            if high >= sl_price:
                return sl_price, "stop_loss"
            if low <= tp_price:
                return tp_price, "take_profit"

        return None, ""

    def _simulate(
        self,
        df: pd.DataFrame,
        signals: dict[datetime, SignalType],
    ) -> tuple[list[BacktestTrade], pd.DataFrame]:
        """Walk through candles, collecting trades and equity."""
        capital = self.config.initial_capital
        position: OrderSide | None = None
        entry_price = 0.0
        entry_time: datetime | None = None
        entry_size = 0.0
        entry_fee = 0.0

        trades: list[BacktestTrade] = []
        equity_records: list[dict[str, float]] = []

        for ts, row in df.iterrows():
            close = row["close"]
            high = row["high"]
            low = row["low"]

            # --- check stop-loss / take-profit on open position ---
            if position is not None and entry_time is not None:
                exit_price, exit_reason = self._check_exits(position, entry_price, high, low)
                if exit_price is not None:
                    exit_price_adj = self._apply_cost(exit_price, position, is_entry=False)
                    pnl, pnl_pct, fee = self._close_position(
                        position, entry_price, exit_price_adj, entry_size
                    )
                    trades.append(
                        BacktestTrade(
                            entry_time=entry_time,
                            exit_time=ts,
                            side=position,
                            entry_price=entry_price,
                            exit_price=exit_price_adj,
                            size=entry_size,
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            fee=fee + entry_fee,
                            exit_reason=exit_reason,
                        )
                    )
                    capital += entry_size + pnl - fee
                    equity_records.append({"timestamp": ts, "equity": capital, "position": 0})
                    position = None
                    entry_time = None
                    continue

            # --- process signal ---
            signal = signals.get(ts, SignalType.NO_SIGNAL)
            if signal in (SignalType.UP, SignalType.DOWN):
                # close opposite before opening new
                if position is not None and entry_time is not None:
                    exit_price_adj = self._apply_cost(close, position, is_entry=False)
                    pnl, pnl_pct, fee = self._close_position(
                        position, entry_price, exit_price_adj, entry_size
                    )
                    trades.append(
                        BacktestTrade(
                            entry_time=entry_time,
                            exit_time=ts,
                            side=position,
                            entry_price=entry_price,
                            exit_price=exit_price_adj,
                            size=entry_size,
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            fee=fee + entry_fee,
                            exit_reason="signal",
                        )
                    )
                    capital += entry_size + pnl - fee

                new_side = OrderSide.LONG if signal == SignalType.UP else OrderSide.SHORT
                entry_price_adj = self._apply_cost(close, new_side, is_entry=True)
                size = self._position_value(capital)
                entry_fee = self._calc_fee(size)
                capital -= entry_fee
                position = new_side
                entry_price = entry_price_adj
                entry_time = ts
                entry_size = size

            elif signal == SignalType.NEUTRAL and position is not None and entry_time is not None:
                exit_price_adj = self._apply_cost(close, position, is_entry=False)
                pnl, pnl_pct, fee = self._close_position(
                    position, entry_price, exit_price_adj, entry_size
                )
                trades.append(
                    BacktestTrade(
                        entry_time=entry_time,
                        exit_time=ts,
                        side=position,
                        entry_price=entry_price,
                        exit_price=exit_price_adj,
                        size=entry_size,
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        fee=fee + entry_fee,
                        exit_reason="signal",
                    )
                )
                capital += entry_size + pnl - fee
                position = None
                entry_time = None

            equity_records.append(
                {
                    "timestamp": ts,
                    "equity": capital + (entry_size if position else 0),
                    "position": (
                        1
                        if position == OrderSide.LONG
                        else (-1 if position == OrderSide.SHORT else 0)
                    ),
                }
            )

        # force-close at end
        if position is not None and entry_time is not None:
            last_close = df.iloc[-1]["close"]
            exit_price_adj = self._apply_cost(last_close, position, is_entry=False)
            pnl, pnl_pct, fee = self._close_position(
                position, entry_price, exit_price_adj, entry_size
            )
            trades.append(
                BacktestTrade(
                    entry_time=entry_time,
                    exit_time=df.index[-1],
                    side=position,
                    entry_price=entry_price,
                    exit_price=exit_price_adj,
                    size=entry_size,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    fee=fee + entry_fee,
                    exit_reason="end_of_data",
                )
            )
            capital += entry_size + pnl - fee
            equity_records.append({"timestamp": df.index[-1], "equity": capital, "position": 0})

        equity_df = pd.DataFrame(equity_records).set_index("timestamp")
        return trades, equity_df
