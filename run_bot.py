"""Run the UMAE Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def setup_logging() -> None:
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )


async def _run_with_cleanup(
    bot: "UMAEBot",
    adapters: list,
    database: "Database",
) -> None:
    """Run bot with deterministic cleanup of all resources."""
    logger = logging.getLogger(__name__)
    try:
        await bot.run()
    finally:
        # Close all adapters — suppress errors to ensure all are attempted
        for adapter in adapters:
            try:
                if hasattr(adapter, "close"):
                    await adapter.close()
                    logger.info("Closed adapter: %s", type(adapter).__name__)
            except Exception as e:
                logger.warning("Error closing adapter %s: %s", type(adapter).__name__, e)
        # Close database
        try:
            database.close()
            logger.info("Database connections closed")
        except Exception as e:
            logger.warning("Error closing database: %s", e)


def main() -> None:
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Load .env file if exists
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # Strip surrounding quotes from value
                    value = value.strip().strip("'\"")
                    os.environ.setdefault(key.strip(), value)

    # Check bot token
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.critical("TELEGRAM_BOT_TOKEN not set. Cannot start bot.")
        logger.info("Set it in .env file or environment variable.")
        sys.exit(1)

    # Import after env is loaded
    from umae.telegram.bot import UMAEBot
    from umae.telegram.config import TelegramBotConfig
    from umae.interfaces.analysis_service import AnalysisService
    from umae.storage.repositories import WatchlistRepository
    from umae.storage.database import Database
    from umae.data.binance_adapter import BinanceAdapter
    from umae.data.yahoo_adapter import YahooFinanceAdapter
    from umae.interfaces.base_adapter import RateLimiter

    # Setup database
    db_url = os.environ.get("DATABASE_URL", "sqlite:///data/umae.db")
    # Ensure data directory exists
    data_dir = os.path.dirname(db_url.replace("sqlite:///", ""))
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
    database = Database(db_url)
    database.create_tables()

    # Setup data adapters
    binance_adapter = BinanceAdapter(
        rate_limiter=RateLimiter(max_requests=10, time_window=1.0),
    )
    yahoo_adapter = YahooFinanceAdapter(
        rate_limiter=RateLimiter(max_requests=5, time_window=1.0),
    )

    # Setup core analysis service with real adapters
    core_analysis = AnalysisService(
        adapters={
            "binance": binance_adapter,
            "yahoo": yahoo_adapter,
        },
        default_adapter="binance",
    )

    # Setup watchlist repository
    watchlist_repo = WatchlistRepository()

    # Setup config
    config = TelegramBotConfig()

    # Create bot with real analysis service
    bot = UMAEBot(
        config=config,
        core_analysis_service=core_analysis,
        watchlist_repo=watchlist_repo,
    )

    logger.info("Starting UMAE Telegram Bot...")
    logger.info("Bot token: ***")

    # Run bot with deterministic adapter cleanup
    try:
        asyncio.run(_run_with_cleanup(bot, [binance_adapter, yahoo_adapter], database))
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception:
        logger.exception("Bot crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
