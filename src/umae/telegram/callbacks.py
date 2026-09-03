"""Telegram callback query handler.

Handles all inline keyboard interactions for the UMAE bot.
Dispatches based on callback data prefixes.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from umae.domain.enums import Timeframe
from umae.telegram.keyboards import (
    analysis_actions,
    category_menu,
    main_menu,
    timeframe_menu,
    watchlist_menu,
)
from umae.telegram.services import TIMEFRAME_MAP

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

    from umae.telegram.formatter import TelegramFormatter
    from umae.telegram.services import AnalysisService, WatchlistService

logger = logging.getLogger(__name__)

# ── Valid callback actions ──────────────────────────────────────
_VALID_ACTIONS = frozenset(
    {
        "cat",
        "asset",
        "tf",
        "multi",
        "back",
        "watch",
        "search",
        "status",
        "help",
        "refresh",
        "noop",
    }
)
_VALID_CATEGORIES = frozenset({"crypto", "stocks", "forex", "indices"})
_VALID_WATCHLIST_SUBS = frozenset({"list", "add", "remove", "do_add", "do_remove"})


# ── Centralized callback payload validation ─────────────────────
@dataclass(frozen=True)
class CallbackPayload:
    """Validated callback payload."""

    action: str
    category: str = ""
    asset: str = ""
    timeframe: str = ""
    sub_action: str = ""
    raw: str = ""

    @property
    def target_tf(self) -> Timeframe | None:
        """Parse timeframe string to Timeframe enum, or None."""
        if not self.timeframe:
            return None
        return TIMEFRAME_MAP.get(self.timeframe)

    @property
    def is_valid(self) -> bool:
        """Check if the payload passed validation."""
        return self.action != ""

    @classmethod
    def parse(cls, data: str) -> CallbackPayload | None:
        """Parse and validate callback data string.

        Returns a validated CallbackPayload or None if invalid.
        """
        if not data:
            return None

        parts = data.split(":")
        action = parts[0]

        if action not in _VALID_ACTIONS:
            logger.debug("Invalid callback action: %s", action)
            return None

        if action == "noop":
            return cls(action="noop", raw=data)

        if action == "status":
            return cls(action="status", raw=data)

        if action == "help":
            return cls(action="help", raw=data)

        if action == "cat":
            if len(parts) < 2 or parts[1] not in _VALID_CATEGORIES:
                logger.debug("Invalid cat callback: %s", data)
                return None
            return cls(action="cat", category=parts[1], raw=data)

        if action == "asset":
            if len(parts) < 3:
                logger.debug("Invalid asset callback: %s", data)
                return None
            return cls(action="asset", category=parts[1], asset=parts[2], raw=data)

        if action == "tf":
            if len(parts) < 4:
                logger.debug("Invalid tf callback: %s", data)
                return None
            if parts[3] not in TIMEFRAME_MAP:
                logger.debug("Invalid timeframe in callback: %s", parts[3])
                return None
            return cls(
                action="tf",
                category=parts[1],
                asset=parts[2],
                timeframe=parts[3],
                raw=data,
            )

        if action == "multi":
            if len(parts) < 3:
                logger.debug("Invalid multi callback: %s", data)
                return None
            return cls(action="multi", category=parts[1], asset=parts[2], raw=data)

        if action == "back":
            if len(parts) < 2:
                return None
            return cls(action="back", sub_action=parts[1], raw=data)

        if action == "watch":
            if len(parts) < 2:
                return None
            sub = parts[1]
            if sub not in _VALID_WATCHLIST_SUBS:
                logger.debug("Invalid watch sub_action: %s", sub)
                return None
            return cls(
                action="watch",
                sub_action=sub,
                category=parts[2] if len(parts) > 2 else "",
                asset=parts[3] if len(parts) > 3 else "",
                raw=data,
            )

        if action == "search":
            if len(parts) < 2:
                return None
            return cls(action="search", category=parts[1], raw=data)

        if action == "refresh":
            if len(parts) < 3:
                return None
            return cls(
                action="refresh",
                category=parts[1],
                asset=parts[2],
                timeframe=parts[3] if len(parts) > 3 else "",
                raw=data,
            )

        return None


# ── Callback rate limiting ──────────────────────────────────────
_EXPENSIVE_ACTIONS = frozenset({"tf", "multi", "refresh"})


def _is_expensive_callback(payload: CallbackPayload) -> bool:
    """Check if a callback triggers expensive analysis."""
    return payload.action in _EXPENSIVE_ACTIONS or (
        payload.action == "watch" and payload.sub_action == "list"
    )


# ── Main handler ────────────────────────────────────────────────


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route all callback queries to the appropriate handler."""
    query = update.callback_query
    if not query or not query.data:
        return

    # Parse and validate callback payload
    payload = CallbackPayload.parse(query.data)
    if payload is None:
        # Invalid callback — answer safely and return
        with contextlib.suppress(Exception):
            await query.answer("Invalid action.", show_alert=False)
        return

    # Answer callback early, but resiliently (stale callbacks)
    with contextlib.suppress(Exception):
        await query.answer()

    # Rate-limit expensive callbacks
    if _is_expensive_callback(payload):
        rate_limiter = context.bot_data.get("rate_limiter")
        user_id = query.from_user.id if query.from_user else None
        if rate_limiter and user_id and not rate_limiter.is_allowed(user_id):
            text = "Rate limit exceeded. Please wait before requesting again."
            with contextlib.suppress(Exception):
                await query.edit_message_text(text)
            return

    try:
        action = payload.action

        if action == "cat":
            await _handle_category(query, context, payload)
        elif action == "asset":
            await _handle_asset(query, context, payload)
        elif action == "tf":
            await _handle_timeframe(query, context, payload)
        elif action == "multi":
            await _handle_multi_tf(query, context, payload)
        elif action == "back":
            await _handle_back(query, context, payload)
        elif action == "watch":
            await _handle_watchlist(query, context, payload)
        elif action == "search":
            await _handle_search(query, context, payload)
        elif action == "status":
            await _handle_status(query, context)
        elif action == "help":
            await _handle_help(query, context)
        elif action == "refresh":
            await _handle_refresh(query, context, payload)
        elif action == "noop":
            pass
        else:
            logger.warning("Unknown callback action: %s", action)

    except Exception as e:
        logger.exception("Callback handling failed for %s", payload.raw)
        with contextlib.suppress(Exception):
            await query.edit_message_text(f"Error: {type(e).__name__}\n\nPlease try again.")


