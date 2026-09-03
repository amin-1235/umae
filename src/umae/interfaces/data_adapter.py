"""Data adapter interface for UMAE."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from umae.domain.enums import Timeframe
    from umae.domain.models import AssetMetadata, CandleSet


@runtime_checkable
class DataAdapter(Protocol):
    """Protocol for data adapter implementations."""

    @property
    def name(self) -> str:
        """Get adapter name."""
        ...

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: str,
        end: str,
    ) -> CandleSet:
        """Fetch candle data from provider.

        Args:
            symbol: Asset symbol (e.g., "BTC/USDT", "AAPL")
            timeframe: Candle timeframe
            start: Start date as ISO format string
            end: End date as ISO format string

        Returns:
            CandleSet with fetched candles
        """
        ...

    async def get_asset_metadata(self, symbol: str) -> AssetMetadata:
        """Get metadata for an asset.

        Args:
            symbol: Asset symbol

        Returns:
            AssetMetadata for the symbol
        """
        ...

    async def validate_symbol(self, symbol: str) -> bool:
        """Validate if a symbol is supported.

        Args:
            symbol: Asset symbol to validate

        Returns:
            True if symbol is valid and supported
        """
        ...

    async def get_supported_timeframes(self) -> list[Timeframe]:
        """Get list of supported timeframes.

        Returns:
            List of supported Timeframe enums
        """
        ...
