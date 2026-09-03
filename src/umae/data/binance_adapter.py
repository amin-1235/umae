"""Binance data adapter for cryptocurrency data."""

from __future__ import annotations

import logging
from datetime import datetime
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

# Binance timeframe mapping
TIMEFRAME_MAP: dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M3: "3m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H2: "2h",
    Timeframe.H4: "4h",
    Timeframe.H6: "6h",
    Timeframe.H12: "12h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1w",
}

# Reverse map for parsing
TIMEFRAME_REVERSE: dict[str, Timeframe] = {v: k for k, v in TIMEFRAME_MAP.items()}

# Maximum candles per request
MAX_CANDLES_PER_REQUEST = 1000


class BinanceAdapter:
    """Binance cryptocurrency data adapter."""

    # Common quote currencies for symbol resolution
    _QUOTE_CURRENCIES = ("USDT", "BUSD", "USDC", "BTC", "ETH", "BNB", "USD", "EUR", "TUSD", "FDUSD")

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str = "https://api.binance.com",
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize Binance adapter.

        Args:
            api_key: API key (optional for public endpoints)
            api_secret: API secret (optional for public endpoints)
            base_url: Binance API base URL
            rate_limiter: Rate limiter instance
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self._http = BaseHTTPAdapter(
            base_url=base_url,
            rate_limiter=rate_limiter or RateLimiter(max_requests=10, time_window=1.0),
        )
        self._http._provider_name = "binance"
        self._supported_timeframes = list(TIMEFRAME_MAP.keys())
        self._symbol_cache: dict[str, str] = {}  # user_input → binance_symbol

    @property
    def name(self) -> str:
        """Get adapter name."""
        return "binance"

    async def close(self) -> None:
        """Close the adapter."""
        await self._http.close()

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize user input to Binance format.

        Handles:
          BTC → BTCUSDT (assumes USDT quote)
          BTCUSDT → BTCUSDT
          BTC/USDT → BTCUSDT
          BTC-USDT → BTCUSDT

        Args:
            symbol: User input symbol

        Returns:
            Binance format symbol (e.g., "BTCUSDT")
        """
        # Check cache first
        cache_key = symbol.upper().strip()
        if cache_key in self._symbol_cache:
            return self._symbol_cache[cache_key]

        # Remove common separators
        normalized = symbol.replace("/", "").replace("-", "").upper().strip()

        # If it already looks like a Binance symbol (ends with known quote), use as-is
        for quote in self._QUOTE_CURRENCIES:
            if normalized.endswith(quote) and len(normalized) > len(quote):
                self._symbol_cache[cache_key] = normalized
                return normalized

        # Short form like "BTC" → assume USDT quote
        # This is a heuristic; the real validation happens when we try to fetch
        candidate = normalized + "USDT"
        self._symbol_cache[cache_key] = candidate
        return candidate

    def _denormalize_symbol(self, binance_symbol: str) -> str:
        """Convert Binance symbol to standard format.

        Args:
            binance_symbol: Binance format (e.g., "BTCUSDT")

        Returns:
            Standard format (e.g., "BTC/USDT")
        """
        for quote in self._QUOTE_CURRENCIES:
            if binance_symbol.endswith(quote) and len(binance_symbol) > len(quote):
                base = binance_symbol[: -len(quote)]
                return f"{base}/{quote}"

        return binance_symbol

    async def resolve_symbol(self, user_input: str) -> str:
        """Resolve user input to a validated Binance symbol.

        Args:
            user_input: User-provided symbol string

        Returns:
            Validated Binance symbol

        Raises:
            ProviderError: If symbol cannot be resolved
        """
        from umae.interfaces.base_adapter import ProviderError

        candidate = self._normalize_symbol(user_input)

        # Try to validate by checking exchange info
        try:
            data = await self._http._request("GET", "/api/v3/exchangeInfo")
            valid_symbols = {s["symbol"] for s in data.get("symbols", [])}

            if candidate in valid_symbols:
                return candidate

            # Try common quotes
            for quote in self._QUOTE_CURRENCIES:
                test = user_input.replace("/", "").replace("-", "").upper() + quote
                if test in valid_symbols:
                    self._symbol_cache[user_input.upper().strip()] = test
                    return test

            raise ProviderError(
                category="SYMBOL_NOT_FOUND",
                message=f"Symbol '{user_input}' not found on Binance",
                provider="binance",
            )
        except ProviderError:
            raise
        except Exception:
            # If we can't reach exchange info, return best guess
            logger.warning("Cannot validate symbol %s against exchange info", user_input)
            return candidate

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: str,
        end: str,
    ) -> CandleSet:
        """Fetch candle data from Binance.

        Args:
            symbol: Asset symbol
            timeframe: Candle timeframe
            start: Start date (ISO format or timestamp)
            end: End date (ISO format or timestamp)

        Returns:
            CandleSet with fetched candles
        """
        binance_symbol = self._normalize_symbol(symbol)
        binance_timeframe = TIMEFRAME_MAP.get(timeframe)
        if not binance_timeframe:
            msg = f"Unsupported timeframe: {timeframe}"
            raise ValueError(msg)

        # Parse start and end times
        start_dt = self._http.parse_timestamp(start) if isinstance(start, str) else start
        end_dt = self._http.parse_timestamp(end) if isinstance(end, str) else end

        # Convert to milliseconds
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        all_candles: list[Candle] = []
        current_start = start_ms

        # Fetch in batches
        while current_start < end_ms:
            params = {
                "symbol": binance_symbol,
                "interval": binance_timeframe,
                "startTime": current_start,
                "endTime": end_ms,
                "limit": MAX_CANDLES_PER_REQUEST,
            }

            try:
                data = await self._http._request("GET", "/api/v3/klines", params=params)
            except Exception:
                logger.exception(f"Failed to fetch candles for {symbol}")
                break

            if not data:
                break

            # Parse candles
            for item in data:
                candle = self._parse_kline(item)
                if candle and candle.timestamp > start_dt:
                    all_candles.append(candle)

            # Move to next batch
            last_timestamp = data[-1][0]
            current_start = last_timestamp + 1

            # If we got fewer than requested, we've reached the end
            if len(data) < MAX_CANDLES_PER_REQUEST:
                break

        # Filter to end date
        all_candles = [c for c in all_candles if c.timestamp <= end_dt]

        return self._http.build_candle_set(
            symbol=self._denormalize_symbol(binance_symbol),
            timeframe=timeframe,
            candles=all_candles,
            source=self.name,
        )

    def _parse_kline(self, data: list) -> Candle | None:
        """Parse a Binance kline (candle) response.

        Binance kline format:
        [
            Open time,
            Open,
            High,
            Low,
            Close,
            Volume,
            Close time,
            Quote asset volume,
            Number of trades,
            Taker buy base asset volume,
            Taker buy quote asset volume,
            Ignore
        ]

        Args:
            data: Raw kline data array

        Returns:
            Parsed Candle or None if invalid
        """
        try:
            return Candle(
                timestamp=datetime.utcfromtimestamp(data[0] / 1000),
                open=Decimal(data[1]),
                high=Decimal(data[2]),
                low=Decimal(data[3]),
                close=Decimal(data[4]),
                volume=Decimal(data[5]),
                quote_volume=Decimal(data[7]),
                trades_count=int(data[8]),
                is_complete=True,
            )
        except (IndexError, ValueError, TypeError):
            logger.warning(f"Failed to parse kline: {data}")
            return None

    async def get_asset_metadata(self, symbol: str) -> AssetMetadata:
        """Get metadata for a cryptocurrency pair.

        Args:
            symbol: Asset symbol (e.g., "BTC/USDT")

        Returns:
            AssetMetadata for the symbol
        """
        binance_symbol = self._normalize_symbol(symbol)

        try:
            # Get exchange info for filters
            data = await self._http._request("GET", "/api/v3/exchangeInfo")

            # Find the symbol in the response
            for s in data.get("symbols", []):
                if s["symbol"] == binance_symbol:
                    # Extract base and quote currencies
                    base_currency = s.get("baseAsset", "")
                    quote_currency = s.get("quoteAsset", "")

                    # Find LOT_SIZE filter
                    tick_size = Decimal("0.01")  # default
                    lot_size = Decimal("0.001")  # default

                    for f in s.get("filters", []):
                        if f["filterType"] == "PRICE_FILTER":
                            tick_size = Decimal(f["tickSize"])
                        elif f["filterType"] == "LOT_SIZE":
                            lot_size = Decimal(f["stepSize"])

                    return AssetMetadata(
                        symbol=self._denormalize_symbol(binance_symbol),
                        asset_type=AssetType.CRYPTO,
                        exchange="binance",
                        timezone="UTC",
                        base_currency=base_currency,
                        quote_currency=quote_currency,
                        tick_size=tick_size,
                        lot_size=lot_size,
                        fee_model=FeeModel(
                            taker_fee=Decimal("0.001"),
                            maker_fee=Decimal("0.001"),
                        ),
                        data_adapter=self.name,
                    )
        except Exception:
            logger.exception(f"Failed to get metadata for {symbol}")

        # Return default metadata
        return AssetMetadata(
            symbol=self._denormalize_symbol(binance_symbol),
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            timezone="UTC",
            base_currency="UNKNOWN",
            quote_currency="UNKNOWN",
            tick_size=Decimal("0.01"),
            data_adapter=self.name,
        )

    async def validate_symbol(self, symbol: str) -> bool:
        """Validate if a symbol is supported by Binance.

        Args:
            symbol: Asset symbol to validate

        Returns:
            True if symbol is valid and supported
        """
        binance_symbol = self._normalize_symbol(symbol)

        try:
            data = await self._http._request("GET", "/api/v3/exchangeInfo")
            symbols = [s["symbol"] for s in data.get("symbols", [])]
            return binance_symbol in symbols
        except Exception:
            logger.exception(f"Failed to validate symbol {symbol}")
            return False

    async def get_supported_timeframes(self) -> list[Timeframe]:
        """Get list of supported timeframes.

        Returns:
            List of supported Timeframe enums
        """
        return self._supported_timeframes.copy()
