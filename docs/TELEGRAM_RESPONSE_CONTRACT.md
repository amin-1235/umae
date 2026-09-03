# Universal Market Analysis Engine (UMAE) - Telegram Response Contract

## Overview

This document defines typed response objects used between the analysis engine and Telegram formatter.

## Core Principle

**Telegram formatter receives typed objects, NOT raw engine data.**

```
Analysis Engine → AnalysisResult → TelegramFormatter → Message
```

The formatter has NO access to internal engine state.

## Response Types

### AnalysisResult

The main response from analysis engine.

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass
class TimeframeResult:
    """Result for a single timeframe."""

    timeframe: str  # e.g., "1h", "4h", "1D"
    signal: str  # "up", "down", "neutral", "no_signal"
    score: float  # -1.0 to 1.0
    regime: str  # Market regime
    regime_confidence: float  # 0.0 to 1.0
    trend: str  # "bullish", "bearish", "neutral"
    momentum: str  # "bullish", "bearish", "neutral"
    volume: str  # "strong", "weak", "normal"
    volatility: str  # "high", "low", "normal"
    structure: str  # "breakout", "consolidation", "trending"
    features_used: list[str]  # Features that contributed
    reason_codes: list[str]  # Why this signal


@dataclass
class DataQuality:
    """Data quality information."""

    freshness_seconds: int  # How old is the data
    completeness: float  # 0.0 to 1.0
    candle_count: int  # Number of candles used
    missing_candles: int  # Number of missing candles
    warnings: list[str]  # Data quality warnings


@dataclass
class FeatureSummary:
    """Summary of feature states."""

    trend: str  # "bullish", "bearish", "neutral"
    momentum: str  # "bullish", "bearish", "neutral"
    volume: str  # "strong", "weak", "normal"
    volatility: str  # "high", "low", "normal"
    structure: str  # Market structure state


@dataclass
class AnalysisResult:
    """Complete analysis result for Telegram formatting."""

    # Asset info
    symbol: str
    asset_type: str  # "crypto", "stock", "forex", "index"
    exchange: str
    timestamp: str  # ISO format
    price: Decimal

    # Data quality
    data_quality: DataQuality

    # Timeframe results
    timeframe_results: list[TimeframeResult]

    # Aggregate
    regime: str  # Overall regime
    regime_confidence: float

    # Signal
    signal: str  # "up", "down", "neutral", "no_signal"
    signal_score: float  # -1.0 to 1.0
    calibrated_confidence: float | None  # 0.0 to 1.0 if available

    # Feature summary
    feature_summary: FeatureSummary

    # Explanation
    reason_codes: list[str]  # Top-level reasons
    warnings: list[str]  # Analysis warnings

    # Meta
    model_version: str
    data_version: str

    # Optional
    support_resistance: dict[str, Any] | None = None
    additional_info: dict[str, Any] | None = None
```

### StatusResult

Response for /status command.

```python
@dataclass
class ProviderStatus:
    """Status of a data provider."""

    name: str  # "binance", "yahoo"
    status: str  # "ok", "error", "degraded"
    error_message: str | None = None
    last_success: str | None = None  # ISO timestamp
    data_quality: float | None = None  # 0.0 to 1.0


@dataclass
class SystemStatus:
    """System health status."""

    # Providers
    providers: list[ProviderStatus]

    # Components
    database_status: str  # "ok", "error"
    analysis_engine_status: str  # "ok", "error", "initializing"

    # Timing
    last_update: str | None  # ISO timestamp
    uptime_seconds: int

    # Metrics
    active_users: int
    symbols_tracked: int

    # Errors
    warnings: list[str]
    errors: list[str]

    # Meta
    version: str
```

### WatchlistResult

Response for /watchlist command.

```python
@dataclass
class WatchlistItem:
    """Single item in watchlist."""

    symbol: str
    exchange: str
    signal: str  # "up", "down", "neutral", "no_signal"
    score: float
    price: Decimal | None = None
    last_analyzed: str | None = None  # ISO timestamp


@dataclass
class WatchlistResult:
    """Watchlist response."""

    user_id: int
    items: list[WatchlistItem]
    max_items: int = 50
