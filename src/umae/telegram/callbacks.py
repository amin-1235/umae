"""Telegram callback query handler.

Handles all inline keyboard interactions for the UMAE bot.
Dispatches based on callback data prefixes.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

from umae.telegram.keyboards import (
    analysis_actions,
    category_menu,
    main_menu,
    timeframe_menu,
    watchlist_menu,
)

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from umae.telegram.formatter import TelegramFormatter
    from umae.telegram.services import AnalysisService, WatchlistService

logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all callback queries to the appropriate handler."""
    query = update.callback_query
    if not query or not query.data:
        return

    await query.answer()

    data = query.data
    parts = data.split(":")

    try:
        action = parts[0]

        if action == "cat":
            await _handle_category(query, context, parts)
        elif action == "asset":
            await _handle_asset(query, context, parts)
        elif action == "tf":
            await _handle_timeframe(query, context, parts)
        elif action == "multi":
            await _handle_multi_tf(query, context, parts)
        elif action == "back":
            await _handle_back(query, context, parts)
        elif action == "watch":
            await _handle_watchlist(query, context, parts)
        elif action == "search":
            await _handle_search(query, context, parts)
        elif action == "status":
            await _handle_status(query, context)
        elif action == "help":
            await _handle_help(query, context)
        elif action == "refresh":
            await _handle_refresh(query, context, parts)
        elif action == "noop":
            pass
        else:
            logger.warning("Unknown callback action: %s", action)

    except Exception as e:
        logger.exception("Callback handling failed for %s", data)
        with contextlib.suppress(Exception):
            await query.edit_message_text(f"Error: {type(e).__name__}\n\nPlease try again.")


