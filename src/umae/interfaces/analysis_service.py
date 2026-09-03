"""High-level analysis service for UMAE."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from umae.analysis.multi_timeframe import MultiTimeframeAnalyzer
from umae.domain.enums import AssetType, MarketRegime, SignalType, Timeframe
from umae.domain.models import (
    CandleSet,
    CompositeSignal,
    FeatureSet,
)
from umae.features.engine import FeatureEngine
from umae.regime.detector import MarketRegimeDetector
from umae.scoring.signal_composer import SignalComposer

if TYPE_CHECKING:
    from umae.interfaces.data_adapter import DataAdapter

logger = logging.getLogger(__name__)

_DEFAULT_TIMEFRAMES = [
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.H1,
    Timeframe.H4,
    Timeframe.D1,
]


@dataclass
class TimeframeAnalysis:
    """Analysis result for a single timeframe."""

    timeframe: Timeframe
    signal: SignalType
    score: float
    regime: MarketRegime
    regime_confidence: float
    features: dict[str, float]
    reason_codes: list[str]


@dataclass
class AnalysisResult:
    """Typed result from analysis service for Telegram formatting."""

    symbol: str
    asset_type: AssetType
    exchange: str
    price: Decimal
    timestamp: datetime

    # Composite
    signal: SignalType
    score: float
    regime: MarketRegime
    regime_confidence: float

    # Breakdown
    timeframe_analyses: list[TimeframeAnalysis] = field(default_factory=list)

    # Data quality from actual candle validation
    data_quality: dict = field(default_factory=dict)

    # Score breakdown (must sum to score within tolerance)
    score_breakdown: dict[str, float] = field(default_factory=dict)

    # Contributors (each maps to an actual computed feature/reason)
    contributors: list[str] = field(default_factory=list)

    # Context
    target_timeframe: Timeframe | None = None
    context_timeframes: list[Timeframe] = field(default_factory=list)

    # Metadata
    reason_codes: list[str] = field(default_factory=list)
    contributing_factors: dict[str, float | str] = field(default_factory=dict)
    model_version: str = "1.0.0"
    feature_version: str = "1.0.0"
    data_version: str = ""
    provider: str = ""
    provider_symbol: str = ""
    analysis_duration_ms: float = 0.0

    @property
    def is_actionable(self) -> bool:
        """Whether the signal is actionable (not neutral/no_signal)."""
        return self.signal in (SignalType.UP, SignalType.DOWN)

    @property
    def direction(self) -> str:
        """Human-readable direction label."""
        if self.signal == SignalType.UP:
            return "LONG"
        if self.signal == SignalType.DOWN:
            return "SHORT"
        return "NEUTRAL"


class AnalysisService:
    """High-level API for asset analysis.

    Orchestrates data adapters, feature engine, regime detector,
    multi-timeframe analysis, and signal composer into a single
    ``analyze(symbol)`` call that returns a typed ``AnalysisResult``.
    """

    def __init__(
        self,
        adapters: dict[str, DataAdapter] | None = None,
        default_adapter: str = "binance",
        timeframes: list[Timeframe] | None = None,
        feature_engine: FeatureEngine | None = None,
        regime_detector: MarketRegimeDetector | None = None,
        mta: MultiTimeframeAnalyzer | None = None,
        signal_composer: SignalComposer | None = None,
    ) -> None:
        self._adapters: dict[str, DataAdapter] = adapters or {}
        self._default_adapter = default_adapter
        self._timeframes = timeframes or list(_DEFAULT_TIMEFRAMES)
        self._feature_engine = feature_engine or FeatureEngine()
        self._regime_detector = regime_detector or MarketRegimeDetector()
        self._mta = mta or MultiTimeframeAnalyzer(regime_detector=self._regime_detector)
        self._signal_composer = signal_composer or SignalComposer()

    def register_adapter(self, name: str, adapter: DataAdapter) -> None:
        """Register a data adapter.

        Args:
            name: Adapter name identifier.
            adapter: DataAdapter implementation.
        """
        self._adapters[name] = adapter

    def _select_adapter(self, category: str | None = None) -> str:
        """Select the best adapter for a given asset category.

        Uses the CATEGORY_PROVIDERS routing map from settings.
        Falls back to self._default_adapter if no mapping exists.

        Args:
            category: Asset category (e.g., "crypto", "forex", "stocks").

        Returns:
            Adapter name to use.

        Raises:
            KeyError: If no adapter is registered for the selected name.
        """
        if category:
            from umae.config.settings import CATEGORY_PROVIDERS

            adapter_name = CATEGORY_PROVIDERS.get(category)
            if adapter_name and adapter_name in self._adapters:
                return adapter_name
        return self._default_adapter

    def _get_adapter(self, adapter_name: str | None = None) -> DataAdapter:
        """Resolve adapter by name or default."""
        name = adapter_name or self._default_adapter
        if name not in self._adapters:
            msg = f"Adapter '{name}' not registered. Available: {list(self._adapters)}"
            raise KeyError(msg)
        return self._adapters[name]

    async def analyze(
        self,
        symbol: str,
        adapter_name: str | None = None,
        timeframes: list[Timeframe] | None = None,
        lookback_days: int = 90,
        target_timeframe: Timeframe | None = None,
        category: str | None = None,
    ) -> AnalysisResult:
        """Run full analysis pipeline on a symbol.

        Args:
            symbol: Asset symbol (e.g., "BTC/USDT", "AAPL").
            adapter_name: Override adapter name (uses default if None).
            timeframes: Override timeframes (uses instance defaults if None).
            lookback_days: Days of historical data to fetch.
            target_timeframe: If set, this is the single-TF target.
            category: Asset category for provider routing (e.g., "crypto", "forex").

        Returns:
            AnalysisResult with signal, regime, and timeframe breakdown.
        """
        import time as _time

        from umae.config.settings import get_settings

        start_ms = _time.monotonic()
        tfs = timeframes or self._timeframes
        settings = get_settings()
        provider_name = adapter_name or self._select_adapter(category)
        provider_symbol = symbol

        # Try to resolve adapter
        try:
            adapter = self._get_adapter(adapter_name)
        except KeyError as e:
            duration_ms = (_time.monotonic() - start_ms) * 1000
            return AnalysisResult(
                symbol=symbol,
                asset_type=AssetType.CRYPTO,
                exchange="unknown",
                price=Decimal("0"),
                timestamp=datetime.utcnow(),
                signal=SignalType.NO_SIGNAL,
                score=0.0,
                regime=MarketRegime.UNCERTAIN,
                regime_confidence=0.0,
                timeframe_analyses=[],
                reason_codes=["DATA_PROVIDER_UNAVAILABLE", str(e)],
                provider=provider_name,
                provider_symbol=provider_symbol,
                model_version=settings.version,
                analysis_duration_ms=round(duration_ms, 2),
            )

        # Get asset metadata
        try:
            metadata = await adapter.get_asset_metadata(symbol)
        except Exception as e:
            logger.warning("Failed to get metadata for %s: %s", symbol, e)
            metadata = None

        # Get current price
        try:
            price = Decimal(str(await self._get_current_price(adapter, symbol)))
        except (ValueError, Exception) as e:
            logger.warning("Failed to get price for %s: %s", symbol, e)
            duration_ms = (_time.monotonic() - start_ms) * 1000
            return AnalysisResult(
                symbol=symbol,
                asset_type=metadata.asset_type if metadata else AssetType.CRYPTO,
                exchange=metadata.exchange if metadata else "unknown",
                price=Decimal("0"),
                timestamp=datetime.utcnow(),
                signal=SignalType.NO_SIGNAL,
                score=0.0,
                regime=MarketRegime.UNCERTAIN,
                regime_confidence=0.0,
                timeframe_analyses=[],
                reason_codes=["DATA_PROVIDER_UNAVAILABLE", f"{type(e).__name__}: {e}"],
                provider=provider_name,
                provider_symbol=provider_symbol,
                model_version=settings.version,
                analysis_duration_ms=round(duration_ms, 2),
            )

        # Fetch candle data for each timeframe
        candle_sets = await self._fetch_candle_sets(adapter, symbol, tfs, lookback_days)

        # Compute data quality from actual candle data
        data_quality = self._compute_data_quality(candle_sets, tfs)

        # Check if we got any data
        total_candles = sum(len(cs.candles) for cs in candle_sets.values())
        if total_candles == 0:
            duration_ms = (_time.monotonic() - start_ms) * 1000
            return AnalysisResult(
                symbol=symbol,
                asset_type=metadata.asset_type if metadata else AssetType.CRYPTO,
                exchange=metadata.exchange if metadata else "unknown",
                price=price,
                timestamp=datetime.utcnow(),
                signal=SignalType.NO_SIGNAL,
                score=0.0,
                regime=MarketRegime.UNCERTAIN,
                regime_confidence=0.0,
                timeframe_analyses=[],
                reason_codes=["NO_CANDLE_DATA"],
                provider=provider_name,
                provider_symbol=provider_symbol,
                model_version=settings.version,
                analysis_duration_ms=round(duration_ms, 2),
            )

        # Compute features per timeframe
        feature_sets: dict[Timeframe, FeatureSet] = {}
        for tf, cs in candle_sets.items():
            if cs.candles:
                try:
                    feature_sets[tf] = self._feature_engine.compute(cs)
                except Exception as e:
                    logger.warning("Feature computation failed for %s %s: %s", symbol, tf.value, e)

        # Run multi-timeframe analysis
        composite = self._mta.analyze(
            symbol=symbol,
            asset_type=metadata.asset_type if metadata else AssetType.CRYPTO,
            exchange=metadata.exchange if metadata else "unknown",
            price=float(price),
            candle_sets=candle_sets,
            feature_sets=feature_sets,
        )

        # Compose final signal
        final = self._signal_composer.compose(composite)

        # Build timeframe breakdown — include ALL configured TFs, DATA_UNAVAILABLE for missing
        tf_analyses = self._build_timeframe_analyses(final, candle_sets, tfs)

        # Extract score breakdown and contributors
        score_breakdown = {}
        contributors = []
        if "score_breakdown" in final.contributing_factors:
            score_breakdown = final.contributing_factors["score_breakdown"]
        if "contributors" in final.contributing_factors:
            contributors = final.contributing_factors["contributors"]

        # Context timeframes
        context_tfs = [tf for tf in tfs if tf != target_timeframe]

        duration_ms = (_time.monotonic() - start_ms) * 1000

        return AnalysisResult(
            symbol=symbol,
            asset_type=metadata.asset_type if metadata else AssetType.CRYPTO,
            exchange=metadata.exchange if metadata else "unknown",
            price=price,
            timestamp=final.timestamp,
            signal=final.signal,
            score=final.score.raw_score,
            regime=final.regime,
            regime_confidence=self._dominant_regime_confidence(final),
            timeframe_analyses=tf_analyses,
            data_quality=data_quality,
            score_breakdown=score_breakdown,
            contributors=contributors,
            target_timeframe=target_timeframe,
            context_timeframes=context_tfs,
            reason_codes=final.reason_codes,
            contributing_factors={
                k: v
                for k, v in final.contributing_factors.items()
                if isinstance(v, (int, float, str))
            },
            model_version=settings.version,
            feature_version="features-1.0.0",
            data_version=f"{provider_name}-rest-v1",
            provider=provider_name,
            provider_symbol=provider_symbol,
            analysis_duration_ms=round(duration_ms, 2),
        )

    async def _get_current_price(self, adapter: DataAdapter, symbol: str) -> float:
        """Get the latest price from adapter.

        Tries to get price from the most recent candle data.
        Falls back to a dedicated price fetch if needed.
        """
        from datetime import timedelta

        from umae.interfaces.base_adapter import ProviderError

        now = datetime.utcnow()

        # Try 1h candles first (most reliable for current price)
        try:
            start = (now - timedelta(hours=2)).isoformat()
            end = now.isoformat()
            cs = await adapter.fetch_candles(symbol, Timeframe.H1, start, end)
            if cs.candles:
                return float(cs.candles[-1].close)
        except ProviderError:
            raise
        except Exception:
            pass

        # Fallback to 1m candles
        try:
            start = (now - timedelta(minutes=5)).isoformat()
            end = now.isoformat()
            cs = await adapter.fetch_candles(symbol, Timeframe.M1, start, end)
            if cs.candles:
                return float(cs.candles[-1].close)
        except ProviderError:
            raise
        except Exception:
            pass

        # Fallback to daily
        try:
            start = (now - timedelta(days=2)).isoformat()
            end = now.isoformat()
            cs = await adapter.fetch_candles(symbol, Timeframe.D1, start, end)
            if cs.candles:
                return float(cs.candles[-1].close)
        except ProviderError:
            raise
        except Exception:
            pass

        raise ValueError(f"Unable to fetch current price for {symbol}")

    async def _fetch_candle_sets(
        self,
        adapter: DataAdapter,
        symbol: str,
        timeframes: list[Timeframe],
        lookback_days: int,
    ) -> dict[Timeframe, CandleSet]:
        """Fetch candle sets for all requested timeframes."""
        from datetime import timedelta

        now = datetime.utcnow()
        start = (now - timedelta(days=lookback_days)).isoformat()
        end = now.isoformat()

        candle_sets: dict[Timeframe, CandleSet] = {}
        for tf in timeframes:
            try:
                cs = await adapter.fetch_candles(symbol, tf, start, end)
                candle_sets[tf] = cs
            except Exception:
                logger.warning("Failed to fetch %s candles for %s", tf.value, symbol)
                candle_sets[tf] = CandleSet(symbol=symbol, timeframe=tf, source=adapter.name)

        return candle_sets

    def _build_timeframe_analyses(
        self,
        composite: CompositeSignal,
        candle_sets: dict[Timeframe, CandleSet],
        all_timeframes: list[Timeframe],
    ) -> list[TimeframeAnalysis]:
        """Build per-timeframe analysis breakdown from composite.

        Returns results for ALL configured timeframes.
        Missing data → signal=NO_SIGNAL with DATA_UNAVAILABLE reason.
        """
        analyses: list[TimeframeAnalysis] = []
        for tf in sorted(all_timeframes, key=lambda x: x.minutes):
            if tf in composite.timeframe_signals:
                ts = composite.timeframe_signals[tf]
                regime = ts.regime.regime if ts.regime else MarketRegime.UNCERTAIN
                regime_conf = ts.regime.confidence if ts.regime else 0.0

                analyses.append(
                    TimeframeAnalysis(
                        timeframe=tf,
                        signal=ts.signal,
                        score=ts.score.raw_score,
                        regime=regime,
                        regime_confidence=regime_conf,
                        features=ts.features_used,
                        reason_codes=ts.reason_codes,
                    )
                )
            else:
                # Missing data — explicit DATA_UNAVAILABLE
                cs = candle_sets.get(tf)
                reasons = ["DATA_UNAVAILABLE"]
                if cs is not None and not cs.candles:
                    reasons.append("no_candle_data")
                elif cs is None:
                    reasons.append("fetch_failed")

                analyses.append(
                    TimeframeAnalysis(
                        timeframe=tf,
                        signal=SignalType.NO_SIGNAL,
                        score=0.0,
                        regime=MarketRegime.UNCERTAIN,
                        regime_confidence=0.0,
                        features={},
                        reason_codes=reasons,
                    )
                )
        return analyses

    def _compute_data_quality(
        self,
        candle_sets: dict[Timeframe, CandleSet],
        all_timeframes: list[Timeframe],
    ) -> dict:
        """Compute data quality from actual candle data.

        Returns dict with quality state, freshness, completeness, etc.
        """

        now = datetime.utcnow()
        total_expected = len(all_timeframes)
        total_present = sum(
            1 for tf in all_timeframes if tf in candle_sets and candle_sets[tf].candles
        )

        completeness = total_present / total_expected if total_expected > 0 else 0.0

        # Find latest candle timestamp across all timeframes
        latest_ts = None
        total_candles = 0
        incomplete_candles = 0
        missing_candles = 0

        for _tf, cs in candle_sets.items():
            if cs.candles:
                total_candles += len(cs.candles)
                if latest_ts is None or cs.candles[-1].timestamp > latest_ts:
                    latest_ts = cs.candles[-1].timestamp
                # Check for incomplete last candle
                if not cs.candles[-1].is_complete:
                    incomplete_candles += 1
                # Check for gaps
                gaps = cs.gaps()
                missing_candles += len(gaps)

        # Determine quality state
        if total_candles == 0:
            quality_state = "UNAVAILABLE"
        elif completeness < 0.5:
            quality_state = "INCOMPLETE"
        elif missing_candles > 0:
            quality_state = "DEGRADED"
        elif incomplete_candles > 0:
            quality_state = "STALE"
        else:
            quality_state = "GOOD"

        freshness_seconds = 0
        if latest_ts:
            freshness_seconds = max(0, int((now - latest_ts).total_seconds()))
            if freshness_seconds > 86400:
                quality_state = "STALE"

        return {
            "state": quality_state,
            "freshness_seconds": freshness_seconds,
            "completeness": completeness,
            "total_candles": total_candles,
            "missing_candles": missing_candles,
            "incomplete_candles": incomplete_candles,
            "latest_closed_candle_timestamp": latest_ts.isoformat() if latest_ts else None,
        }

    def _dominant_regime_confidence(self, composite: CompositeSignal) -> float:
        """Extract confidence for the dominant regime from timeframe signals."""
        regime_votes: dict[MarketRegime, tuple[int, float]] = {}
        for ts in composite.timeframe_signals.values():
            if ts.regime is None:
                continue
            r = ts.regime.regime
            count, total_conf = regime_votes.get(r, (0, 0.0))
            regime_votes[r] = (count + 1, total_conf + ts.regime.confidence)

        if not regime_votes:
            return 0.0

        best_regime = max(regime_votes, key=lambda r: regime_votes[r][0])
        count, total_conf = regime_votes[best_regime]
        return round(total_conf / count, 4) if count else 0.0
