"""Security module: rate limiting, deduplication, input validation."""

from __future__ import annotations

import re
import time
from re import Pattern


class UserRateLimiter:
    """Per-user sliding window rate limiter.

    Tracks command timestamps per user and rejects requests
    that exceed the configured rate.
    """

    def __init__(self, max_commands: int = 10, window: int = 60) -> None:
        self.max_commands = max_commands
        self.window = window
        self._user_commands: dict[int, list[float]] = {}

    def is_allowed(self, user_id: int) -> bool:
        """Check if a user is allowed to send a command.

        Records the current timestamp if allowed.
        Returns False if rate limit is exceeded.
        """
        now = time.monotonic()
        commands = self._user_commands.get(user_id, [])
        commands = [t for t in commands if now - t < self.window]

        if len(commands) >= self.max_commands:
            self._user_commands[user_id] = commands
            return False

        commands.append(now)
        self._user_commands[user_id] = commands
        return True

    def remaining(self, user_id: int) -> int:
        """Return remaining allowed commands for a user."""
        now = time.monotonic()
        commands = self._user_commands.get(user_id, [])
        commands = [t for t in commands if now - t < self.window]
        return max(0, self.max_commands - len(commands))

    def reset(self, user_id: int) -> None:
        """Clear rate limit state for a user."""
        self._user_commands.pop(user_id, None)


class UpdateDeduplicator:
    """Prevent processing the same Telegram update twice.

    Telegram can deliver updates more than once during network issues.
    This tracks seen update IDs within a bounded set.
    """

    def __init__(self, max_size: int = 10000) -> None:
        self.max_size = max_size
        self._seen: set[int] = set()

    def is_duplicate(self, update_id: int) -> bool:
        """Return True if this update has already been processed."""
        if update_id in self._seen:
            return True
        self._seen.add(update_id)
        if len(self._seen) > self.max_size:
            self._seen = set(list(self._seen)[-1000:])
        return False


class InputValidator:
    """Validate user input before processing.

    Checks symbol format, command structure, and sanitizes text.
    """

    _SYMBOL_PATTERN: Pattern[str] = re.compile(r"^[A-Z0-9/^_.\-]{1,20}$", re.IGNORECASE)
    _VALID_COMMANDS: frozenset[str] = frozenset(
        {
            "/start",
            "/help",
            "/analyze",
            "/status",
            "/watchlist",
            "/add",
            "/remove",
        }
    )

    @classmethod
    def validate_symbol(cls, symbol: str) -> bool:
        """Check if a symbol string is valid.

        Accepts: BTCUSDT, BTC/USDT, AAPL, EURUSD, ^GSPC, etc.
        Max 20 chars, alphanumeric plus / ^ . _ -
        """
        return bool(cls._SYMBOL_PATTERN.match(symbol))

    @classmethod
    def sanitize_symbol(cls, symbol: str) -> str:
        """Normalize a symbol string.

        Strips whitespace and converts to uppercase.
        """
        return symbol.strip().upper()

    @classmethod
    def is_valid_command(cls, command: str) -> bool:
        """Check if a command is recognized."""
        return command.lower().split()[0] in cls._VALID_COMMANDS

    @classmethod
    def parse_analyze_args(cls, args: list[str]) -> str | None:
        """Extract and validate symbol from /analyze command args.

        Returns the sanitized symbol or None if invalid/missing.
        """
        if not args:
            return None
        symbol = cls.sanitize_symbol(args[0])
        if cls.validate_symbol(symbol):
            return symbol
        return None

    @classmethod
    def truncate(cls, text: str, max_length: int = 4096) -> str:
        """Truncate text to Telegram message length limit."""
        if len(text) <= max_length:
            return text
        return text[: max_length - 20] + "\n\n...(truncated)"
