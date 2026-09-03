"""Signal audit logger for full context logging and querying."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from umae.domain.enums import (
    AssetType,
    MarketRegime,
    SignalType,
    Timeframe,
)
from umae.domain.models import CompositeSignal, SignalAudit

logger = logging.getLogger(__name__)


class SignalAuditLogger:
    """Logs every signal with full context for auditability.

    Stores: timestamp, asset, exchange, timeframe, price, features,
    regime, signal, score, reason codes.
    """

    def __init__(self, store_dir: str | Path | None = None) -> None:
        self._store_dir = Path(store_dir) if store_dir else None
        self._memory_store: list[SignalAudit] = []

    def log(self, composite: CompositeSignal) -> SignalAudit:
        """Log a composite signal as a full audit record.

        Args:
            composite: The composite signal to audit.

        Returns:
            SignalAudit record with generated id.
        """
        audit = self._from_composite(composite)

        self._memory_store.append(audit)

        if self._store_dir is not None:
            self._persist(audit)

        logger.debug(
            "Signal audit: %s %s score=%.4f signal=%s",
            audit.symbol,
            audit.exchange,
            audit.raw_score,
            audit.signal.value,
        )

        return audit

    def log_timeframe(
        self,
        symbol: str,
        asset_type: AssetType,
        exchange: str,
        timeframe: Timeframe,
        price: float,
        signal: SignalType,
        raw_score: float,
        features: dict[str, float],
        regime: MarketRegime,
        regime_confidence: float = 0.0,
        reason_codes: list[str] | None = None,
    ) -> SignalAudit:
        """Log a single timeframe signal.

        Returns:
            SignalAudit record.
        """
        audit = SignalAudit(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            symbol=symbol,
            asset_type=asset_type,
            exchange=exchange,
            timeframe=timeframe,
            price=Decimal(str(price)),
            signal=signal,
            raw_score=raw_score,
            features=features,
            market_regime=regime,
            regime_confidence=regime_confidence,
            reason_codes=reason_codes or [],
        )

        self._memory_store.append(audit)

        if self._store_dir is not None:
            self._persist(audit)

        return audit

    def query(
        self,
        symbol: str | None = None,
        exchange: str | None = None,
        signal: SignalType | None = None,
        timeframe: Timeframe | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[SignalAudit]:
        """Query audit records with optional filters.

        Args:
            symbol: Filter by symbol.
            exchange: Filter by exchange.
            signal: Filter by signal type.
            timeframe: Filter by timeframe.
            since: Only records after this timestamp.
            until: Only records before this timestamp.
            limit: Maximum records to return.

        Returns:
            Matching audit records.
        """
        results = self._memory_store

        if symbol is not None:
            results = [a for a in results if a.symbol == symbol]
        if exchange is not None:
            results = [a for a in results if a.exchange == exchange]
        if signal is not None:
            results = [a for a in results if a.signal == signal]
        if timeframe is not None:
            results = [a for a in results if a.timeframe == timeframe]
        if since is not None:
            results = [a for a in results if a.timestamp >= since]
        if until is not None:
            results = [a for a in results if a.timestamp <= until]

        return results[-limit:]

    def get_by_id(self, audit_id: str) -> SignalAudit | None:
        """Get an audit record by id."""
        for audit in self._memory_store:
            if audit.id == audit_id:
                return audit
        return None

    def summary(
        self,
        symbol: str | None = None,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """Get summary statistics of audit records."""
        records = self._memory_store
        if symbol is not None:
            records = [a for a in records if a.symbol == symbol]
        if since is not None:
            records = [a for a in records if a.timestamp >= since]

        if not records:
            return {"count": 0}

        signal_counts: dict[str, int] = {}
        scores: list[float] = []
        for a in records:
            signal_counts[a.signal.value] = signal_counts.get(a.signal.value, 0) + 1
            scores.append(a.raw_score)

        return {
            "count": len(records),
            "signal_distribution": signal_counts,
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "symbols": list({a.symbol for a in records}),
            "exchanges": list({a.exchange for a in records}),
        }

    def clear(self) -> None:
        """Clear in-memory audit store."""
        self._memory_store.clear()

    def _from_composite(self, composite: CompositeSignal) -> SignalAudit:
        features: dict[str, float] = {}
        for tf_sig in composite.timeframe_signals.values():
            for k, v in tf_sig.features_used.items():
                if k not in features:
                    features[k] = v

        timeframe_signals: dict[str, str] = {}
        for tf, ts in composite.timeframe_signals.items():
            timeframe_signals[tf.value] = ts.signal.value

        return SignalAudit(
            id=str(uuid.uuid4()),
            timestamp=composite.timestamp,
            symbol=composite.symbol,
            asset_type=composite.asset_type,
            exchange=composite.exchange,
            timeframe=max(
                composite.timeframe_signals.keys(),
                key=lambda x: x.minutes,
                default=Timeframe.D1,
            ),
            price=composite.price,
            signal=composite.signal,
            raw_score=composite.score.raw_score,
            calibrated_confidence=composite.score.calibrated_confidence,
            features=features,
            market_regime=composite.regime,
            timeframe_signals=timeframe_signals,
            reason_codes=composite.reason_codes,
            contributing_factors=composite.contributing_factors,
            model_version=composite.model_version,
            data_version=composite.data_version,
        )

    def _persist(self, audit: SignalAudit) -> None:
        if self._store_dir is None:
            return

        self._store_dir.mkdir(parents=True, exist_ok=True)
        date_str = audit.timestamp.strftime("%Y-%m-%d")
        filename = self._store_dir / f"audit_{date_str}.jsonl"

        record = {
            "id": audit.id,
            "timestamp": audit.timestamp.isoformat(),
            "symbol": audit.symbol,
            "asset_type": audit.asset_type.value,
            "exchange": audit.exchange,
            "timeframe": audit.timeframe.value,
            "price": str(audit.price),
            "signal": audit.signal.value,
            "raw_score": audit.raw_score,
            "calibrated_confidence": audit.calibrated_confidence,
            "features": audit.features,
            "market_regime": audit.market_regime.value,
            "regime_confidence": audit.regime_confidence,
            "timeframe_signals": audit.timeframe_signals,
            "reason_codes": audit.reason_codes,
            "contributing_factors": audit.contributing_factors,
            "model_version": audit.model_version,
            "data_version": audit.data_version,
            "created_at": audit.created_at.isoformat(),
        }

        with open(filename, "a") as f:
            f.write(json.dumps(record) + "\n")
