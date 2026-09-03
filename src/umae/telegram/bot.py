"""Telegram bot main setup and lifecycle management.

Handles bot initialization, handler registration, error handling,
graceful shutdown, and reconnection logic.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING

from telegram import BotCommand, BotCommandScopeDefault, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from umae.telegram.callbacks import handle_callback, handle_text_search
from umae.telegram.formatter import TelegramFormatter
from umae.telegram.handlers import (
    handle_add,
    handle_analyze,
    handle_help,
    handle_remove,
    handle_start,
    handle_status,
    handle_unknown,
    handle_watchlist,
)
from umae.telegram.security import UpdateDeduplicator, UserRateLimiter

if TYPE_CHECKING:
    from umae.interfaces.analysis_service import AnalysisService as CoreAnalysisService
    from umae.storage.repositories import WatchlistRepository
    from umae.telegram.config import TelegramBotConfig

logger = logging.getLogger(__name__)


class UMAEBot:
    """Main UMAE Telegram bot.

    Manages the bot lifecycle: setup, handler registration,
    error handling, graceful shutdown, and reconnection.
    """

    def __init__(
        self,
        config: TelegramBotConfig,
        core_analysis_service: CoreAnalysisService,
        watchlist_repo: WatchlistRepository,
    ) -> None:
        self._config = config
        self._core_analysis = core_analysis_service
        self._watchlist_repo = watchlist_repo
        self._application: Application | None = None
        self._running = False

    def _build_application(self) -> Application:
        """Build and configure the telegram Application."""
        from umae.telegram.services import AnalysisService, WatchlistService

        app = Application.builder().token(self._config.bot_token).build()

        # Shared services
        analysis_svc = AnalysisService(self._core_analysis)
        watchlist_svc = WatchlistService(
            repo=self._watchlist_repo,
            analysis_service=analysis_svc,
            max_size=self._config.max_watchlist_size,
        )

        # Shared security
        rate_limiter = UserRateLimiter(
            max_commands=self._config.rate_limit,
            window=self._config.rate_window,
        )
        dedup = UpdateDeduplicator(max_size=self._config.max_dedup_size)
        formatter = TelegramFormatter()

        # Store shared objects in bot_data for handlers
        app.bot_data["analysis_service"] = analysis_svc
        app.bot_data["watchlist_service"] = watchlist_svc
        app.bot_data["rate_limiter"] = rate_limiter
        app.bot_data["dedup"] = dedup
        app.bot_data["formatter"] = formatter
        app.bot_data["config"] = self._config

        # Register command handlers
        app.add_handler(CommandHandler("start", handle_start))
        app.add_handler(CommandHandler("help", handle_help))
        app.add_handler(CommandHandler("analyze", handle_analyze))
        app.add_handler(CommandHandler("status", handle_status))
        app.add_handler(CommandHandler("watchlist", handle_watchlist))
        app.add_handler(CommandHandler("add", handle_add))
        app.add_handler(CommandHandler("remove", handle_remove))

        # Register callback query handler for inline keyboards
        from telegram.ext import CallbackQueryHandler

        app.add_handler(CallbackQueryHandler(handle_callback))

        # Text message handler (for search mode)
        from telegram.ext import MessageHandler as _MH

        app.add_handler(_MH(filters.TEXT & ~filters.COMMAND, handle_text_search))

        # Catch-all for unknown commands
        app.add_handler(MessageHandler(filters.COMMAND, handle_unknown))

        # Error handler
        app.add_error_handler(self._error_handler)

        return app

    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors from handler processing."""
        logger.exception("Unhandled exception in handler", exc_info=context.error)

        if isinstance(update, Update) and update.message:
            try:
                await update.message.reply_text(
                    "An unexpected error occurred. Please try again later."
                )
            except Exception:
                logger.warning("Failed to send error message to user")

    async def _post_init(self, application: Application) -> None:
        """Called after Application is initialized."""
        # Set bot commands in Telegram UI
        commands = [
            BotCommand("start", "Welcome message"),
            BotCommand("help", "Show help"),
            BotCommand("analyze", "Analyze an asset"),
            BotCommand("status", "System health"),
            BotCommand("watchlist", "Show your watchlist"),
            BotCommand("add", "Add to watchlist"),
            BotCommand("remove", "Remove from watchlist"),
        ]
        await application.bot.set_my_commands(commands, BotCommandScopeDefault())
        logger.info("Bot commands registered")

    async def _post_shutdown(self, application: Application) -> None:
        """Called during graceful shutdown."""
        logger.info("Bot shutting down gracefully")
        self._running = False

    async def run(self) -> None:
        """Run the bot with reconnection logic.

        Starts polling for updates. Reconnects automatically
        on transient errors with exponential backoff.
        """
        if not self._config.is_configured:
            logger.critical("Bot token not configured. Cannot start.")
            return

        self._application = self._build_application()
        self._running = True
        self._shutdown_event = asyncio.Event()

        max_retries = 5
        retries = 0

        while retries < max_retries and self._running:
            try:
                logger.info("Starting bot polling (attempt %d)", retries + 1)
                # Initialize the application
                await self._application.initialize()
                await self._post_init(self._application)
                await self._application.start()
                await self._application.updater.start_polling(
                    allowed_updates=Update.ALL_TYPES,
                    drop_pending_updates=True,
                )
                # Wait for shutdown signal
                await self._shutdown_event.wait()
                # Cleanup
                await self._application.updater.stop()
                await self._application.stop()
                await self._application.shutdown()
                await self._post_shutdown(self._application)
                break
            except Exception as e:
                retries += 1
                wait_time = min(2**retries, 60)
                logger.warning(
                    "Polling failed (%s). Reconnecting in %ds (attempt %d/%d)",
                    type(e).__name__,
                    wait_time,
                    retries,
                    max_retries,
                )
                await asyncio.sleep(wait_time)

        if retries >= max_retries:
            logger.critical("Max retries reached. Bot shutting down.")

        self._running = False

    def stop(self) -> None:
        """Signal the bot to stop gracefully."""
        logger.info("Stop requested")
        self._running = False
        if hasattr(self, "_shutdown_event"):
            self._shutdown_event.set()

    def setup_signal_handlers(self) -> None:
        """Register OS signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop)