```

### CommandResult

Generic command response.

```python
@dataclass
class CommandResult:
    """Result from a command execution."""

    success: bool
    message: str
    data: dict[str, Any] | None = None
```

## Formatter Interface

```python
from abc import ABC, abstractmethod


class ResponseFormatter(ABC):
    """Base class for response formatters."""
    
    @abstractmethod
    def format_analysis(self, result: AnalysisResult) -> str:
        """Format analysis result for display."""
        ...
    
    @abstractmethod
    def format_status(self, result: SystemStatus) -> str:
        """Format status result for display."""
        ...
    
    @abstractmethod
    def format_watchlist(self, result: WatchlistResult) -> str:
        """Format watchlist result for display."""
        ...
    
    @abstractmethod
    def format_error(self, error: str) -> str:
        """Format error message."""
        ...
    
    @abstractmethod
    def format_help(self) -> str:
        """Format help text."""
        ...
```

## Telegram Formatter

```python
class TelegramFormatter(ResponseFormatter):
    """Format responses for Telegram."""

    MAX_MESSAGE_LENGTH = 4096

    def format_analysis(self, result: AnalysisResult) -> str:
        """Format analysis result."""
        lines = []

        # Header
        lines.append("═" * 31)
        lines.append(f"📊 ANALYSIS: {result.symbol}")
        lines.append("═" * 31)
        lines.append("")

        # Basic info
        lines.append(f"⏰ {result.timestamp}")
        lines.append(f"💰 Price: ${result.price:,.2f}")
        lines.append(f"📦 Data: {self._format_freshness(result.data_quality)}")
        lines.append("")

        # Regime
        lines.append("─" * 31)
        lines.append("📈 MARKET REGIME")
        lines.append("─" * 31)
        lines.append(f"Regime: {result.regime}")
        lines.append(f"Confidence: {result.regime_confidence:.0%}")
        lines.append("")

        # Timeframe table
        lines.append("─" * 31)
        lines.append("⏱ TIMEFRAME ANALYSIS")
        lines.append("─" * 31)
        lines.append("TF    | Signal | Score | Regime")
        lines.append("------+--------+-------+--------")
        for tf in result.timeframe_results[:7]:  # Limit to 7 for readability
            signal_emoji = self._signal_emoji(tf.signal)
            lines.append(f"{tf.timeframe:<5} | {signal_emoji:^6} | {tf.score:>+5.2f} | {tf.regime}")
        lines.append("")

        # Signal
        lines.append("─" * 31)
        lines.append("🎯 SIGNAL")
        lines.append("─" * 31)
        lines.append(f"Signal: {self._signal_emoji(result.signal)} {result.signal.upper()}")
        lines.append(f"Score: {result.signal_score:+.2f}")
        if result.calibrated_confidence is not None:
            lines.append(f"Confidence: {result.calibrated_confidence:.0%}")
        lines.append("")

        # Reasons
        if result.reason_codes:
            lines.append("─" * 31)
            lines.append("📝 REASONS")
            lines.append("─" * 31)
            for reason in result.reason_codes[:5]:
                lines.append(f"• {reason}")
            lines.append("")

        # Feature summary
        lines.append("─" * 31)
        lines.append("📊 FEATURE SUMMARY")
        lines.append("─" * 31)
        fs = result.feature_summary
        lines.append(f"Trend:     {self._feature_emoji(fs.trend)} {fs.trend}")
        lines.append(f"Momentum:  {self._feature_emoji(fs.momentum)} {fs.momentum}")
        lines.append(f"Volume:    {self._volume_emoji(fs.volume)} {fs.volume}")
        lines.append(f"Volatility: {fs.volatility}")
        lines.append(f"Structure: {fs.structure}")
        lines.append("")

        # Warnings
        if result.warnings:
            lines.append("─" * 31)
            lines.append("⚠ WARNINGS")
            lines.append("─" * 31)
            for warning in result.warnings[:3]:
                lines.append(f"• {warning}")
            lines.append("")

        # Meta
        lines.append("─" * 31)
        lines.append("ℹ META")
        lines.append("─" * 31)
        lines.append(f"Model: {result.model_version}")
        lines.append(f"Data: {result.data_version}")
        lines.append("")

        # Footer
        lines.append("═" * 31)
        lines.append("⚠ This is analysis, not advice.")
        lines.append("═" * 31)

        return "\n".join(lines)

    def format_status(self, result: SystemStatus) -> str:
        """Format status result."""
        lines = []

        lines.append("═" * 31)
        lines.append("🔧 SYSTEM STATUS")
        lines.append("═" * 31)
        lines.append("")

        # Providers
        lines.append("Providers:")
        for p in result.providers:
            status_emoji = "✅" if p.status == "ok" else "❌" if p.status == "error" else "⚠"
            lines.append(f"  {p.name:<12} {status_emoji} {p.status.upper()}")
        lines.append("")

        # Components
        lines.append(
            f"Database:       {'✅' if result.database_status == 'ok' else '❌'} {result.database_status.upper()}"
        )
        lines.append(
            f"Analysis Engine: {'✅' if result.analysis_engine_status == 'ok' else '❌'} {result.analysis_engine_status.upper()}"
        )
        lines.append(f"Last Update:    {result.last_update or 'Never'}")
        lines.append("")

        # Metrics
        lines.append(f"Active Users:   {result.active_users}")
        lines.append(f"Symbols:        {result.symbols_tracked}")
        lines.append("")

        # Warnings
        if result.warnings:
            lines.append("Warnings:")
            for w in result.warnings[:3]:
                lines.append(f"  • {w}")
            lines.append("")

        # Uptime
        uptime_days = result.uptime_seconds // 86400
        uptime_hours = (result.uptime_seconds % 86400) // 3600
        lines.append(f"Uptime: {uptime_days}d {uptime_hours}h")
        lines.append(f"Version: {result.version}")
        lines.append("═" * 31)

        return "\n".join(lines)

    def _format_freshness(self, quality: "DataQuality") -> str:
        """Format data freshness."""
        seconds = quality.freshness_seconds
        if seconds < 60:
            return f"Fresh ({seconds}s ago)"
        elif seconds < 3600:
            return f"Fresh ({seconds // 60}m ago)"
        elif seconds < 86400:
            return f"Stale ({seconds // 3600}h ago)"
        else:
            return f"Very stale ({seconds // 86400}d ago)"

    def _signal_emoji(self, signal: str) -> str:
        """Get emoji for signal."""
        return {"up": "🟢", "down": "🔴", "neutral": "🟡", "no_signal": "⚪"}.get(signal, "⚪")

    def _feature_emoji(self, value: str) -> str:
        """Get emoji for feature value."""
        return {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(value, "⚪")

    def _volume_emoji(self, value: str) -> str:
        """Get emoji for volume value."""
        return {"strong": "🔊", "weak": "🔇", "normal": "🔈"}.get(value, "⚪")
```

## Usage Example

```python
# In bot handler
async def handle_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /analyze command."""
    symbol = context.args[0] if context.args else None
    
    if not symbol:
        await update.message.reply_text("Usage: /analyze <symbol>")
        return
    
    # Call analysis service (NOT engine directly)
    result: AnalysisResult = await analysis_service.analyze(symbol)
    
    # Format using typed formatter
    formatter = TelegramFormatter()
    message = formatter.format_analysis(result)
    
    # Send
    await update.message.reply_text(message, parse_mode="HTML")
```

## Message Length Handling

```python
def split_message(text: str, max_length: int = 4096) -> list[str]:
    """Split long messages."""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    lines = text.split("\n")
    current = []
    current_length = 0
    
    for line in lines:
        if current_length + len(line) + 1 > max_length - 50:  # Leave buffer
            parts.append("\n".join(current))
            current = [line]
            current_length = len(line)
        else:
            current.append(line)
            current_length += len(line) + 1
    
    if current:
        parts.append("\n".join(current))
    
    return parts
```

## Notes

1. All types are dataclasses for clarity
2. Formatter has NO access to engine internals
3. All values pre-computed by engine
4. Formatter only adds emojis and layout
5. Message length handled by splitting
6. No calculation logic in formatter
