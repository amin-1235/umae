"""Telegram inline keyboard builders.

All keyboard layouts for the UMAE interactive UX.
Keyboards are pure functions that return InlineKeyboardMarkup objects.
No business logic lives here.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ── Callback data prefixes ──────────────────────────────────────
# Format: action:param1:param2
# Actions: cat, asset, tf, multi, back, refresh, watch, unwatch, search, help, status, overview

# ── Main Menu ───────────────────────────────────────────────────


def main_menu() -> InlineKeyboardMarkup:
    """Build the main /start menu."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Crypto", callback_data="cat:crypto"),
                InlineKeyboardButton("Stocks", callback_data="cat:stocks"),
            ],
            [
                InlineKeyboardButton("Forex", callback_data="cat:forex"),
                InlineKeyboardButton("Indices", callback_data="cat:indices"),
            ],
            [
                InlineKeyboardButton("Watchlist", callback_data="watch:list"),
            ],
            [
                InlineKeyboardButton("Status", callback_data="status"),
                InlineKeyboardButton("Help", callback_data="help"),
            ],
        ]
    )


# ── Category Menu ───────────────────────────────────────────────

_CRYPTO_ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
_STOCK_ASSETS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
_FOREX_ASSETS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF"]
_INDEX_ASSETS = ["^GSPC", "^NDX", "^DJI", "^RUT", "^VIX"]

_ASSET_MAP = {
    "crypto": _CRYPTO_ASSETS,
    "stocks": _STOCK_ASSETS,
    "forex": _FOREX_ASSETS,
    "indices": _INDEX_ASSETS,
}


def category_menu(category: str) -> InlineKeyboardMarkup:
    """Build asset selection menu for a category."""
    assets = _ASSET_MAP.get(category, [])
    buttons: list[list[InlineKeyboardButton]] = []

    for asset in assets:
        buttons.append(
            [
                InlineKeyboardButton(asset, callback_data=f"asset:{category}:{asset}"),
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton("Search", callback_data=f"search:{category}"),
        ]
    )
    buttons.append(
        [
            InlineKeyboardButton("Back", callback_data="back:main"),
        ]
    )

    return InlineKeyboardMarkup(buttons)


# ── Timeframe Menu ──────────────────────────────────────────────

_ALL_TIMEFRAMES = ["1m", "3m", "5m", "15m", "20m", "30m", "1h", "2h", "4h", "6h", "12h", "1D", "1W"]


def timeframe_menu(category: str, asset: str) -> InlineKeyboardMarkup:
    """Build timeframe selection menu for an asset."""
    buttons: list[list[InlineKeyboardButton]] = []

    # Row 1: LTF
    buttons.append(
        [
            InlineKeyboardButton("1m", callback_data=f"tf:{category}:{asset}:1m"),
            InlineKeyboardButton("3m", callback_data=f"tf:{category}:{asset}:3m"),
            InlineKeyboardButton("5m", callback_data=f"tf:{category}:{asset}:5m"),
        ]
    )
    # Row 2: MTF lower
    buttons.append(
        [
            InlineKeyboardButton("15m", callback_data=f"tf:{category}:{asset}:15m"),
            InlineKeyboardButton("20m", callback_data=f"tf:{category}:{asset}:20m"),
            InlineKeyboardButton("30m", callback_data=f"tf:{category}:{asset}:30m"),
        ]
    )
    # Row 3: MTF upper
    buttons.append(
        [
            InlineKeyboardButton("1h", callback_data=f"tf:{category}:{asset}:1h"),
            InlineKeyboardButton("2h", callback_data=f"tf:{category}:{asset}:2h"),
            InlineKeyboardButton("4h", callback_data=f"tf:{category}:{asset}:4h"),
        ]
    )
    # Row 4: HTF
    buttons.append(
        [
            InlineKeyboardButton("6h", callback_data=f"tf:{category}:{asset}:6h"),
            InlineKeyboardButton("12h", callback_data=f"tf:{category}:{asset}:12h"),
        ]
    )
    # Row 5: Daily/Weekly
    buttons.append(
        [
            InlineKeyboardButton("1D", callback_data=f"tf:{category}:{asset}:1D"),
            InlineKeyboardButton("1W", callback_data=f"tf:{category}:{asset}:1W"),
        ]
    )
    # Row 6: Multi-TF
    buttons.append(
        [
            InlineKeyboardButton("Multi-TF Analysis", callback_data=f"multi:{category}:{asset}"),
        ]
    )
    # Row 7: Back
    buttons.append(
        [
            InlineKeyboardButton("Back", callback_data=f"back:cat:{category}"),
        ]
    )

    return InlineKeyboardMarkup(buttons)


# ── Analysis Action Buttons ─────────────────────────────────────


def analysis_actions(category: str, asset: str, tf: str | None = None) -> InlineKeyboardMarkup:
    """Build action buttons shown after an analysis result."""
    if tf:
        refresh_cb = f"tf:{category}:{asset}:{tf}"
        multi_cb = f"multi:{category}:{asset}"
    else:
        refresh_cb = f"multi:{category}:{asset}"
        multi_cb = refresh_cb

    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("Refresh", callback_data=refresh_cb),
        ],
        [
            InlineKeyboardButton("Multi-TF", callback_data=multi_cb),
        ],
        [
            InlineKeyboardButton("Add Watchlist", callback_data=f"watch:add:{category}:{asset}"),
        ],
        [
            InlineKeyboardButton("Back", callback_data=f"back:tf:{category}:{asset}"),
        ],
    ]

    return InlineKeyboardMarkup(buttons)


# ── Watchlist Menu ──────────────────────────────────────────────


def watchlist_menu(symbols: list[str]) -> InlineKeyboardMarkup:
    """Build watchlist display with asset buttons."""
    buttons: list[list[InlineKeyboardButton]] = []

    for symbol in symbols[:20]:
        buttons.append(
            [
                InlineKeyboardButton(f"{symbol}", callback_data=f"asset:watch:{symbol}"),
                InlineKeyboardButton("Remove", callback_data=f"watch:remove:{symbol}"),
            ]
        )

    if not buttons:
        buttons.append(
            [
                InlineKeyboardButton("No assets in watchlist", callback_data="noop"),
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton("Back", callback_data="back:main"),
        ]
    )

    return InlineKeyboardMarkup(buttons)


# ── Watchlist Confirm ───────────────────────────────────────────


def watchlist_confirm(action: str, symbol: str, category: str, asset: str) -> InlineKeyboardMarkup:
    """Build confirmation for watchlist add/remove."""
    if action == "add":
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Confirm Add", callback_data=f"watch:do_add:{category}:{asset}"
                    ),
                    InlineKeyboardButton("Cancel", callback_data=f"back:tf:{category}:{asset}"),
                ],
            ]
        )
    else:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Confirm Remove", callback_data=f"watch:do_remove:{symbol}"
                    ),
                    InlineKeyboardButton("Cancel", callback_data="watch:list"),
                ],
            ]
        )


# ── Search ──────────────────────────────────────────────────────


def search_menu(category: str) -> InlineKeyboardMarkup:
    """Build search prompt menu."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Back", callback_data=f"back:cat:{category}"),
            ],
        ]
    )


# ── Error / Noop ────────────────────────────────────────────────


def noop_keyboard() -> InlineKeyboardMarkup:
    """Empty keyboard for no-op callbacks."""
    return InlineKeyboardMarkup([])
