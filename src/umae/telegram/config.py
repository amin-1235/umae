"""Telegram bot configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramBotConfig(BaseSettings):
    """Telegram-specific configuration loaded from environment variables.

    Bot token MUST come from TELEGRAM_BOT_TOKEN env var.
    """

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_")

    bot_token: str = Field(..., description="Telegram bot token from BotFather")
    enabled: bool = Field(default=False, description="Enable Telegram bot")
    rate_limit: int = Field(default=10, description="Max commands per minute per user")
    rate_window: int = Field(default=60, description="Rate limit window in seconds")
    max_message_length: int = Field(default=4096, description="Max Telegram message length")
    dedup_window: int = Field(default=300, description="Update deduplication window in seconds")
    max_dedup_size: int = Field(default=10000, description="Max dedup set size before cleanup")
    max_watchlist_size: int = Field(default=50, description="Max symbols per user watchlist")

    @property
    def is_configured(self) -> bool:
        """Check if bot token is set."""
        return bool(self.bot_token)
