"""Telegram-specific response models.

These are the typed objects passed from the analysis service to the
formatter. The formatter has NO access to internal engine state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal


@dataclass
class TimeframeResult:
    """Result for a single timeframe."""

    timeframe: str
    signal: str
    score: float
    regime: str
    regime_confidence: float
    trend: str
    momentum: str
    volume: str
    volatility: str
    structure: str
    features_used: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class DataQuality:
    """Data quality information."""

    state: str  # GOOD, DEGRADED, STALE, INCOMPLETE, INVALID, UNAVAILABLE
    freshness_seconds: int
    completeness: float
    candle_count: int
    missing_candles: int
    incomplete_candles: int = 0
    latest_closed_candle_timestamp: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class FeatureSummary:
    """Summary of feature states."""

    trend: str
    momentum: str
    volume: str
    volatility: str
    structure: str


@dataclass
class ScoreBreakdown:
    """Structured score breakdown for auditability."""

    htf_bias: float = 0.0
    trend_alignment: float = 0.0
    momentum: float = 0.0
    volume: float = 0.0
    structure: float = 0.0
    regime_adjustment: float = 0.0
    total: float = 0.0


@dataclass
class AnalysisResult:
    """Complete analysis result for Telegram formatting."""

    symbol: str
    asset_type: str
    exchange: str
    timestamp: str
    price: Decimal
    data_quality: DataQuality
    regime: str
    regime_confidence: float
    signal: str
    signal_score: float

    timeframe_results: list[TimeframeResult] = field(default_factory=list)
    calibrated_confidence: float | None = None
    feature_summary: FeatureSummary | None = None
    score_breakdown: ScoreBreakdown | None = None
    contributors: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    target_timeframe: str | None = None
    context_timeframes: list[str] = field(default_factory=list)
    model_version: str = "1.0.0"
    feature_version: str = "1.0.0"
    data_version: str = ""
    provider: str = ""
    provider_symbol: str = ""
    support_resistance: dict[str, object] | None = None
    additional_info: dict[str, object] | None = None


@dataclass
class ProviderStatus:
    """Status of a data provider."""

    name: str
    status: str
    error_message: str | None = None
    last_success: str | None = None
    data_quality: float | None = None


@dataclass
class SystemStatus:
    """System health status."""

    providers: list[ProviderStatus] = field(default_factory=list)

    database_status: str = "ok"
    analysis_engine_status: str = "ok"

    last_update: str | None = None
    uptime_seconds: int = 0

    active_users: int = 0
    symbols_tracked: int = 0

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    version: str = "0.1.0"


@dataclass
class WatchlistItem:
    """Single item in watchlist."""

    symbol: str
    exchange: str
    signal: str
    score: float
    price: Decimal | None = None
    last_analyzed: str | None = None


@dataclass
class WatchlistResult:
    """Watchlist response."""

    user_id: int
    items: list[WatchlistItem] = field(default_factory=list)
    max_items: int = 50