async def _handle_category(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Show assets for a category."""
    if len(parts) < 2:
        return
    category = parts[1]
    text = f"Select an asset from {category.title()}:"
    keyboard = category_menu(category)
    await query.edit_message_text(text, reply_markup=keyboard)


async def _handle_asset(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Show timeframe selection for an asset."""
    if len(parts) < 3:
        return
    category = parts[1]
    asset = parts[2]
    text = f"Select timeframe for {asset}:"
    keyboard = timeframe_menu(category, asset)
    await query.edit_message_text(text, reply_markup=keyboard)


async def _handle_timeframe(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Run single-timeframe analysis."""
    if len(parts) < 4:
        return
    category = parts[1]
    asset = parts[2]
    tf = parts[3]

    text = f"Analyzing {asset} ({tf})..."
    await query.edit_message_text(text)

    analysis_service: AnalysisService = context.bot_data["analysis_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]

    try:
        result = await analysis_service.analyze(asset)
        text = formatter.format_analysis_single_tf(result, tf)
        keyboard = analysis_actions(category, asset, tf)
        await query.edit_message_text(text, reply_markup=keyboard)
    except Exception as e:
        from umae.interfaces.base_adapter import ProviderError

        if isinstance(e, ProviderError):
            text = formatter.format_provider_error(
                symbol=asset,
                category=e.category,
                message=str(e),
                provider=e.provider,
            )
        else:
            logger.exception("Analysis failed for %s %s", asset, tf)
            text = formatter.format_error(f"Analysis failed: {type(e).__name__}")
        await query.edit_message_text(text)


async def _handle_multi_tf(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Run multi-timeframe analysis."""
    if len(parts) < 3:
        return
    category = parts[1]
    asset = parts[2]

    text = f"Running multi-TF analysis for {asset}..."
    await query.edit_message_text(text)

    analysis_service: AnalysisService = context.bot_data["analysis_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]

    try:
        result = await analysis_service.analyze(asset)
        text = formatter.format_analysis(result)
        keyboard = analysis_actions(category, asset)
        # Split if too long
        parts_list = formatter.split_message(text)
        if len(parts_list) == 1:
            await query.edit_message_text(text, reply_markup=keyboard)
        else:
            await query.edit_message_text(parts_list[0])
            for part in parts_list[1:-1]:
                await context.bot.send_message(chat_id=query.message.chat_id, text=part)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=parts_list[-1],
                reply_markup=keyboard,
            )
    except Exception as e:
        from umae.interfaces.base_adapter import ProviderError

        if isinstance(e, ProviderError):
            text = formatter.format_provider_error(
                symbol=asset,
                category=e.category,
                message=str(e),
                provider=e.provider,
            )
        else:
            logger.exception("Multi-TF analysis failed for %s", asset)
            text = formatter.format_error(f"Analysis failed: {type(e).__name__}")
        await query.edit_message_text(text)


async def _handle_back(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Handle back navigation."""
    if len(parts) < 2:
        return

    target = parts[1]

    if target == "main":
        formatter: TelegramFormatter = context.bot_data["formatter"]
        text = formatter.format_welcome()
        keyboard = main_menu()
        await query.edit_message_text(text, reply_markup=keyboard)

    elif target == "cat" and len(parts) >= 3:
        category = parts[2]
        text = f"Select an asset from {category.title()}:"
        keyboard = category_menu(category)
        await query.edit_message_text(text, reply_markup=keyboard)

    elif target == "tf" and len(parts) >= 4:
        category = parts[2]
        asset = parts[3]
        text = f"Select timeframe for {asset}:"
        keyboard = timeframe_menu(category, asset)
        await query.edit_message_text(text, reply_markup=keyboard)

    elif target == "watch":
        watchlist_service: WatchlistService = context.bot_data["watchlist_service"]
        user_id = query.from_user.id
        symbols = watchlist_service.get_symbols(user_id)
        formatter: TelegramFormatter = context.bot_data["formatter"]
        text = formatter.format_watchlist_from_symbols(symbols)
        keyboard = watchlist_menu(symbols)
        await query.edit_message_text(text, reply_markup=keyboard)


async def _handle_watchlist(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Handle watchlist operations."""
    if len(parts) < 2:
        return

    sub_action = parts[1]
    watchlist_service: WatchlistService = context.bot_data["watchlist_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if sub_action == "list":
        symbols = watchlist_service.get_symbols(user_id)
        text = formatter.format_watchlist_from_symbols(symbols)
        keyboard = watchlist_menu(symbols)
        await query.edit_message_text(text, reply_markup=keyboard)

    elif sub_action == "add" and len(parts) >= 4:
        asset = parts[3]
        result = watchlist_service.add_symbol(user_id, chat_id, asset)
        if result == "added":
            text = f"Added {asset} to your watchlist."
        elif result == "duplicate":
            text = f"{asset} is already in your watchlist."
        elif result == "full":
            text = "Watchlist is full. Remove a symbol first."
        else:
            text = f"Failed to add {asset}."
        await query.edit_message_text(text)

    elif sub_action == "remove" and len(parts) >= 3:
        symbol = parts[2]
        result = watchlist_service.remove_symbol(user_id, symbol)
        if result == "removed":
            text = f"Removed {symbol} from your watchlist."
        else:
            text = f"{symbol} is not in your watchlist."
        # Refresh watchlist
        symbols = watchlist_service.get_symbols(user_id)
        keyboard = watchlist_menu(symbols)
        text += "\n\n" + formatter.format_watchlist_from_symbols(symbols)
        await query.edit_message_text(text, reply_markup=keyboard)

    elif sub_action == "do_add" and len(parts) >= 4:
        asset = parts[3]
        result = watchlist_service.add_symbol(user_id, chat_id, asset)
        if result == "added":
            text = f"Added {asset} to your watchlist."
        elif result == "duplicate":
            text = f"{asset} is already in your watchlist."
        else:
            text = "Watchlist is full."
        await query.edit_message_text(text)

    elif sub_action == "do_remove" and len(parts) >= 3:
        symbol = parts[2]
        watchlist_service.remove_symbol(user_id, symbol)
        symbols = watchlist_service.get_symbols(user_id)
        text = formatter.format_watchlist_from_symbols(symbols)
        keyboard = watchlist_menu(symbols)
        await query.edit_message_text(text, reply_markup=keyboard)


async def _handle_search(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Handle search — prompt user to type a symbol."""
    if len(parts) < 2:
        return
    category = parts[1]
    text = (
        "Type a symbol to search.\n\n"
        "Examples:\n"
        "  BTC/USDT, ETHUSDT, AAPL, EUR/USD, ^GSPC\n\n"
        "The symbol will be analyzed automatically."
    )
    # Store search state
    context.user_data["search_category"] = category
    await query.edit_message_text(text)


async def _handle_status(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show system status."""
    formatter: TelegramFormatter = context.bot_data["formatter"]

    # Check database
    db_status = "ok"
    try:
        from umae.storage.database import get_session

        session = get_session()
        session.execute("SELECT 1")
    except Exception as e:
        db_status = f"error: {type(e).__name__}"

    # Check providers
    providers = []
    try:
        analysis_service: AnalysisService = context.bot_data["analysis_service"]
        core = analysis_service._core
        if hasattr(core, "_adapters"):
            for name in core._adapters:
                providers.append(f"  {name}: OK")
    except Exception:
        pass

    from umae.telegram.models import ProviderStatus, SystemStatus

    provider_statuses = [
        ProviderStatus(name=p.strip().split(":")[0].strip(), status="ok") for p in providers
    ]

    status = SystemStatus(
        providers=provider_statuses,
        database_status=db_status,
        analysis_engine_status="ok",
        version="1.0.0",
    )
    text = formatter.format_status(status)
    await query.edit_message_text(text)


async def _handle_help(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help text."""
    formatter: TelegramFormatter = context.bot_data["formatter"]
    text = formatter.format_help()
    await query.edit_message_text(text)


async def _handle_refresh(query, context: ContextTypes.DEFAULT_TYPE, parts: list[str]) -> None:
    """Refresh analysis — re-run the same analysis."""
    if len(parts) < 3:
        return
    category = parts[1]
    asset = parts[2]
    tf = parts[3] if len(parts) >= 4 else None

    if tf:
        await _handle_timeframe(query, context, ["tf", category, asset, tf])
    else:
        await _handle_multi_tf(query, context, ["multi", category, asset])


async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text message during search mode."""
    if not update.message or not update.message.text:
        return

    search_category = context.user_data.get("search_category")
    if not search_category:
        return

    symbol = update.message.text.strip().upper()
    context.user_data.pop("search_category", None)

    # Validate symbol
    from umae.telegram.security import InputValidator

    parsed = InputValidator.parse_analyze_args([symbol])
    if not parsed:
        await update.message.reply_text(
            "Invalid symbol format.\n\nUse: BTCUSDT, BTC/USDT, AAPL, EURUSD, ^GSPC"
        )
        return

    # Analyze
    analysis_service: AnalysisService = context.bot_data["analysis_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]

    await update.message.reply_text(f"Analyzing {parsed}...")

    try:
        result = await analysis_service.analyze(parsed)
        text = formatter.format_analysis(result)
        parts_list = formatter.split_message(text)
        for part in parts_list:
            await update.message.reply_text(part)
    except Exception as e:
        logger.exception("Search analysis failed for %s", symbol)
        text = formatter.format_error(f"Analysis failed: {type(e).__name__}")
        await update.message.reply_text(text)
