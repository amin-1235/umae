"""Configuration management using pydantic-settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Category → Adapter routing ─────────────────────────────────
# Maps Telegram asset category names to the adapter that supports them.
CATEGORY_PROVIDERS: dict[str, str] = {
    "crypto": "binance",
    "stocks": "yahoo",
    "forex": "yahoo",
    "indices": "yahoo",
}


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = Field(
        default="sqlite:///data/umae.db",
        description="Database URL",
    )
    echo: bool = Field(default=False, description="Echo SQL queries")
    pool_size: int = Field(default=5, description="Connection pool size")


class BinanceConfig(BaseSettings):
    """Binance adapter configuration."""

    model_config = SettingsConfigDict(env_prefix="BINANCE_")

    api_key: str | None = Field(default=None, description="Binance API key")
    api_secret: str | None = Field(default=None, description="Binance API secret")
    base_url: str = Field(
        default="https://api.binance.com",
        description="Binance API base URL",
    )
    rate_limit: int = Field(default=10, description="Requests per second")


class YahooConfig(BaseSettings):
    """Yahoo Finance adapter configuration."""

    model_config = SettingsConfigDict(env_prefix="YAHOO_")

    rate_limit: int = Field(default=5, description="Requests per second")


class TelegramConfig(BaseSettings):
    """Telegram bot configuration."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")

    bot_token: str | None = Field(default=None, description="Telegram bot token")
    enabled: bool = Field(default=False, description="Enable Telegram bot")
    rate_limit: int = Field(default=10, description="Commands per minute per user")
    max_message_length: int = Field(default=4096, description="Max message length")


class FeatureConfig(BaseSettings):
    """Feature engine configuration."""

    model_config = SettingsConfigDict(env_prefix="FEATURE_")

    # Trend features
    ema_fast_period: int = Field(default=9, description="Fast EMA period")
    ema_slow_period: int = Field(default=21, description="Slow EMA period")
    ema_trend_period: int = Field(default=50, description="Trend EMA period")
    sma_long_period: int = Field(default=200, description="Long SMA period")

    # Momentum features
    rsi_period: int = Field(default=14, description="RSI period")
    rsi_overbought: float = Field(default=70.0, description="RSI overbought level")
    rsi_oversold: float = Field(default=30.0, description="RSI oversold level")
    macd_fast: int = Field(default=12, description="MACD fast period")
    macd_slow: int = Field(default=26, description="MACD slow period")
    macd_signal: int = Field(default=9, description="MACD signal period")
    roc_period: int = Field(default=10, description="ROC period")

    # Volume features
    volume_period: int = Field(default=20, description="Volume MA period")
    volume_expansion_period: int = Field(default=5, description="Volume expansion period")

    # Volatility features
    atr_period: int = Field(default=14, description="ATR period")
    volatility_period: int = Field(default=100, description="Volatility lookback period")

    # Price structure
    structure_lookback: int = Field(default=20, description="Market structure lookback")
    sr_lookback: int = Field(default=50, description="Support/resistance lookback")


class BacktestConfig(BaseSettings):
    """Backtesting configuration."""

    model_config = SettingsConfigDict(env_prefix="BACKTEST_")

    initial_capital: float = Field(default=10000.0, description="Initial capital")
    maker_fee: float = Field(default=0.001, description="Maker fee")
    taker_fee: float = Field(default=0.001, description="Taker fee")
    base_spread: float = Field(default=0.001, description="Base spread")
    base_slippage: float = Field(default=0.0005, description="Base slippage")

    # Walk-forward
    train_days: int = Field(default=365, description="Training window in days")
    test_days: int = Field(default=180, description="Testing window in days")
    step_days: int = Field(default=90, description="Step size in days")

    # Position sizing
    position_percentage: float = Field(default=0.02, description="Position size %")
    max_position: float = Field(default=0.10, description="Max position %")
    stop_loss_percent: float = Field(default=0.02, description="Stop loss %")
    take_profit_percent: float = Field(default=0.04, description="Take profit %")


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format")
    file: str | None = Field(default=None, description="Log file path")


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_prefix="UMAE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App info
    app_name: str = Field(default="UMAE", description="Application name")
    version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")

    # Sub-configs
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    binance: BinanceConfig = Field(default_factory=BinanceConfig)
    yahoo: YahooConfig = Field(default_factory=YahooConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    features: FeatureConfig = Field(default_factory=FeatureConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v: str | bool) -> bool:
        """Parse debug from string or bool."""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return v


def load_config(config_path: str | Path | None = None) -> Settings:
    """Load configuration from file and environment.

    Args:
        config_path: Path to YAML config file

    Returns:
        Settings instance
    """
    overrides: dict[str, Any] = {}

    if config_path:
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                overrides = yaml.safe_load(f) or {}

    return Settings(**overrides)


_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """Get application settings (cached).

    Returns:
        Settings instance
    """
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_config()
    return _settings_cache
