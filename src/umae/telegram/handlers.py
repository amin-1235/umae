"""Telegram bot command handlers.

All handlers are async functions that receive the update and context
from python-telegram-bot. They use the services layer for business logic
and the formatter for message construction.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from umae.telegram.models import ProviderStatus, SystemStatus
from umae.telegram.security import InputValidator, UserRateLimiter

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from umae.telegram.formatter import TelegramFormatter
    from umae.telegram.services import AnalysisService, WatchlistService

logger = logging.getLogger(__name__)


async def _check_rate_limit(update: Update, rate_limiter: UserRateLimiter) -> bool:
    """Check rate limit and send warning if exceeded."""
    user_id = update.effective_user.id
    if not rate_limiter.is_allowed(user_id):
        remaining = rate_limiter.remaining(user_id)
        text = f"Rate limit exceeded. Try again later.\nRemaining: {remaining} commands."
        await update.message.reply_text(text)  # type: ignore[union-attr]
        return False
    return True


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - send welcome message with interactive menu."""
    if not update.message:
        return

    from umae.telegram.keyboards import main_menu

    formatter: TelegramFormatter = context.bot_data["formatter"]
    text = formatter.format_welcome()
    keyboard = main_menu()
    await update.message.reply_text(text, reply_markup=keyboard)


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - send help text."""
    if not update.message:
        return

    formatter: TelegramFormatter = context.bot_data["formatter"]
    text = formatter.format_help()
    await update.message.reply_text(text)


async def handle_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analyze <symbol> command - full analysis for a symbol."""
    if not update.message or not context.args:
        text = "Usage: /analyze <symbol>\nExample: /analyze BTCUSDT"
        await update.message.reply_text(text)
        return

    rate_limiter: UserRateLimiter = context.bot_data["rate_limiter"]
    if not _check_rate_limit(update, rate_limiter):
        return

    symbol = InputValidator.parse_analyze_args(context.args)
    if symbol is None:
        raw = context.args[0] if context.args else ""
        text = (
            f"Invalid symbol: {raw}\n\n"
            "Use uppercase letters, numbers, or common separators.\n"
            "Examples: BTCUSDT, BTC/USDT, AAPL, EURUSD, ^GSPC"
        )
        await update.message.reply_text(text)
        return

    analysis_service: AnalysisService = context.bot_data["analysis_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]

    try:
        result = await analysis_service.analyze(symbol)
        text = formatter.format_analysis(result)
        parts = formatter.split_message(text)
        for part in parts:
            await update.message.reply_text(part)
    except KeyError as e:
        text = formatter.format_error(f"Unknown adapter: {e}")
        await update.message.reply_text(text)
    except Exception as e:
        from umae.interfaces.base_adapter import ProviderError

        if isinstance(e, ProviderError):
            text = formatter.format_provider_error(
                symbol=symbol,
                category=e.category,
                message=str(e),
                provider=e.provider,
            )
        else:
            logger.exception("Analysis failed for %s", symbol)
            text = formatter.format_error(f"Analysis failed: {type(e).__name__}")
        await update.message.reply_text(text)


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command - system health."""
    if not update.message:
        return

    rate_limiter: UserRateLimiter = context.bot_data["rate_limiter"]
    if not _check_rate_limit(update, rate_limiter):
        return

    formatter: TelegramFormatter = context.bot_data["formatter"]

    # Check database
    db_status = "ok"
    try:
        from umae.storage.database import get_session

        session = get_session()
        session.execute("SELECT 1")
    except Exception as e:
        db_status = f"error: {type(e).__name__}"

    # Check analysis engine
    engine_status = "ok"
    version = "1.0.0"

    # Probe each provider for connectivity
    providers = []
    analysis_service = context.bot_data["analysis_service"]
    core = analysis_service._core
    if hasattr(core, "_adapters"):
        for name, adapter in core._adapters.items():
            try:
                # Quick probe: try to get exchange info / metadata
                from umae.domain.models import Timeframe

                now = datetime.utcnow()
                start = (now - timedelta(hours=1)).isoformat()
                end = now.isoformat()
                cs = await adapter.fetch_candles("BTCUSDT", Timeframe.H1, start, end)
                if cs.candles:
                    providers.append(ProviderStatus(name=name, status="ok"))
                else:
                    providers.append(
                        ProviderStatus(
                            name=name, status="warning", error_message="No data returned"
                        )
                    )
            except Exception as e:
                from umae.interfaces.base_adapter import ProviderError

                if isinstance(e, ProviderError) and e.category == "DATA_PROVIDER_TLS_ERROR":
                    providers.append(
                        ProviderStatus(
                            name=name,
                            status="error",
                            error_message=f"TLS error: {e.category}",
                        )
                    )
                else:
                    providers.append(
                        ProviderStatus(
                            name=name,
                            status="error",
                            error_message=f"{type(e).__name__}: {e}",
                        )
                    )

    status = SystemStatus(
        providers=providers,
        database_status=db_status,
        analysis_engine_status=engine_status,
        last_update="now",
        uptime_seconds=0,
        active_users=0,
        symbols_tracked=0,
        version=version,
    )
    text = formatter.format_status(status)
    await update.message.reply_text(text)


async def handle_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /watchlist command - show user's watchlist."""
    if not update.message:
        return

    rate_limiter: UserRateLimiter = context.bot_data["rate_limiter"]
    if not _check_rate_limit(update, rate_limiter):
        return

    watchlist_service: WatchlistService = context.bot_data["watchlist_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]

    user_id = update.effective_user.id
    try:
        result = await watchlist_service.get_watchlist(user_id)
        text = formatter.format_watchlist(result)
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("Watchlist fetch failed for user %s", user_id)
        text = formatter.format_error(f"Failed to load watchlist: {type(e).__name__}")
        await update.message.reply_text(text)


async def handle_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add <symbol> command - add to watchlist."""
    if not update.message or not context.args:
        text = "Usage: /add <symbol>\nExample: /add BTCUSDT"
        await update.message.reply_text(text)
        return

    rate_limiter: UserRateLimiter = context.bot_data["rate_limiter"]
    if not _check_rate_limit(update, rate_limiter):
        return

    symbol = InputValidator.parse_analyze_args(context.args)
    if symbol is None:
        raw = context.args[0]
        text = (
            f"Invalid symbol: {raw}\n\n"
            "Use uppercase letters, numbers, or common separators.\n"
            "Examples: BTCUSDT, BTC/USDT, AAPL"
        )
        await update.message.reply_text(text)
        return

    watchlist_service: WatchlistService = context.bot_data["watchlist_service"]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    result = watchlist_service.add_symbol(user_id, chat_id, symbol)

    if result == "full":
        text = "Watchlist is full. Remove a symbol first."
        await update.message.reply_text(text)
    elif result == "duplicate":
        text = f"{symbol} is already in your watchlist."
        await update.message.reply_text(text)
    elif result == "added":
        text = f"Added {symbol} to your watchlist."
        try:
            analysis_result = await watchlist_service._analysis.analyze(symbol)
            text += (
                f"\n\nCurrent: {analysis_result.signal.upper()} {analysis_result.signal_score:+.2f}"
            )
        except Exception as e:
            logger.warning("Failed to analyze %s after adding to watchlist: %s", symbol, e)
            text += "\n\nCould not fetch current analysis."
        await update.message.reply_text(text)


async def handle_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /remove <symbol> command - remove from watchlist."""
    if not update.message or not context.args:
        text = "Usage: /remove <symbol>\nExample: /remove BTCUSDT"
        await update.message.reply_text(text)
        return

    rate_limiter: UserRateLimiter = context.bot_data["rate_limiter"]
    if not _check_rate_limit(update, rate_limiter):
        return

    symbol = InputValidator.parse_analyze_args(context.args)
    if symbol is None:
        raw = context.args[0]
        text = f"Invalid symbol: {raw}"
        await update.message.reply_text(text)
        return

    watchlist_service: WatchlistService = context.bot_data["watchlist_service"]
    user_id = update.effective_user.id

    result = watchlist_service.remove_symbol(user_id, symbol)

    if result == "removed":
        text = f"Removed {symbol} from your watchlist."
        await update.message.reply_text(text)
    elif result == "not_found":
        text = f"{symbol} is not in your watchlist."
        await update.message.reply_text(text)


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unknown commands."""
    if not update.message:
        return

    text = "Unknown command.\n\nUse /help for available commands."
    await update.message.reply_text(text)