async def _handle_category(
    query, context: ContextTypes.DEFAULT_TYPE, payload: CallbackPayload
) -> None:
    """Show assets for a category."""
    text = f"Select an asset from {payload.category.title()}:"
    keyboard = category_menu(payload.category)
    await query.edit_message_text(text, reply_markup=keyboard)


async def _handle_asset(
    query, context: ContextTypes.DEFAULT_TYPE, payload: CallbackPayload
) -> None:
    """Show timeframe selection for an asset."""
    text = f"Select timeframe for {payload.asset}:"
    keyboard = timeframe_menu(payload.category, payload.asset)
    await query.edit_message_text(text, reply_markup=keyboard)


async def _handle_timeframe(
    query, context: ContextTypes.DEFAULT_TYPE, payload: CallbackPayload
) -> None:
    """Run single-timeframe analysis with target_tf passed to core."""
    text = f"Analyzing {payload.asset} ({payload.timeframe})..."
    await query.edit_message_text(text)

    analysis_service: AnalysisService = context.bot_data["analysis_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]

    try:
        target_tf = payload.target_tf
        result = await analysis_service.analyze(
            payload.asset,
            target_timeframe=target_tf,
            category=payload.category,
        )
        text = formatter.format_analysis_single_tf(result, payload.timeframe)
        keyboard = analysis_actions(payload.category, payload.asset, payload.timeframe)
        await query.edit_message_text(text, reply_markup=keyboard)
    except Exception as e:
        from umae.interfaces.base_adapter import ProviderError

        if isinstance(e, ProviderError):
            text = formatter.format_provider_error(
                symbol=payload.asset,
                category=e.category,
                message=str(e),
                provider=e.provider,
            )
        else:
            logger.exception("Analysis failed for %s %s", payload.asset, payload.timeframe)
            text = formatter.format_error(f"Analysis failed: {type(e).__name__}")
        await query.edit_message_text(text)


async def _handle_multi_tf(
    query, context: ContextTypes.DEFAULT_TYPE, payload: CallbackPayload
) -> None:
    """Run multi-timeframe analysis."""
    text = f"Running multi-TF analysis for {payload.asset}..."
    await query.edit_message_text(text)

    analysis_service: AnalysisService = context.bot_data["analysis_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]

    try:
        result = await analysis_service.analyze(
            payload.asset,
            category=payload.category,
        )
        text = formatter.format_analysis(result)
        keyboard = analysis_actions(payload.category, payload.asset)
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
                symbol=payload.asset,
                category=e.category,
                message=str(e),
                provider=e.provider,
            )
        else:
            logger.exception("Multi-TF analysis failed for %s", payload.asset)
            text = formatter.format_error(f"Analysis failed: {type(e).__name__}")
        await query.edit_message_text(text)


async def _handle_back(query, context: ContextTypes.DEFAULT_TYPE, payload: CallbackPayload) -> None:
    """Handle back navigation."""
    target = payload.sub_action
    parts = payload.raw.split(":")

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


async def _handle_watchlist(
    query, context: ContextTypes.DEFAULT_TYPE, payload: CallbackPayload
) -> None:
    """Handle watchlist operations."""
    sub_action = payload.sub_action
    watchlist_service: WatchlistService = context.bot_data["watchlist_service"]
    formatter: TelegramFormatter = context.bot_data["formatter"]
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if sub_action == "list":
        symbols = watchlist_service.get_symbols(user_id)
        text = formatter.format_watchlist_from_symbols(symbols)
        keyboard = watchlist_menu(symbols)
        await query.edit_message_text(text, reply_markup=keyboard)

    elif sub_action == "add" and payload.asset:
        result = watchlist_service.add_symbol(user_id, chat_id, payload.asset)
        if result == "added":
            text = f"Added {payload.asset} to your watchlist."
        elif result == "duplicate":
            text = f"{payload.asset} is already in your watchlist."
        elif result == "full":
            text = "Watchlist is full. Remove a symbol first."
        else:
            text = f"Failed to add {payload.asset}."
        await query.edit_message_text(text)

    elif sub_action == "remove":
        symbol = payload.category  # repurposed field for remove
        if not symbol:
            return
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

    elif sub_action == "do_add" and payload.asset:
        result = watchlist_service.add_symbol(user_id, chat_id, payload.asset)
        if result == "added":
            text = f"Added {payload.asset} to your watchlist."
        elif result == "duplicate":
            text = f"{payload.asset} is already in your watchlist."
        else:
            text = "Watchlist is full."
        await query.edit_message_text(text)

    elif sub_action == "do_remove":
        symbol = payload.category  # repurposed field for remove
        if not symbol:
            return
        watchlist_service.remove_symbol(user_id, symbol)
        symbols = watchlist_service.get_symbols(user_id)
        text = formatter.format_watchlist_from_symbols(symbols)
        keyboard = watchlist_menu(symbols)
        await query.edit_message_text(text, reply_markup=keyboard)


async def _handle_search(
    query, context: ContextTypes.DEFAULT_TYPE, payload: CallbackPayload
) -> None:
    """Handle search — prompt user to type a symbol."""
    text = (
        "Type a symbol to search.\n\n"
        "Examples:\n"
        "  BTC/USDT, ETHUSDT, AAPL, EUR/USD, ^GSPC\n\n"
        "The symbol will be analyzed automatically."
    )
    # Store search state
    context.user_data["search_category"] = payload.category
    await query.edit_message_text(text)


async def _handle_status(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show system status using unified health check."""
    formatter: TelegramFormatter = context.bot_data["formatter"]

    # Check database
    db_status = "ok"
    try:
        from umae.storage.database import get_session

        session = get_session()
        session.execute("SELECT 1")
    except Exception as e:
        db_status = f"error: {type(e).__name__}"

    # Check providers using application-level health check
    providers = []
    analysis_service: AnalysisService = context.bot_data["analysis_service"]
    core = analysis_service._core

    for name, adapter in core._adapters.items():
        try:
            from datetime import timedelta

            now = datetime.now(UTC)
            start = (now - timedelta(hours=1)).isoformat()
            end = now.isoformat()
            cs = await adapter.fetch_candles("BTCUSDT", Timeframe.H1, start, end)
            if cs.candles:
                from umae.telegram.models import ProviderStatus

                providers.append(ProviderStatus(name=name, status="ok"))
            else:
                from umae.telegram.models import ProviderStatus

                providers.append(
                    ProviderStatus(name=name, status="warning", error_message="No data returned")
                )
        except Exception as e:
            from umae.interfaces.base_adapter import ProviderError
            from umae.telegram.models import ProviderStatus

            if isinstance(e, ProviderError) and e.category == "DATA_PROVIDER_TLS_ERROR":
                providers.append(
                    ProviderStatus(
                        name=name, status="error", error_message=f"TLS error: {e.category}"
                    )
                )
            else:
                providers.append(
                    ProviderStatus(
                        name=name, status="error", error_message=f"{type(e).__name__}: {e}"
                    )
                )

    from umae.telegram.models import SystemStatus

    status = SystemStatus(
        providers=providers,
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


async def _handle_refresh(
    query, context: ContextTypes.DEFAULT_TYPE, payload: CallbackPayload
) -> None:
    """Refresh analysis — re-run the same analysis using standardized refresh callbacks."""
    if payload.timeframe:
        await _handle_timeframe(query, context, payload)
    else:
        # Build a multi payload from refresh payload
        multi_payload = CallbackPayload(
            action="multi",
            category=payload.category,
            asset=payload.asset,
            raw=payload.raw,
        )
        await _handle_multi_tf(query, context, multi_payload)


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
