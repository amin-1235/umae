"""SQLAlchemy models for storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class CandleModel(Base):
    """Candle data model."""

    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=0.0)
    quote_volume = Column(Float, nullable=True)
    trades_count = Column(Integer, nullable=True)
    is_complete = Column(Boolean, nullable=False, default=True)
    source = Column(String(50), nullable=False)
    data_version = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<CandleModel(symbol={self.symbol}, timeframe={self.timeframe}, "
            f"timestamp={self.timestamp})>"
        )


class FeatureModel(Base):
    """Computed features model."""

    __tablename__ = "features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    features = Column(Text, nullable=False)  # JSON string
    feature_version = Column(String(50), nullable=False)
    computed_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return (
            f"<FeatureModel(symbol={self.symbol}, timeframe={self.timeframe}, "
            f"timestamp={self.timestamp})>"
        )


class SignalModel(Base):
    """Signal audit record model."""

    __tablename__ = "signals"

    id = Column(String(36), primary_key=True)  # UUID
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    asset_type = Column(String(20), nullable=False)
    exchange = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False)
    price = Column(Float, nullable=False)
    signal = Column(String(20), nullable=False)
    raw_score = Column(Float, nullable=False)
    calibrated_confidence = Column(Float, nullable=True)
    features = Column(Text, nullable=False)  # JSON string
    market_regime = Column(String(30), nullable=False)
    regime_confidence = Column(Float, nullable=False)
    timeframe_signals = Column(Text, nullable=False)  # JSON string
    reason_codes = Column(Text, nullable=False)  # JSON string
    contributing_factors = Column(Text, nullable=True)  # JSON string
    model_version = Column(String(50), nullable=False)
    data_version = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SignalModel(id={self.id}, symbol={self.symbol}, signal={self.signal})>"


class BacktestRunModel(Base):
    """Backtest run metadata model."""

    __tablename__ = "backtest_runs"

    id = Column(String(36), primary_key=True)  # UUID
    name = Column(String(100), nullable=False)
    strategy_config = Column(Text, nullable=False)  # JSON string
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    symbol = Column(String(50), nullable=False)
    timeframe = Column(String(10), nullable=False)
    initial_capital = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String(20), nullable=False, default="running")
    error = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<BacktestRunModel(id={self.id}, name={self.name})>"


class BacktestTradeModel(Base):
    """Backtest trade model."""

    __tablename__ = "backtest_trades"

    id = Column(String(36), primary_key=True)  # UUID
    backtest_run_id = Column(String(36), nullable=False, index=True)
    entry_timestamp = Column(DateTime, nullable=False)
    entry_price = Column(Float, nullable=False)
    entry_signal = Column(String(20), nullable=False)
    exit_timestamp = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_signal = Column(String(20), nullable=True)
    side = Column(String(10), nullable=False)
    size = Column(Float, nullable=False)
    fee_entry = Column(Float, nullable=False)
    fee_exit = Column(Float, nullable=True)
    slippage_entry = Column(Float, nullable=False)
    slippage_exit = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    holding_periods = Column(Integer, nullable=True)
    regime_at_entry = Column(String(30), nullable=False)
    regime_at_exit = Column(String(30), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<BacktestTradeModel(id={self.id}, side={self.side})>"


class AssetMetadataModel(Base):
    """Asset metadata model."""

    __tablename__ = "asset_metadata"

    symbol = Column(String(50), primary_key=True)
    asset_type = Column(String(20), nullable=False)
    exchange = Column(String(50), nullable=False)
    timezone = Column(String(50), nullable=False)
    base_currency = Column(String(20), nullable=False)
    quote_currency = Column(String(20), nullable=False)
    tick_size = Column(Float, nullable=False)
    lot_size = Column(Float, nullable=True)
    fee_model = Column(Text, nullable=True)  # JSON string
    data_adapter = Column(String(50), nullable=False)
    metadata_version = Column(String(50), nullable=False, default="1.0.0")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AssetMetadataModel(symbol={self.symbol})>"


class WatchlistModel(Base):
    """User watchlist model."""

    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    chat_id = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    symbols = Column(Text, nullable=False, default="[]")  # JSON string
    alert_config = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<WatchlistModel(user_id={self.user_id})>"


class ModelVersionModel(Base):
    """Model version tracking model."""

    __tablename__ = "model_versions"

    version = Column(String(50), primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    config = Column(Text, nullable=False)  # JSON string
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_active = Column(Boolean, nullable=False, default=True)
    parent_version = Column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<ModelVersionModel(version={self.version})>"
