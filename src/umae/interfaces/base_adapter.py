"""Base adapter with common functionality."""

from __future__ import annotations

import asyncio
import logging
import ssl
from datetime import datetime
from typing import TYPE_CHECKING, Any

import aiohttp
import certifi

from umae.domain.models import Candle, CandleSet

if TYPE_CHECKING:
    from umae.domain.enums import Timeframe

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Typed error for data provider failures."""

    def __init__(self, category: str, message: str, provider: str = "") -> None:
        self.category = category
        self.provider = provider
        super().__init__(f"[{category}] {message}")


class TLSError(ProviderError):
    """TLS certificate verification failed."""

    pass


class ProviderUnavailableError(ProviderError):
    """Provider is unreachable."""

    pass


class DoHResolver(aiohttp.abc.AbstractResolver):
    """DNS-over-HTTPS resolver to bypass ISP DNS hijacking.

    Resolves hostnames via Cloudflare/Google DoH, falling back to
    system DNS if DoH is unavailable. Cache prevents repeated lookups.
    """

    _DOH_URLS = (
        "https://cloudflare-dns.com/dns-query",
        "https://dns.google/resolve",
    )

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: int = 2,  # socket.AF_INET
    ) -> list[aiohttp.abc.ResolveResult]:
        """Resolve hostname via DoH, with caching and system DNS fallback."""
        ip: str | None = self._cache.get(host)

        if not ip:
            import json
            import urllib.request

            for doh_url in self._DOH_URLS:
                url = f"{doh_url}?name={host}&type=A"
                try:
                    req = urllib.request.Request(
                        url,
                        headers={"Accept": "application/dns-json"},
                    )
                    resp = urllib.request.urlopen(req, timeout=5)
                    data = json.loads(resp.read())
                    for ans in data.get("Answer", []):
                        if ans.get("type") == 1:
                            ip = str(ans["data"])
                            self._cache[host] = ip
                            logger.info("DoH resolved %s -> %s", host, ip)
                            break
                    if ip:
                        break
                except Exception:
                    continue

        if not ip:
            # System DNS fallback
            import socket

            try:
                infos = socket.getaddrinfo(host, port or 443, family, socket.SOCK_STREAM)
                if infos:
                    ip = str(infos[0][4][0])
                    logger.info("System DNS resolved %s -> %s", host, ip)
            except Exception:
                logger.warning("DNS resolution failed for %s", host)
                ip = host  # let aiohttp handle the error

        assert ip is not None
        return [
            {
                "hostname": host,
                "host": ip,
                "port": port or 443,
                "family": family,
                "proto": 6,
                "flags": 0,
            }
        ]

    async def close(self) -> None:
        """No-op cleanup."""


class RateLimiter:
    """Simple rate limiter using token bucket."""

    def __init__(self, max_requests: int, time_window: float) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests in time window
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.tokens: float = max_requests
        self.last_refill: float = 0.0  # lazy init on first acquire
        self._lock = asyncio.Lock()
        self._initialized = False

    def _get_time(self) -> float:
        """Get current event loop time, initializing if needed."""
        try:
            return asyncio.get_event_loop().time()
        except RuntimeError:
            import time

            return time.monotonic()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = self._get_time()
            if not self._initialized:
                self.last_refill = now
                self._initialized = True
            elapsed = now - self.last_refill
            if elapsed > 0:
                self.tokens = min(
                    self.max_requests,
                    self.tokens + (elapsed / self.time_window) * self.max_requests,
                )
                self.last_refill = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) * (self.time_window / self.max_requests)
                await asyncio.sleep(wait_time)
                self.tokens = 1

            self.tokens -= 1


def _build_ssl_context(ca_bundle: str | None = None) -> ssl.SSLContext:
    """Build a verified SSL context.

    Args:
        ca_bundle: Optional path to a custom CA bundle file.

    Returns:
        Configured SSLContext with verification enabled.
    """
    ctx = ssl.create_default_context()
    if ca_bundle:
        import os

        if not os.path.isfile(ca_bundle):
            msg = f"CA bundle not found: {ca_bundle}"
            raise FileNotFoundError(msg)
        ctx.load_verify_locations(ca_bundle)
        logger.info("Using custom CA bundle: %s", ca_bundle)
    else:
        # Use certifi bundle as fallback if system CA is unavailable
        try:
            ctx.load_verify_locations(certifi.where())
        except Exception:
            logger.warning("certifi bundle load failed, using system default")
    return ctx


class BaseHTTPAdapter:
    """Base HTTP adapter with rate limiting and retry logic."""

    def __init__(
        self,
        base_url: str,
        rate_limiter: RateLimiter | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        ssl_verify: bool = True,
        ca_bundle: str | None = None,
    ) -> None:
        """Initialize base adapter.

        Args:
            base_url: Base URL for API calls
            rate_limiter: Rate limiter instance
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            ssl_verify: Whether to verify TLS certificates (default: True)
            ca_bundle: Optional path to custom CA bundle
        """
        self.base_url = base_url
        self.rate_limiter = rate_limiter or RateLimiter(max_requests=10, time_window=1.0)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None
        self._ssl_verify = ssl_verify
        self._ssl_context: ssl.SSLContext | None = None
        if ssl_verify:
            self._ssl_context = _build_ssl_context(ca_bundle)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with DoH DNS resolver."""
        if self._session is None or self._session.closed:
            resolver = DoHResolver()
            connector_kwargs: dict[str, Any] = {"resolver": resolver}
            if self._ssl_context:
                connector_kwargs["ssl"] = self._ssl_context
            connector = aiohttp.TCPConnector(**connector_kwargs)
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector,
            )
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def _classify_error(self, exc: Exception) -> ProviderError:
        """Classify an HTTP error into a typed ProviderError."""
        provider = getattr(self, "_provider_name", "unknown")

        if isinstance(exc, aiohttp.ClientConnectorCertificateError):
            return ProviderError(
                category="DATA_PROVIDER_TLS_ERROR",
                message=f"TLS certificate verification failed for {provider}. "
                "The network may be intercepted by an ISP or firewall.",
                provider=provider,
            )
        if isinstance(exc, aiohttp.ClientConnectorError):
            return ProviderError(
                category="DATA_PROVIDER_UNAVAILABLE",
                message=f"Cannot connect to {provider}: {exc}",
                provider=provider,
            )
        if isinstance(exc, aiohttp.ClientResponseError):
            status = exc.status
            if status == 400:
                return ProviderError(
                    category="UNSUPPORTED_ASSET",
                    message=f"{provider} rejected request (HTTP {status}): {exc.message}",
                    provider=provider,
                )
            if status == 429:
                return ProviderError(
                    category="RATE_LIMITED",
                    message=f"{provider} rate limited (HTTP {status}): {exc.message}",
                    provider=provider,
                )
            return ProviderError(
                category="DATA_PROVIDER_HTTP_ERROR",
                message=f"{provider} returned HTTP {status}: {exc.message}",
                provider=provider,
            )
        if isinstance(exc, asyncio.TimeoutError):
            return ProviderError(
                category="DATA_PROVIDER_TIMEOUT",
                message=f"Request to {provider} timed out",
                provider=provider,
            )
        if isinstance(exc, aiohttp.ClientError):
            return ProviderError(
                category="DATA_PROVIDER_ERROR",
                message=f"{provider} error: {exc}",
                provider=provider,
            )
        return ProviderError(
            category="DATA_PROVIDER_ERROR",
            message=f"{type(exc).__name__}: {exc}",
            provider=provider,
        )

    def _should_retry(self, exc: Exception) -> bool:
        """Determine if a request should be retried.

        Non-retryable:
          - TLS certificate errors
          - Connection errors (cannot reach server)
          - SSL errors
          - HTTP 400 Bad Request (unsupported symbol / invalid params)
          - HTTP 401 Unauthorized
          - HTTP 403 Forbidden
          - HTTP 404 Not Found

        Retryable:
          - HTTP 408 Request Timeout
          - HTTP 429 Too Many Requests
          - HTTP 5xx Server Errors
          - asyncio.TimeoutError (transport-level timeout)
          - Other transient client errors
        """
        # Never retry TLS or connection-level failures
        if isinstance(
            exc,
            (
                aiohttp.ClientConnectorCertificateError,
                aiohttp.ClientConnectorError,
                ssl.SSLError,
            ),
        ):
            return False

        # Check HTTP status codes for ClientResponseError
        if isinstance(exc, aiohttp.ClientResponseError):
            status = exc.status
            # Permanent client errors — do not retry
            if status in (400, 401, 403, 404):
                return False
            # Retryable: 408, 429, 5xx; others — do not retry
            return status == 408 or status == 429 or status >= 500

        # Timeouts and other transient errors — retry
        return isinstance(exc, (aiohttp.ClientError, asyncio.TimeoutError))

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Make HTTP request with rate limiting.

        Args:
            method: HTTP method
            path: API path
            params: Query parameters
            headers: Additional headers

        Returns:
            JSON response data

        Raises:
            ProviderError: On any connection/HTTP failure
        """
        await self.rate_limiter.acquire()
        session = await self._get_session()
        url = f"{self.base_url}{path}"

        logger.debug("HTTP %s %s params=%s", method, url, params)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with session.request(method, url, params=params, headers=headers) as resp:
                    # Check status before raising — enables Retry-After extraction
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait_time = min(float(retry_after) if retry_after else 2**attempt, 30)
                        logger.warning(
                            "Rate limited (attempt %d/%d). Retrying in %.1fs",
                            attempt + 1,
                            self.max_retries,
                            wait_time,
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_exc = exc
                if not self._should_retry(exc):
                    raise self._classify_error(exc) from exc
                wait_time = min(2**attempt, 10)
                logger.warning(
                    "Request failed (attempt %d/%d): %s. Retrying in %ds",
                    attempt + 1,
                    self.max_retries,
                    type(exc).__name__,
                    wait_time,
                )
                await asyncio.sleep(wait_time)

        assert last_exc is not None
        raise self._classify_error(last_exc) from last_exc

    @staticmethod
    def parse_timestamp(ts: str | int | float) -> datetime:
        """Parse timestamp to datetime.

        Args:
            ts: Timestamp as string (ISO), int (unix), or float (unix)

        Returns:
            Parsed datetime in UTC
        """
        if isinstance(ts, str):
            # Try ISO format first
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return dt.replace(tzinfo=None)  # Return naive UTC
            except ValueError:
                pass
            # Try unix timestamp as string
            try:
                ts = float(ts)
            except ValueError:
                msg = f"Cannot parse timestamp: {ts}"
                raise ValueError(msg) from None

        if isinstance(ts, (int, float)):
            return datetime.utcfromtimestamp(ts)

        msg = f"Invalid timestamp type: {type(ts)}"
        raise TypeError(msg)

    @staticmethod
    def timeframe_to_string(tf: Timeframe) -> str:
        """Convert timeframe to common string formats."""
        return tf.value

    @staticmethod
    def parse_candle_data(
        data: dict[str, Any],
        timestamp_key: str = "timestamp",
        open_key: str = "open",
        high_key: str = "high",
        low_key: str = "low",
        close_key: str = "close",
        volume_key: str = "volume",
        quote_volume_key: str = "quote_volume",
        trades_key: str = "trades",
    ) -> Candle:
        """Parse candle data from provider format.

        Args:
            data: Raw candle data dictionary
            timestamp_key: Key for timestamp
            open_key: Key for open price
            high_key: Key for high price
            low_key: Key for low price
            close_key: Key for close price
            volume_key: Key for volume
            quote_volume_key: Key for quote volume
            trades_key: Key for trades count

        Returns:
            Parsed Candle object
        """
        from decimal import Decimal

        return Candle(
            timestamp=BaseHTTPAdapter.parse_timestamp(data[timestamp_key]),
            open=Decimal(str(data[open_key])),
            high=Decimal(str(data[high_key])),
            low=Decimal(str(data[low_key])),
            close=Decimal(str(data[close_key])),
            volume=Decimal(str(data.get(volume_key, 0))),
            quote_volume=(
                Decimal(str(data[quote_volume_key])) if data.get(quote_volume_key) else None
            ),
            trades_count=int(data[trades_key]) if trades_key in data else None,
            is_complete=True,
        )

    def build_candle_set(
        self,
        symbol: str,
        timeframe: Timeframe,
        candles: list[Candle],
        source: str,
        data_version: str = "",
    ) -> CandleSet:
        """Build a CandleSet from parsed candles.

        Args:
            symbol: Asset symbol
            timeframe: Candle timeframe
            candles: List of parsed candles
            source: Data source name
            data_version: Version identifier

        Returns:
            CandleSet object
        """
        # Sort by timestamp
        candles.sort(key=lambda c: c.timestamp)

        return CandleSet(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            source=source,
            data_version=data_version
            or f"{source}_{datetime.utcnow().strftime('%Y%m%d')}_{len(candles)}",
        )
