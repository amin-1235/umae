"""Telegram response formatter.

Formats typed response objects into Telegram-compatible messages.
No analysis logic lives here — only layout and emoji decoration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from umae.telegram.models import (
        AnalysisResult,
        DataQuality,
        SystemStatus,
        WatchlistResult,
    )

_MAX_MESSAGE_LENGTH = 4096


class TelegramFormatter:
    """Format UMAE response objects for Telegram display."""

    def format_analysis(self, result: AnalysisResult) -> str:
        """Format a full analysis result into a readable message."""
        lines: list[str] = []

        lines.append("═" * 31)
        lines.append("\U0001f4ca UMAE ANALYSIS")
        lines.append("═" * 31)
        lines.append("")

        # Asset info
        lines.append(f"Asset: {result.symbol}")
        if result.target_timeframe:
            lines.append(f"Target TF: {result.target_timeframe}")
            lines.append("Mode: SINGLE-TF")
        else:
            lines.append("Mode: MULTI-TF")
        lines.append(f"Exchange: {result.exchange}")
        lines.append("")

        # Price and data
        lines.append(f"Price: ${result.price:,.2f}")
        lines.append(f"Data Quality: {result.data_quality.state}")
        if result.data_quality.freshness_seconds > 0:
            secs = result.data_quality.freshness_seconds
            if secs < 60:
                lines.append(f"  Age: {secs}s")
            elif secs < 3600:
                lines.append(f"  Age: {secs // 60}m")
            elif secs < 86400:
                lines.append(f"  Age: {secs // 3600}h")
            else:
                lines.append(f"  Age: {secs // 86400}d")
        lines.append("")

        # Signal
        lines.append("─" * 31)
        lines.append("\U0001f3af SIGNAL")
        lines.append("─" * 31)
        signal_emoji = self._signal_emoji(result.signal)
        lines.append(f"Signal: {signal_emoji} {result.signal.upper()}")
        lines.append(f"Raw Score: {result.signal_score:+.2f}")
        if result.calibrated_confidence is not None:
            lines.append(f"Calibrated Confidence: {result.calibrated_confidence:.0%}")
        else:
            lines.append("Calibrated Confidence: N/A")
        lines.append("")

        # Score breakdown
        if result.score_breakdown:
            lines.append("─" * 31)
            lines.append("\U0001f4ca SCORE BREAKDOWN")
            lines.append("─" * 31)
            sb = result.score_breakdown
            lines.append(f"  htf_bias:        {sb.htf_bias:+.2f}")
            lines.append(f"  trend_alignment: {sb.trend_alignment:+.2f}")
            lines.append(f"  momentum:        {sb.momentum:+.2f}")
            lines.append(f"  volume:          {sb.volume:+.2f}")
            lines.append(f"  structure:       {sb.structure:+.2f}")
            lines.append(f"  regime_adj:      {sb.regime_adjustment:+.2f}")
            lines.append("  ─────────────────")
            lines.append(f"  total:           {sb.total:+.2f}")
            lines.append("")

        # Regime
        lines.append("─" * 31)
        lines.append("\U0001f4c8 REGIME")
        lines.append("─" * 31)
        lines.append(f"Regime: {result.regime}")
        lines.append(f"Confidence: {result.regime_confidence:.0%}")
        lines.append("")

        # Features
        if result.feature_summary:
            lines.append("─" * 31)
            lines.append("\U0001f4ca FEATURES")
            lines.append("─" * 31)
            fs = result.feature_summary
            lines.append(f"Trend:      {self._feature_emoji(fs.trend)} {fs.trend}")
            lines.append(f"Momentum:   {self._feature_emoji(fs.momentum)} {fs.momentum}")
            lines.append(f"Volume:     {self._volume_emoji(fs.volume)} {fs.volume}")
            lines.append(f"Volatility: {fs.volatility}")
            lines.append(f"Structure:  {fs.structure}")
            lines.append("")

        # Contributors
        if result.contributors:
            lines.append("─" * 31)
            lines.append("CONTRIBUTORS")
            lines.append("─" * 31)
            for c in result.contributors[:8]:
                lines.append(f"  {c}")
            lines.append("")

        # Context TFs
        if result.timeframe_results:
            lines.append("─" * 31)
            lines.append("\u23f1 TIMEFRAME ANALYSIS")
            lines.append("─" * 31)
            lines.append("TF    | Signal | Score | Regime")
            lines.append("------+--------+-------+--------")
            for tf in result.timeframe_results[:13]:
                emoji = self._signal_emoji(tf.signal)
                lines.append(f"{tf.timeframe:<5} | {emoji:^6} | {tf.score:>+5.2f} | {tf.regime}")
            lines.append("")

        # Reason codes
        if result.reason_codes:
            lines.append("─" * 31)
            lines.append("\U0001f4dd REASONS")
            lines.append("─" * 31)
            for reason in result.reason_codes[:8]:
                lines.append(f"  {reason}")
            lines.append("")

        # Warnings
        if result.warnings:
            lines.append("─" * 31)
            lines.append("\u26a0 WARNINGS")
            lines.append("─" * 31)
            for warning in result.warnings[:5]:
                lines.append(f"  \u2022 {warning}")
            lines.append("")

        # Meta
        lines.append("─" * 31)
        lines.append("\u2139\ufe0f META")
        lines.append("─" * 31)
        lines.append(f"Model: {result.model_version}")
        lines.append(f"Features: {result.feature_version}")
        lines.append(f"Data: {result.data_version}")
        lines.append(f"Provider: {result.provider}")
        lines.append("")

        lines.append("═" * 31)
        lines.append("\u26a0 This is analysis, not advice.")
        lines.append("═" * 31)

        return "\n".join(lines)

    def format_status(self, result: SystemStatus) -> str:
        """Format system status into a readable message."""
        lines: list[str] = []

        lines.append("═" * 31)
        lines.append("\U0001f527 SYSTEM STATUS")
        lines.append("═" * 31)
        lines.append("")

        lines.append("Providers:")
        for p in result.providers:
            if p.status == "ok":
                icon = "\u2705"
            elif p.status == "error":
                icon = "\u274c"
            else:
                icon = "\u26a0\ufe0f"
            lines.append(f"  {p.name:<12} {icon} {p.status.upper()}")
        lines.append("")

        db_icon = "\u2705" if result.database_status == "ok" else "\u274c"
        engine_icon = "\u2705" if result.analysis_engine_status == "ok" else "\u274c"
        lines.append(f"Database:       {db_icon} {result.database_status.upper()}")
        lines.append(f"Analysis Engine: {engine_icon} {result.analysis_engine_status.upper()}")
        lines.append(f"Last Update:    {result.last_update or 'Never'}")
        lines.append("")

        lines.append(f"Active Users:   {result.active_users}")
        lines.append(f"Symbols:        {result.symbols_tracked}")
        lines.append("")

        if result.warnings:
            lines.append("Warnings:")
            for w in result.warnings[:3]:
                lines.append(f"  \u2022 {w}")
            lines.append("")

        days = result.uptime_seconds // 86400
        hours = (result.uptime_seconds % 86400) // 3600
        minutes = (result.uptime_seconds % 3600) // 60
        lines.append(f"Uptime: {days}d {hours}h {minutes}m")
        lines.append(f"Version: {result.version}")
        lines.append("═" * 31)

        return "\n".join(lines)

    def format_watchlist(self, result: WatchlistResult) -> str:
        """Format watchlist into a readable message."""
        lines: list[str] = []

        if not result.items:
            lines.append("Your watchlist is empty.")
            lines.append("")
            lines.append("Use /add <symbol> to add an asset.")
            return "\n".join(lines)

        lines.append("Your Watchlist:")
        lines.append("")

        for i, item in enumerate(result.items, 1):
            emoji = self._signal_emoji(item.signal)
            price_str = f"${item.price:,.2f}" if item.price is not None else "N/A"
            if item.signal == "unavailable":
                lines.append(
                    f"{i}. {item.symbol} ({item.exchange or 'N/A'}) - \u26a0\ufe0f DATA UNAVAILABLE"
                )
            else:
                lines.append(
                    f"{i}. {item.symbol} ({item.exchange}) - "
                    f"{emoji} {item.signal.upper()} {item.score:+.2f} @ {price_str}"
                )

        lines.append("")
        lines.append("Use /add <symbol> to add")
        lines.append("Use /remove <symbol> to remove")

        return "\n".join(lines)

    def format_help(self) -> str:
        """Format help text."""
        return (
            "UMAE Commands:\n"
            "\n"
            "/analyze <symbol>\n"
            "  Full multi-timeframe analysis\n"
            "  Example: /analyze BTCUSDT\n"
            "\n"
            "/status\n"
            "  Show system health and data status\n"
            "\n"
            "/watchlist\n"
            "  Show your watchlist\n"
            "\n"
            "/add <symbol>\n"
            "  Add symbol to watchlist\n"
            "\n"
            "/remove <symbol>\n"
            "  Remove from watchlist\n"
            "\n"
            "Supported Assets:\n"
            "  Crypto: BTC, ETH, SOL, BNB, etc.\n"
            "  Stocks: AAPL, GOOGL, MSFT, etc.\n"
            "  Forex: EURUSD, GBPUSD, etc.\n"
            "  Indices: ^GSPC, ^DJI, etc.\n"
            "\n"
            "Timeframes Analyzed:\n"
            "  1m, 3m, 5m, 15m, 20m, 30m,\n"
            "  1h, 2h, 4h, 6h, 12h, 1D, 1W\n"
            "\n"
            "Disclaimer: Analysis only, not trading advice."
        )

    def format_error(self, error: str) -> str:
        """Format an error message for display."""
        return f"\u274c Error\n\n{error}\n\nUse /help for available commands."

    def format_provider_error(self, symbol: str, category: str, message: str, provider: str) -> str:
        """Format a provider error with clear user-facing message."""
        lines = [
            "\u26a0\ufe0f DATA UNAVAILABLE",
            "",
            f"Asset: {symbol}",
            f"Provider: {provider}",
            "",
        ]

        if category == "DATA_PROVIDER_TLS_ERROR":
            lines.extend(
                [
                    "Unable to securely connect to the market data provider.",
                    "",
                    "Reason: TLS certificate verification failed.",
                    "This may be caused by:",
                    "  - ISP network interception",
                    "  - Corporate firewall/proxy",
                    "  - VPN configuration",
                    "",
                    "No market signal was generated.",
                ]
            )
        elif category == "DATA_PROVIDER_UNAVAILABLE":
            lines.extend(
                [
                    "Unable to connect to the market data provider.",
                    "",
                    f"Reason: {message}",
                    "",
                    "No market signal was generated.",
                ]
            )
        elif category == "DATA_PROVIDER_TIMEOUT":
            lines.extend(
                [
                    "Request to market data provider timed out.",
                    "",
                    "No market signal was generated.",
                ]
            )
        elif category == "SYMBOL_NOT_FOUND":
            lines.extend(
                [
                    f"Symbol '{symbol}' was not found on {provider}.",
                    "",
                    "Check the symbol and try again.",
                    "Examples: BTCUSDT, ETH/USDT, AAPL",
                ]
            )
        else:
            lines.extend(
                [
                    f"Provider error: {message}",
                    "",
                    "No market signal was generated.",
                ]
            )

        lines.append("")
        lines.append("\u26a0 This is analysis, not advice.")
        return "\n".join(lines)

    def format_welcome(self) -> str:
        """Format welcome message for /start."""
        return "\U0001f4ca UMAE\nUniversal Market Analysis Engine\n\nSelect a category to begin:"

    def format_watchlist_from_symbols(self, symbols: list[str]) -> str:
        """Format a simple watchlist from symbol list."""
        if not symbols:
            return "Your watchlist is empty.\n\nUse the menu to add assets."
        lines = ["Your Watchlist:"]
        for i, symbol in enumerate(symbols, 1):
            lines.append(f"  {i}. {symbol}")
        lines.append("")
        lines.append("Select an asset to analyze.")
        return "\n".join(lines)

    def format_analysis_single_tf(self, result: AnalysisResult, target_tf: str) -> str:
        """Format analysis for a single target timeframe."""
        lines: list[str] = []

        lines.append("═" * 31)
        lines.append("\U0001f4ca UMAE ANALYSIS")
        lines.append("═" * 31)
        lines.append("")
        lines.append(f"Asset: {result.symbol}")
        # Use result's target_timeframe if available, otherwise the parameter
        display_tf = result.target_timeframe or target_tf
        lines.append(f"Target TF: {display_tf}")
        lines.append("Mode: SINGLE-TF")
        lines.append(f"Exchange: {result.exchange}")
        lines.append("")
        lines.append(f"Price: ${result.price:,.2f}")
        lines.append(f"Data Quality: {result.data_quality.state}")
        lines.append("")

        # Signal
        lines.append("─" * 31)
        lines.append("\U0001f3af SIGNAL")
        lines.append("─" * 31)
        emoji = self._signal_emoji(result.signal)
        lines.append(f"Signal: {emoji} {result.signal.upper()}")
        lines.append(f"Raw Score: {result.signal_score:+.2f}")
        if result.calibrated_confidence is not None:
            lines.append(f"Calibrated Confidence: {result.calibrated_confidence:.0%}")
        else:
            lines.append("Calibrated Confidence: N/A")
        lines.append("")

        # Score breakdown
        if result.score_breakdown:
            lines.append("─" * 31)
            lines.append("\U0001f4ca SCORE BREAKDOWN")
            lines.append("─" * 31)
            sb = result.score_breakdown
            lines.append(f"  htf_bias:        {sb.htf_bias:+.2f}")
            lines.append(f"  trend_alignment: {sb.trend_alignment:+.2f}")
            lines.append(f"  momentum:        {sb.momentum:+.2f}")
            lines.append(f"  volume:          {sb.volume:+.2f}")
            lines.append(f"  structure:       {sb.structure:+.2f}")
            lines.append(f"  regime_adj:      {sb.regime_adjustment:+.2f}")
            lines.append("  ─────────────────")
            lines.append(f"  total:           {sb.total:+.2f}")
            lines.append("")

        # Regime
        lines.append(f"Regime: {result.regime}")
        lines.append(f"Confidence: {result.regime_confidence:.0%}")
        lines.append("")

        # Features
        if result.feature_summary:
            lines.append("─" * 31)
            lines.append("\U0001f4ca FEATURES")
            lines.append("─" * 31)
            fs = result.feature_summary
            lines.append(f"Trend:      {self._feature_emoji(fs.trend)} {fs.trend}")
            lines.append(f"Momentum:   {self._feature_emoji(fs.momentum)} {fs.momentum}")
            lines.append(f"Volume:     {self._volume_emoji(fs.volume)} {fs.volume}")
            lines.append(f"Volatility: {fs.volatility}")
            lines.append(f"Structure:  {fs.structure}")
            lines.append("")

        # Contributors
        if result.contributors:
            lines.append("─" * 31)
            lines.append("CONTRIBUTORS")
            lines.append("─" * 31)
            for c in result.contributors[:8]:
                lines.append(f"  {c}")
            lines.append("")

        # Context TFs
        if result.timeframe_results:
            lines.append("─" * 31)
            lines.append("\u23f1 CONTEXT")
            lines.append("─" * 31)
            lines.append("TF    | Signal | Score | Regime")
            lines.append("------+--------+-------+--------")
            for tf in result.timeframe_results[:7]:
                emoji = self._signal_emoji(tf.signal)
                lines.append(f"{tf.timeframe:<5} | {emoji:^6} | {tf.score:>+5.2f} | {tf.regime}")
            lines.append("")

        # Reasons
        if result.reason_codes:
            lines.append("─" * 31)
            lines.append("\U0001f4dd REASONS")
            lines.append("─" * 31)
            for reason in result.reason_codes[:5]:
                lines.append(f"  {reason}")
            lines.append("")

        # Warnings
        if result.warnings:
            lines.append("─" * 31)
            lines.append("\u26a0 WARNINGS")
            lines.append("─" * 31)
            for w in result.warnings[:3]:
                lines.append(f"  \u2022 {w}")
            lines.append("")

        lines.append("─" * 31)
        lines.append("\u2139\ufe0f META")
        lines.append("─" * 31)
        lines.append(f"Model: {result.model_version}")
        lines.append(f"Features: {result.feature_version}")
        lines.append(f"Data: {result.data_version}")
        lines.append("")

        lines.append("═" * 31)
        lines.append("\u26a0 This is analysis, not advice.")
        lines.append("═" * 31)

        return "\n".join(lines)

    def split_message(self, text: str) -> list[str]:
        """Split a message that exceeds Telegram's length limit.

        Splits on newline boundaries when possible.
        Falls back to hard character split for single very long lines.
        """
        if len(text) <= _MAX_MESSAGE_LENGTH:
            return [text]

        parts: list[str] = []
        current_lines: list[str] = []
        current_length = 0
        limit = _MAX_MESSAGE_LENGTH - 50  # leave buffer

        for line in text.split("\n"):
            line_len = len(line) + 1  # +1 for \n

            if line_len > limit:
                # Line itself is too long — flush current buffer
                if current_lines:
                    parts.append("\n".join(current_lines))
                    current_lines = []
                    current_length = 0
                # Hard-split the long line
                while len(line) > limit:
                    parts.append(line[:limit])
                    line = line[limit:]
                if line:
                    current_lines = [line]
                    current_length = len(line) + 1
            elif current_length + line_len > limit:
                parts.append("\n".join(current_lines))
                current_lines = [line]
                current_length = line_len
            else:
                current_lines.append(line)
                current_length += line_len

        if current_lines:
            parts.append("\n".join(current_lines))

        return parts

    @staticmethod
    def _format_freshness(quality: DataQuality) -> str:
        """Format data freshness from seconds."""
        seconds = quality.freshness_seconds
        if seconds < 60:
            return f"Fresh ({seconds}s ago)"
        if seconds < 3600:
            return f"Fresh ({seconds // 60}m ago)"
        if seconds < 86400:
            return f"Stale ({seconds // 3600}h ago)"
        return f"Very stale ({seconds // 86400}d ago)"

    @staticmethod
    def _signal_emoji(signal: str) -> str:
        """Map signal value to emoji."""
        return {
            "up": "\U0001f7e2",
            "down": "\U0001f534",
            "neutral": "\U0001f7e1",
            "no_signal": "\u26aa",
            "unavailable": "\u26a0\ufe0f",
        }.get(signal, "\u26aa")

    @staticmethod
    def _feature_emoji(value: str) -> str:
        """Map feature value to emoji."""
        return {
            "bullish": "\U0001f7e2",
            "bearish": "\U0001f534",
            "neutral": "\U0001f7e1",
        }.get(value, "\u26aa")

    @staticmethod
    def _volume_emoji(value: str) -> str:
        """Map volume value to emoji."""
        return {
            "strong": "\U0001f50a",
            "weak": "\U0001f507",
            "normal": "\U0001f508",
        }.get(value, "\u26aa")
