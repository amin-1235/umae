"""Yahoo Finance data adapter for stocks, ETFs, and indices."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from umae.domain.enums import AssetType, Timeframe
from umae.domain.models import (
    AssetMetadata,
    Candle,
    CandleSet,
    FeeModel,
)
from umae.interfaces.base_adapter import BaseHTTPAdapter, RateLimiter

logger = logging.getLogger(__name__)

# Yahoo Finance timeframe mapping
TIMEFRAME_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1wk",
}

# Yahoo Finance valid intervals
VALID_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "1d", "1wk", "1mo"}

# Intraday limit (7 days for 1m, 60 days for others)
INTRADAY_LIMITS = {
    "1m": 7,
    "2m": 60,
    "5m": 60,
    "15m": 60,
    "30m": 60,
    "60m": 730,
}


class YahooFinanceAdapter:
    """Yahoo Finance data adapter for stocks and ETFs."""

    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize Yahoo Finance adapter.

        Args:
            rate_limiter: Rate limiter instance
        """
        self._http = BaseHTTPAdapter(
            base_url=self.BASE_URL,
            rate_limiter=rate_limiter or RateLimiter(max_requests=5, time_window=1.0),
        )

    @property
    def name(self) -> str:
        """Get adapter name."""
        return "yahoo"

    @property
    def supported_asset_types(self) -> frozenset[AssetType]:
        """Yahoo Finance supports stocks, forex, indices, and ETFs."""
        return frozenset({AssetType.STOCK, AssetType.FOREX, AssetType.INDEX, AssetType.ETF})

    async def close(self) -> None:
        """Close the adapter."""
        await self._http.close()

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol for Yahoo Finance.

        Args:
            symbol: Input symbol (e.g., "AAPL", "BTC-USD", "^GSPC")

        Returns:
            Yahoo Finance format symbol
        """
        # Yahoo uses - for crypto pairs (e.g., BTC-USD)
        # Indices start with ^ (e.g., ^GSPC)
        normalized = symbol.upper()

        # Convert / to - for crypto
        if "/" in normalized and "." not in normalized:
            normalized = normalized.replace("/", "-")

        return normalized

    def _map_timeframe(self, timeframe: Timeframe) -> str | None:
        """Map Timeframe to Yahoo Finance interval.

        Args:
            timeframe: Timeframe enum

        Returns:
            Yahoo interval string or None if not supported
        """
        mapping = {
            Timeframe.M1: "1m",
            Timeframe.M5: "5m",
            Timeframe.M15: "15m",
            Timeframe.M30: "30m",
            Timeframe.H1: "60m",
            Timeframe.D1: "1d",
            Timeframe.W1: "1wk",
        }
        return mapping.get(timeframe)

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: str,
        end: str,
    ) -> CandleSet:
        """Fetch candle data from Yahoo Finance.

        Args:
            symbol: Asset symbol
            timeframe: Candle timeframe
            start: Start date (ISO format)
            end: End date (ISO format)

        Returns:
            CandleSet with fetched candles
        """
        yahoo_symbol = self._normalize_symbol(symbol)
        interval = self._map_timeframe(timeframe)

        if not interval:
            msg = f"Timeframe {timeframe} not supported by Yahoo Finance"
            raise ValueError(msg)

        # Parse dates
        start_dt = self._http.parse_timestamp(start)
        end_dt = self._http.parse_timestamp(end)

        # Convert to Unix timestamps
        period1 = int(start_dt.timestamp())
        period2 = int(end_dt.timestamp())

        params = {
            "period1": period1,
            "period2": period2,
            "interval": interval,
            "includePrePost": "false",
        }

        try:
            data = await self._http._request("GET", f"/{yahoo_symbol}", params=params)
        except Exception:
            logger.exception(f"Failed to fetch candles for {symbol}")
            return CandleSet(
                symbol=symbol,
                timeframe=timeframe,
                source=self.name,
            )

        # Parse response
        candles = self._parse_response(data, yahoo_symbol)

        return self._http.build_candle_set(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            source=self.name,
        )

    def _parse_response(self, data: dict, symbol: str) -> list[Candle]:
        """Parse Yahoo Finance response.

        Args:
            data: Raw API response
            symbol: Symbol being parsed

        Returns:
            List of parsed Candle objects
        """
        candles: list[Candle] = []

        try:
            result = data.get("chart", {}).get("result", [])
            if not result:
                logger.warning(f"No chart data for {symbol}")
                return candles

            quote = result[0].get("indicators", {}).get("quote", [{}])[0]
            timestamps = result[0].get("timestamp", [])

            if not timestamps or not quote:
                return candles

            opens = quote.get("open", [])
            highs = quote.get("high", [])
            lows = quote.get("low", [])
            closes = quote.get("close", [])
            volumes = quote.get("volume", [])

            for i, ts in enumerate(timestamps):
                if i >= len(opens) or opens[i] is None:
                    continue

                candle = Candle(
                    timestamp=datetime.utcfromtimestamp(ts),
                    open=Decimal(str(opens[i])),
                    high=Decimal(str(highs[i])),
                    low=Decimal(str(lows[i])),
                    close=Decimal(str(closes[i])),
                    volume=Decimal(str(volumes[i] if i < len(volumes) and volumes[i] else 0)),
                    is_complete=True,
                )
                candles.append(candle)

        except (KeyError, IndexError, TypeError) as e:
            logger.warning(f"Error parsing Yahoo response for {symbol}: {e}")

        return candles

    async def get_asset_metadata(self, symbol: str) -> AssetMetadata:
        """Get metadata for a stock/ETF.

        Args:
            symbol: Asset symbol

        Returns:
            AssetMetadata for the symbol
        """
        yahoo_symbol = self._normalize_symbol(symbol)

        # Determine asset type
        asset_type = AssetType.STOCK
        if yahoo_symbol.startswith("^"):
            asset_type = AssetType.INDEX
        elif yahoo_symbol.endswith("-USD"):
            asset_type = AssetType.CRYPTO
        elif "." in yahoo_symbol:
            asset_type = AssetType.ETF

        # Extract base/quote currencies
        if asset_type == AssetType.CRYPTO:
            parts = yahoo_symbol.split("-")
            base_currency = parts[0] if parts else "UNKNOWN"
            quote_currency = parts[1] if len(parts) > 1 else "USD"
        else:
            base_currency = yahoo_symbol
            quote_currency = "USD"

        return AssetMetadata(
            symbol=symbol,
            asset_type=asset_type,
            exchange="yahoo",
            timezone="America/New_York",
            base_currency=base_currency,
            quote_currency=quote_currency,
            tick_size=Decimal("0.01"),
            fee_model=FeeModel(taker_fee=Decimal("0")),  # No direct fee on Yahoo
            data_adapter=self.name,
        )

    async def validate_symbol(self, symbol: str) -> bool:
        """Validate if a symbol exists on Yahoo Finance.

        Args:
            symbol: Asset symbol to validate

        Returns:
            True if symbol is valid
        """
        yahoo_symbol = self._normalize_symbol(symbol)

        try:
            # Try to fetch a small amount of data
            params = {
                "period1": int((datetime.utcnow() - timedelta(days=1)).timestamp()),
                "period2": int(datetime.utcnow().timestamp()),
                "interval": "1d",
            }
            data = await self._http._request("GET", f"/{yahoo_symbol}", params=params)
            result = data.get("chart", {}).get("result", [])
            return len(result) > 0
        except Exception:
            logger.debug(f"Symbol {symbol} not found on Yahoo Finance")
            return False

    async def get_supported_timeframes(self) -> list[Timeframe]:
        """Get list of supported timeframes.

        Returns:
            List of supported Timeframe enums
        """
        return [
            Timeframe.M1,
            Timeframe.M5,
            Timeframe.M15,
            Timeframe.M30,
            Timeframe.H1,
            Timeframe.D1,
            Timeframe.W1,
        ]
