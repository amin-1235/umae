"""Telegram-specific services.

Wraps core UMAE services for Telegram bot usage.
Bridges between the analysis engine's typed results and Telegram formatter models.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from umae.domain.enums import AssetType, MarketRegime, SignalType, Timeframe
from umae.telegram.models import (
    AnalysisResult,
    DataQuality,
    FeatureSummary,
    ScoreBreakdown,
    TimeframeResult,
    WatchlistItem,
    WatchlistResult,
)

if TYPE_CHECKING:
    from umae.interfaces.analysis_service import (
        AnalysisService as CoreAnalysisService,
    )
    from umae.storage.repositories import WatchlistRepository

logger = logging.getLogger(__name__)

# ── Timeframe string → enum mapping ────────────────────────────
TIMEFRAME_MAP: dict[str, Timeframe] = {tf.value: tf for tf in Timeframe}

# ── Signal state for unavailable data ───────────────────────────
DATA_UNAVAILABLE_SIGNAL = "unavailable"
DATA_UNAVAILABLE_SCORE = 0.0


def _convert_signal(signal: SignalType) -> str:
    """Convert SignalType enum to Telegram string."""
    mapping = {
        SignalType.UP: "up",
        SignalType.DOWN: "down",
        SignalType.NEUTRAL: "neutral",
        SignalType.NO_SIGNAL: "no_signal",
    }
    return mapping.get(signal, "neutral")


def _convert_regime(regime: MarketRegime) -> str:
    """Convert MarketRegime enum to Telegram string."""
    mapping = {
        MarketRegime.TRENDING_UP: "TRENDING_UP",
        MarketRegime.TRENDING_DOWN: "TRENDING_DOWN",
        MarketRegime.RANGING: "RANGING",
        MarketRegime.HIGH_VOLATILITY: "HIGH_VOLATILITY",
        MarketRegime.LOW_VOLATILITY: "LOW_VOLATILITY",
        MarketRegime.BREAKOUT: "BREAKOUT",
        MarketRegime.UNCERTAIN: "UNCERTAIN",
    }
    return mapping.get(regime, "UNKNOWN")


def _convert_asset_type(asset_type: AssetType) -> str:
    """Convert AssetType enum to Telegram string."""
    mapping = {
        AssetType.CRYPTO: "crypto",
        AssetType.STOCK: "stock",
        AssetType.FOREX: "forex",
        AssetType.INDEX: "index",
        AssetType.COMMODITY: "commodity",
    }
    return mapping.get(asset_type, "unknown")


class AnalysisService:
    """Telegram-facing analysis service.

    Wraps the core AnalysisService and converts results into
    Telegram formatter models (dataclass-based, string-typed).
    """

    def __init__(self, core_service: CoreAnalysisService) -> None:
        self._core = core_service

    async def analyze(
        self,
        symbol: str,
        target_timeframe: Timeframe | None = None,
        category: str | None = None,
    ) -> AnalysisResult:
        """Run analysis and return Telegram-formatted result.

        Args:
            symbol: Asset symbol to analyze.
            target_timeframe: If set, the single-TF target for analysis.
            category: Asset category for provider routing (e.g., "crypto", "forex").

        Returns:
            AnalysisResult formatted for Telegram display.
        """
        result = await self._core.analyze(
            symbol,
            target_timeframe=target_timeframe,
            category=category,
        )
        return self._convert_result(result)

    def _convert_result(self, core_result) -> AnalysisResult:
        """Convert core AnalysisResult to Telegram AnalysisResult."""
        timeframe_results = []
        for tf_analysis in core_result.timeframe_analyses:
            timeframe_results.append(
                TimeframeResult(
                    timeframe=tf_analysis.timeframe.value,
                    signal=_convert_signal(tf_analysis.signal),
                    score=tf_analysis.score,
                    regime=_convert_regime(tf_analysis.regime),
                    regime_confidence=tf_analysis.regime_confidence,
                    trend=self._extract_trend(tf_analysis.features),
                    momentum=self._extract_momentum(tf_analysis.features),
                    volume=self._extract_volume(tf_analysis.features),
                    volatility=self._extract_volatility(tf_analysis.features),
                    structure=self._extract_structure(tf_analysis.features),
                    features_used=list(tf_analysis.features.keys()),
                    reason_codes=tf_analysis.reason_codes,
                )
            )

        # Data quality from core result
        dq = getattr(core_result, "data_quality", None)
        if dq and isinstance(dq, dict):
            data_quality = DataQuality(
                state=dq.get("state", "UNKNOWN"),
                freshness_seconds=dq.get("freshness_seconds", 0),
                completeness=dq.get("completeness", 0.0),
                candle_count=dq.get("total_candles", 0),
                missing_candles=dq.get("missing_candles", 0),
                incomplete_candles=dq.get("incomplete_candles", 0),
                latest_closed_candle_timestamp=dq.get("latest_closed_candle_timestamp"),
            )
        else:
            data_quality = DataQuality(
                state="UNKNOWN",
                freshness_seconds=0,
                completeness=0.0,
                candle_count=0,
                missing_candles=0,
            )

        # Feature summary from dominant TF (highest with data)
        feature_summary = None
        data_tfs = [ta for ta in core_result.timeframe_analyses if ta.features]
        if data_tfs:
            dominant_tf = data_tfs[-1]
            feature_summary = FeatureSummary(
                trend=self._extract_trend(dominant_tf.features),
                momentum=self._extract_momentum(dominant_tf.features),
                volume=self._extract_volume(dominant_tf.features),
                volatility=self._extract_volatility(dominant_tf.features),
                structure=self._extract_structure(dominant_tf.features),
            )

        # Score breakdown
        score_breakdown = None
        sb = getattr(core_result, "score_breakdown", None)
        if sb and isinstance(sb, dict):
            total = core_result.score
            score_breakdown = ScoreBreakdown(
                htf_bias=sb.get("htf_bias", 0.0),
                trend_alignment=sb.get("trend_alignment", 0.0),
                momentum=sb.get("momentum", 0.0),
                volume=sb.get("volume", 0.0),
                structure=sb.get("structure", 0.0),
                regime_adjustment=sb.get("regime_adjustment", 0.0),
                total=total,
            )

        # Contributors
        contributors = getattr(core_result, "contributors", [])

        # Warnings from missing data
        warnings = []
        for ta in core_result.timeframe_analyses:
            if "DATA_UNAVAILABLE" in ta.reason_codes:
                warnings.append(f"{ta.timeframe.value}: DATA_UNAVAILABLE")

        timestamp = core_result.timestamp
        if isinstance(timestamp, datetime):
            timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        else:
            timestamp_str = str(timestamp)

        # Target / context timeframes
        target_tf = None
        context_tfs = []
        if core_result.target_timeframe is not None:
            target_tf = core_result.target_timeframe.value
        if core_result.context_timeframes:
            context_tfs = [tf.value for tf in core_result.context_timeframes]

        return AnalysisResult(
            symbol=core_result.symbol,
            asset_type=_convert_asset_type(core_result.asset_type),
            exchange=core_result.exchange,
            timestamp=timestamp_str,
            price=core_result.price,
            data_quality=data_quality,
            regime=_convert_regime(core_result.regime),
            regime_confidence=core_result.regime_confidence,
            signal=_convert_signal(core_result.signal),
            signal_score=core_result.score,
            timeframe_results=timeframe_results,
            calibrated_confidence=None,
            feature_summary=feature_summary,
            score_breakdown=score_breakdown,
            contributors=contributors,
            reason_codes=core_result.reason_codes,
            warnings=warnings,
            target_timeframe=target_tf,
            context_timeframes=context_tfs,
            model_version=core_result.model_version,
            feature_version=core_result.feature_version,
            data_version=core_result.data_version,
            provider=core_result.provider,
            provider_symbol=core_result.provider_symbol,
            support_resistance=None,
            additional_info={
                "analysis_duration_ms": core_result.analysis_duration_ms,
            },
        )

    @staticmethod
    def _extract_trend(features: dict[str, float]) -> str:
        """Extract trend state from actual computed features."""
        ema_fast = features.get("trend_ema_fast", 0)
        ema_slow = features.get("trend_ema_slow", 0)
        ema_trend = features.get("trend_ema_trend", 0)
        struct_score = features.get("trend_structure_score", 0)

        # EMA alignment
        if ema_fast > ema_slow > ema_trend and struct_score > 0:
            return "BULLISH"
        if ema_fast < ema_slow < ema_trend and struct_score < 0:
            return "BEARISH"
        if struct_score > 0.3:
            return "BULLISH"
        if struct_score < -0.3:
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _extract_momentum(features: dict[str, float]) -> str:
        """Extract momentum state from actual computed features."""
        rsi = features.get("momentum_rsi", 50.0)
        macd_hist = features.get("momentum_macd_histogram", 0.0)

        if rsi > 70 and macd_hist > 0:
            return "BULLISH"
        if rsi < 30 and macd_hist < 0:
            return "BEARISH"
        if rsi > 70:
            return "OVERBOUGHT"
        if rsi < 30:
            return "OVERSOLD"
        return "NEUTRAL"

    @staticmethod
    def _extract_volume(features: dict[str, float]) -> str:
        """Extract volume state from actual computed features."""
        vol_relative = features.get("volume_relative", 1.0)
        vol_spike = features.get("volume_spike", 0.0)

        if vol_spike > 0 or vol_relative > 2.0:
            return "HIGH"
        if vol_relative > 1.5:
            return "ELEVATED"
        if vol_relative < 0.5:
            return "LOW"
        return "NORMAL"

    @staticmethod
    def _extract_volatility(features: dict[str, float]) -> str:
        """Extract volatility state from actual computed features."""
        expansion = features.get("volatility_expansion", 1.0)
        vol_regime = features.get("volatility_regime", 0.0)

        if vol_regime > 0 or expansion > 1.5:
            return "HIGH"
        if vol_regime < 0 or expansion < 0.5:
            return "LOW"
        return "NORMAL"

    @staticmethod
    def _extract_structure(features: dict[str, float]) -> str:
        """Extract market structure state from actual computed features."""
        hh = features.get("trend_structure_hh", 0)
        hl = features.get("trend_structure_hl", 0)
        lh = features.get("trend_structure_lh", 0)
        ll = features.get("trend_structure_ll", 0)
        struct_score = features.get("trend_structure_score", 0)

        if hh > 0 and hl > 0 and struct_score > 0:
            return "BULLISH"
        if lh > 0 and ll > 0 and struct_score < 0:
            return "BEARISH"
        if struct_score > 0:
            return "BULLISH"
        if struct_score < 0:
            return "BEARISH"
        return "MIXED"


class WatchlistService:
    """Telegram-facing watchlist service.

    Wraps WatchlistRepository and adds symbol analysis lookups
    for watchlist display.
    """

    def __init__(
        self,
        repo: WatchlistRepository,
        analysis_service: AnalysisService,
        max_size: int = 50,
    ) -> None:
        self._repo = repo
        self._analysis = analysis_service
        self._max_size = max_size

    async def get_watchlist(self, user_id: int) -> WatchlistResult:
        """Get formatted watchlist for a user."""
        symbols = self._repo.get_watchlist(user_id)
        items: list[WatchlistItem] = []

        for symbol in symbols[: self._max_size]:
            try:
                result = await self._analysis.analyze(symbol)
                items.append(
                    WatchlistItem(
                        symbol=result.symbol,
                        exchange=result.exchange,
                        signal=result.signal,
                        score=result.signal_score,
                        price=result.price,
                        last_analyzed=result.timestamp,
                    )
                )
            except Exception as e:
                logger.warning("Failed to analyze %s for watchlist: %s", symbol, e)
                items.append(
                    WatchlistItem(
                        symbol=symbol,
                        exchange="",
                        signal=DATA_UNAVAILABLE_SIGNAL,
                        score=DATA_UNAVAILABLE_SCORE,
                    )
                )

        return WatchlistResult(
            user_id=user_id,
            items=items,
            max_items=self._max_size,
        )

    def add_symbol(self, user_id: int, chat_id: int, symbol: str) -> str:
        """Add a symbol to user's watchlist.

        Returns:
            "added", "duplicate", or "full"
        """
        symbols = self._repo.get_watchlist(user_id)
        if len(symbols) >= self._max_size:
            return "full"

        added = self._repo.add_to_watchlist(user_id, chat_id, symbol)
        return "added" if added else "duplicate"

    def remove_symbol(self, user_id: int, symbol: str) -> str:
        """Remove a symbol from user's watchlist.

        Returns:
            "removed" or "not_found"
        """
        removed = self._repo.remove_from_watchlist(user_id, symbol)
        return "removed" if removed else "not_found"

    def get_symbols(self, user_id: int) -> list[str]:
        """Get raw symbol list for a user."""
        return self._repo.get_watchlist(user_id)
