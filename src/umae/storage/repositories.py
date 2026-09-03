"""Repository pattern for data access."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import and_, desc

from umae.domain.enums import AssetType, MarketRegime, Timeframe
from umae.domain.models import (
    AssetMetadata,
    Candle,
    CandleSet,
    FeeModel,
    SignalAudit,
)
from umae.storage.database import get_session
from umae.storage.models import (
    AssetMetadataModel,
    CandleModel,
    SignalModel,
    WatchlistModel,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CandleRepository:
    """Repository for candle data."""

    def __init__(self, session: Session | None = None) -> None:
        """Initialize repository.

        Args:
            session: Database session (creates new if not provided)
        """
        self._session = session

    @property
    def session(self) -> Session:
        """Get database session."""
        if self._session is None:
            return get_session()
        return self._session

    def save_candle_set(self, candle_set: CandleSet) -> int:
        """Save a candle set to database.

        Args:
            candle_set: CandleSet to save

        Returns:
            Number of candles saved
        """
        count = 0
        for candle in candle_set.candles:
            model = CandleModel(
                symbol=candle_set.symbol,
                timeframe=candle_set.timeframe.value,
                timestamp=candle.timestamp,
                open=float(candle.open),
                high=float(candle.high),
                low=float(candle.low),
                close=float(candle.close),
                volume=float(candle.volume),
                quote_volume=float(candle.quote_volume) if candle.quote_volume else None,
                trades_count=candle.trades_count,
                is_complete=candle.is_complete,
                source=candle_set.source,
                data_version=candle_set.data_version,
            )
            self.session.merge(model)
            count += 1

        self.session.commit()
        logger.debug(f"Saved {count} candles for {candle_set.symbol}")
        return count

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> CandleSet:
        """Get candles from database.

        Args:
            symbol: Asset symbol
            timeframe: Candle timeframe
            start: Start timestamp
            end: End timestamp
            limit: Maximum number of candles

        Returns:
            CandleSet with retrieved candles
        """
        query = self.session.query(CandleModel).filter(
            and_(
                CandleModel.symbol == symbol,
                CandleModel.timeframe == timeframe.value,
            )
        )

        if start:
            query = query.filter(CandleModel.timestamp >= start)
        if end:
            query = query.filter(CandleModel.timestamp <= end)

        query = query.order_by(CandleModel.timestamp)

        if limit:
            query = query.limit(limit)

        models = query.all()

        candles = [
            Candle(
                timestamp=m.timestamp.value if hasattr(m.timestamp, "value") else m.timestamp,
                open=Decimal(str(m.open)),
                high=Decimal(str(m.high)),
                low=Decimal(str(m.low)),
                close=Decimal(str(m.close)),
                volume=Decimal(str(m.volume)),
                quote_volume=Decimal(str(m.quote_volume)) if m.quote_volume else None,
                trades_count=m.trades_count.value
                if hasattr(m.trades_count, "value")
                else m.trades_count,
                is_complete=m.is_complete.value
                if hasattr(m.is_complete, "value")
                else m.is_complete,
            )
            for m in models
        ]

        return CandleSet(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            source=(
                models[0].source.value if hasattr(models[0].source, "value") else models[0].source
            )
            if models
            else "",
            data_version=(
                models[0].data_version.value
                if hasattr(models[0].data_version, "value")
                else models[0].data_version
            )
            if models
            else "",
        )

    def get_latest_candle(self, symbol: str, timeframe: Timeframe) -> Candle | None:
        """Get the latest candle for a symbol/timeframe.

        Args:
            symbol: Asset symbol
            timeframe: Candle timeframe

        Returns:
            Latest Candle or None
        """
        model = (
            self.session.query(CandleModel)
            .filter(
                and_(
                    CandleModel.symbol == symbol,
                    CandleModel.timeframe == timeframe.value,
                )
            )
            .order_by(desc(CandleModel.timestamp))
            .first()
        )

        if model is None:
            return None

        return Candle(
            timestamp=model.timestamp.value
            if hasattr(model.timestamp, "value")
            else model.timestamp,
            open=Decimal(str(model.open)),
            high=Decimal(str(model.high)),
            low=Decimal(str(model.low)),
            close=Decimal(str(model.close)),
            volume=Decimal(str(model.volume)),
            quote_volume=Decimal(str(model.quote_volume)) if model.quote_volume else None,
            trades_count=model.trades_count.value
            if hasattr(model.trades_count, "value")
            else model.trades_count,
            is_complete=model.is_complete.value
            if hasattr(model.is_complete, "value")
            else model.is_complete,
        )

    def get_candle_count(self, symbol: str, timeframe: Timeframe) -> int:
        """Get count of candles for a symbol/timeframe.

        Args:
            symbol: Asset symbol
            timeframe: Candle timeframe

        Returns:
            Number of candles
        """
        return (
            self.session.query(CandleModel)
            .filter(
                and_(
                    CandleModel.symbol == symbol,
                    CandleModel.timeframe == timeframe.value,
                )
            )
            .count()
        )


class SignalRepository:
    """Repository for signal audit records."""

    def __init__(self, session: Session | None = None) -> None:
        """Initialize repository.

        Args:
            session: Database session (creates new if not provided)
        """
        self._session = session

    @property
    def session(self) -> Session:
        """Get database session."""
        if self._session is None:
            return get_session()
        return self._session

    def save_signal(self, audit: SignalAudit) -> str:
        """Save a signal audit record.

        Args:
            audit: SignalAudit to save

        Returns:
            Signal ID
        """
        signal_id = audit.id or str(uuid4())

        model = SignalModel(
            id=signal_id,
            timestamp=audit.timestamp,
            symbol=audit.symbol,
            asset_type=audit.asset_type.value,
            exchange=audit.exchange,
            timeframe=audit.timeframe.value,
            price=float(audit.price),
            signal=audit.signal.value,
            raw_score=audit.raw_score,
            calibrated_confidence=audit.calibrated_confidence,
            features=json.dumps(audit.features),
            market_regime=audit.market_regime.value,
            regime_confidence=audit.regime_confidence,
            timeframe_signals=json.dumps(audit.timeframe_signals),
            reason_codes=json.dumps(audit.reason_codes),
            contributing_factors=json.dumps(audit.contributing_factors),
            model_version=audit.model_version,
            data_version=audit.data_version,
        )

        self.session.merge(model)
        self.session.commit()

        logger.debug(f"Saved signal {signal_id} for {audit.symbol}")
        return signal_id

    def get_signals(
        self,
        symbol: str | None = None,
        timeframe: Timeframe | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[SignalAudit]:
        """Get signal audit records.

        Args:
            symbol: Filter by symbol
            timeframe: Filter by timeframe
            start: Start timestamp
            end: End timestamp
            limit: Maximum number of records

        Returns:
            List of SignalAudit records
        """
        query = self.session.query(SignalModel)

        if symbol:
            query = query.filter(SignalModel.symbol == symbol)
        if timeframe:
            query = query.filter(SignalModel.timeframe == timeframe.value)
        if start:
            query = query.filter(SignalModel.timestamp >= start)
        if end:
            query = query.filter(SignalModel.timestamp <= end)

        query = query.order_by(desc(SignalModel.timestamp))

        if limit:
            query = query.limit(limit)

        models = query.all()

        def _val(col):
            return col.value if hasattr(col, "value") else col

        return [
            SignalAudit(
                id=_val(m.id),
                timestamp=_val(m.timestamp),
                symbol=_val(m.symbol),
                asset_type=AssetType(_val(m.asset_type)),
                exchange=_val(m.exchange),
                timeframe=Timeframe(_val(m.timeframe)),
                price=Decimal(str(m.price)),
                signal=__import__("umae.domain.enums", fromlist=["SignalType"]).SignalType(
                    _val(m.signal)
                ),
                raw_score=float(_val(m.raw_score)),
                calibrated_confidence=float(_val(m.calibrated_confidence))
                if _val(m.calibrated_confidence) is not None
                else None,
                features=json.loads(_val(m.features)),
                market_regime=MarketRegime(_val(m.market_regime)),
                regime_confidence=float(_val(m.regime_confidence)),
                timeframe_signals=json.loads(_val(m.timeframe_signals)),
                reason_codes=json.loads(_val(m.reason_codes)),
                contributing_factors=json.loads(_val(m.contributing_factors))
                if _val(m.contributing_factors)
                else {},
                model_version=_val(m.model_version),
                data_version=_val(m.data_version),
            )
            for m in models
        ]


class AssetMetadataRepository:
    """Repository for asset metadata."""

    def __init__(self, session: Session | None = None) -> None:
        """Initialize repository.

        Args:
            session: Database session (creates new if not provided)
        """
        self._session = session

    @property
    def session(self) -> Session:
        """Get database session."""
        if self._session is None:
            return get_session()
        return self._session

    def save_metadata(self, metadata: AssetMetadata) -> None:
        """Save asset metadata.

        Args:
            metadata: AssetMetadata to save
        """
        model = AssetMetadataModel(
            symbol=metadata.symbol,
            asset_type=metadata.asset_type.value,
            exchange=metadata.exchange,
            timezone=metadata.timezone,
            base_currency=metadata.base_currency,
            quote_currency=metadata.quote_currency,
            tick_size=float(metadata.tick_size),
            lot_size=float(metadata.lot_size) if metadata.lot_size else None,
            fee_model=json.dumps(
                {
                    "taker_fee": str(metadata.fee_model.taker_fee),
                    "maker_fee": str(metadata.fee_model.maker_fee)
                    if metadata.fee_model.maker_fee
                    else None,
                }
            ),
            data_adapter=metadata.data_adapter,
            metadata_version=metadata.metadata_version,
        )

        self.session.merge(model)
        self.session.commit()

    def get_metadata(self, symbol: str) -> AssetMetadata | None:
        """Get asset metadata.

        Args:
            symbol: Asset symbol

        Returns:
            AssetMetadata or None
        """
        model = (
            self.session.query(AssetMetadataModel)
            .filter(AssetMetadataModel.symbol == symbol)
            .first()
        )

        if model is None:
            return None

        fee_data = json.loads(model.fee_model) if model.fee_model else {}

        return AssetMetadata(
            symbol=model.symbol,
            asset_type=AssetType(model.asset_type),
            exchange=model.exchange,
            timezone=model.timezone,
            base_currency=model.base_currency,
            quote_currency=model.quote_currency,
            tick_size=Decimal(str(model.tick_size)),
            lot_size=Decimal(str(model.lot_size)) if model.lot_size else None,
            fee_model=FeeModel(
                taker_fee=Decimal(fee_data.get("taker_fee", "0.001")),
                maker_fee=Decimal(fee_data["maker_fee"]) if fee_data.get("maker_fee") else None,
            ),
            data_adapter=model.data_adapter,
            metadata_version=model.metadata_version,
        )


class WatchlistRepository:
    """Repository for user watchlists."""

    def __init__(self, session: Session | None = None) -> None:
        """Initialize repository.

        Args:
            session: Database session (creates new if not provided)
        """
        self._session = session

    @property
    def session(self) -> Session:
        """Get database session."""
        if self._session is None:
            return get_session()
        return self._session

    def get_watchlist(self, user_id: int) -> list[str]:
        """Get user's watchlist.

        Args:
            user_id: Telegram user ID

        Returns:
            List of symbols
        """
        model = self.session.query(WatchlistModel).filter(WatchlistModel.user_id == user_id).first()

        if model is None:
            return []

        return json.loads(model.symbols)

    def add_to_watchlist(self, user_id: int, chat_id: int, symbol: str) -> bool:
        """Add symbol to user's watchlist.

        Args:
            user_id: Telegram user ID
            chat_id: Telegram chat ID
            symbol: Symbol to add

        Returns:
            True if added, False if already exists
        """
        model = self.session.query(WatchlistModel).filter(WatchlistModel.user_id == user_id).first()

        if model is None:
            model = WatchlistModel(
                user_id=user_id,
                chat_id=chat_id,
                symbols=json.dumps([symbol]),
            )
            self.session.add(model)
        else:
            symbols = json.loads(model.symbols)
            if symbol in symbols:
                return False
            symbols.append(symbol)
            model.symbols = json.dumps(symbols)
            model.updated_at = datetime.utcnow()

        self.session.commit()
        return True

    def remove_from_watchlist(self, user_id: int, symbol: str) -> bool:
        """Remove symbol from user's watchlist.

        Args:
            user_id: Telegram user ID
            symbol: Symbol to remove

        Returns:
            True if removed, False if not found
        """
        model = self.session.query(WatchlistModel).filter(WatchlistModel.user_id == user_id).first()

        if model is None:
            return False

        symbols = json.loads(model.symbols)
        if symbol not in symbols:
            return False

        symbols.remove(symbol)
        model.symbols = json.dumps(symbols)
        model.updated_at = datetime.utcnow()

        self.session.commit()
        return True
