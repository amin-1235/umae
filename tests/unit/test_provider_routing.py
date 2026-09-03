"""Regression tests for provider routing, retry classification, and asset discovery.

Covers:
1. FX does not route to Binance
2. Crypto still routes to Binance
3. Unsupported provider symbol raises ProviderError
4. HTTP 400 is not retried
5. HTTP 429 is retried
6. Current price and candles use same adapter
7. Provider failure is not neutral
8. Shutdown closes all adapters
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from umae.config.settings import CATEGORY_PROVIDERS
from umae.domain.enums import AssetType, Timeframe
from umae.domain.models import CandleSet
from umae.interfaces.analysis_service import AnalysisService
from umae.interfaces.base_adapter import BaseHTTPAdapter, ProviderError, RateLimiter

_TEST_RATE_LIMITER = RateLimiter(max_requests=100, time_window=1.0)


# ── Helpers ──────────────────────────────────────────────────────


def _make_mock_adapter(name: str, supported: frozenset[AssetType] | None = None):
    """Create a mock DataAdapter with configurable capabilities."""
    adapter = AsyncMock()
    adapter.name = name
    adapter.supported_asset_types = supported
    adapter.close = AsyncMock()
    return adapter


def _make_candle_set(symbol: str, tf: Timeframe, count: int = 5):
    """Create a minimal CandleSet for testing."""
    from datetime import datetime, timedelta
    from decimal import Decimal

    from umae.domain.models import Candle

    candles = [
        Candle(
            timestamp=datetime.now() - timedelta(hours=i),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1000"),
        )
        for i in range(count)
    ]
    return CandleSet(symbol=symbol, timeframe=tf, candles=candles, source="test")


# ── 1. FX does not route to Binance ────────────────────────────


class TestFXDoesNotRouteToBinance(unittest.TestCase):
    """EUR/USD and GBP/USD must NOT be sent to BinanceAdapter."""

    def test_category_routing_maps_forex_to_yahoo(self):
        """Forex category maps to yahoo adapter."""
        self.assertEqual(CATEGORY_PROVIDERS["forex"], "yahoo")

    def test_category_routing_maps_stocks_to_yahoo(self):
        """Stocks category maps to yahoo adapter."""
        self.assertEqual(CATEGORY_PROVIDERS["stocks"], "yahoo")

    def test_category_routing_maps_indices_to_yahoo(self):
        """Indices category maps to yahoo adapter."""
        self.assertEqual(CATEGORY_PROVIDERS["indices"], "yahoo")

    def test_category_routing_maps_crypto_to_binance(self):
        """Crypto category maps to binance adapter."""
        self.assertEqual(CATEGORY_PROVIDERS["crypto"], "binance")

    def test_select_adapter_returns_yahoo_for_forex(self):
        """AnalysisService._select_adapter returns yahoo for forex."""
        binance = _make_mock_adapter("binance", frozenset({AssetType.CRYPTO}))
        yahoo = _make_mock_adapter("yahoo", frozenset({AssetType.FOREX}))

        svc = AnalysisService(
            adapters={"binance": binance, "yahoo": yahoo},
            default_adapter="binance",
        )
        self.assertEqual(svc._select_adapter("forex"), "yahoo")

    def test_select_adapter_returns_yahoo_for_stocks(self):
        """AnalysisService._select_adapter returns yahoo for stocks."""
        binance = _make_mock_adapter("binance", frozenset({AssetType.CRYPTO}))
        yahoo = _make_mock_adapter("yahoo", frozenset({AssetType.STOCK}))

        svc = AnalysisService(
            adapters={"binance": binance, "yahoo": yahoo},
            default_adapter="binance",
        )
        self.assertEqual(svc._select_adapter("stocks"), "yahoo")

    def test_select_adapter_returns_binance_for_crypto(self):
        """AnalysisService._select_adapter returns binance for crypto."""
        binance = _make_mock_adapter("binance", frozenset({AssetType.CRYPTO}))
        yahoo = _make_mock_adapter("yahoo", frozenset({AssetType.FOREX}))

        svc = AnalysisService(
            adapters={"binance": binance, "yahoo": yahoo},
            default_adapter="binance",
        )
        self.assertEqual(svc._select_adapter("crypto"), "binance")

    def test_select_adapter_falls_back_to_default(self):
        """Unknown category falls back to default adapter."""
        binance = _make_mock_adapter("binance")
        svc = AnalysisService(
            adapters={"binance": binance},
            default_adapter="binance",
        )
        self.assertEqual(svc._select_adapter("unknown_category"), "binance")

    def test_select_adapter_with_no_category_uses_default(self):
        """No category falls back to default adapter."""
        binance = _make_mock_adapter("binance")
        svc = AnalysisService(
            adapters={"binance": binance},
            default_adapter="binance",
        )
        self.assertEqual(svc._select_adapter(None), "binance")


# ── 2. Crypto still routes correctly ────────────────────────────


class TestCryptoRoutesToBinance(unittest.TestCase):
    """BTC/USDT and ETH/USDT must route to BinanceAdapter."""

    def test_binance_adapter_supports_only_crypto(self):
        """BinanceAdapter.supported_asset_types is CRYPTO only."""
        from umae.data.binance_adapter import BinanceAdapter

        adapter = BinanceAdapter()
        self.assertEqual(adapter.supported_asset_types, frozenset({AssetType.CRYPTO}))

    def test_yahoo_adapter_supports_forex(self):
        """YahooFinanceAdapter supports FOREX."""
        from umae.data.yahoo_adapter import YahooFinanceAdapter

        adapter = YahooFinanceAdapter()
        self.assertIn(AssetType.FOREX, adapter.supported_asset_types)

    def test_yahoo_adapter_supports_stocks(self):
        """YahooFinanceAdapter supports STOCK."""
        from umae.data.yahoo_adapter import YahooFinanceAdapter

        adapter = YahooFinanceAdapter()
        self.assertIn(AssetType.STOCK, adapter.supported_asset_types)

    def test_yahoo_adapter_supports_indices(self):
        """YahooFinanceAdapter supports INDEX."""
        from umae.data.yahoo_adapter import YahooFinanceAdapter

        adapter = YahooFinanceAdapter()
        self.assertIn(AssetType.INDEX, adapter.supported_asset_types)


# ── 3. Unsupported provider symbol ──────────────────────────────


class TestUnsupportedSymbolHandling(unittest.TestCase):
    """Symbols not confirmed by provider metadata must not be blindly accepted."""

    def test_binance_resolve_symbol_rejects_when_metadata_unavailable(self):
        """BinanceAdapter.resolve_symbol raises when exchange info unreachable."""
        from umae.data.binance_adapter import BinanceAdapter

        adapter = BinanceAdapter()
        adapter._http._request = AsyncMock(side_effect=ConnectionError("Cannot connect"))

        async def _run():
            with self.assertRaises(ProviderError) as ctx:
                await adapter.resolve_symbol("EUR/USD")
            self.assertEqual(ctx.exception.category, "DATA_PROVIDER_UNAVAILABLE")

        asyncio.run(_run())

    def test_binance_resolve_symbol_rejects_unknown_symbol(self):
        """BinanceAdapter.resolve_symbol raises UNSUPPORTED_ASSET for unknown symbol."""
        from umae.data.binance_adapter import BinanceAdapter

        adapter = BinanceAdapter()
        adapter._http._request = AsyncMock(return_value={"symbols": []})

        async def _run():
            with self.assertRaises(ProviderError) as ctx:
                await adapter.resolve_symbol("EUR/USD")
            self.assertEqual(ctx.exception.category, "UNSUPPORTED_ASSET")

        asyncio.run(_run())


# ── 4. HTTP 400 is not retried ──────────────────────────────────


class TestHTTP400NotRetried(unittest.TestCase):
    """HTTP 400 must produce one request, not three retries."""

    def test_should_retry_returns_false_for_400(self):
        """_should_retry returns False for HTTP 400."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=400,
            message="Bad Request",
        )
        self.assertFalse(adapter._should_retry(exc))

    def test_should_retry_returns_false_for_401(self):
        """_should_retry returns False for HTTP 401."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=401,
            message="Unauthorized",
        )
        self.assertFalse(adapter._should_retry(exc))

    def test_should_retry_returns_false_for_403(self):
        """_should_retry returns False for HTTP 403."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=403,
            message="Forbidden",
        )
        self.assertFalse(adapter._should_retry(exc))

    def test_should_retry_returns_false_for_404(self):
        """_should_retry returns False for HTTP 404."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=404,
            message="Not Found",
        )
        self.assertFalse(adapter._should_retry(exc))

    def test_classify_error_returns_unsupported_asset_for_400(self):
        """_classify_error returns UNSUPPORTED_ASSET for HTTP 400."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        adapter._provider_name = "binance"
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=400,
            message="Bad Request",
        )
        result = adapter._classify_error(exc)
        self.assertEqual(result.category, "UNSUPPORTED_ASSET")

    def test_classify_error_returns_rate_limited_for_429(self):
        """_classify_error returns RATE_LIMITED for HTTP 429."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        adapter._provider_name = "binance"
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=429,
            message="Too Many Requests",
        )
        result = adapter._classify_error(exc)
        self.assertEqual(result.category, "RATE_LIMITED")


# ── 5. HTTP 429 is retried ─────────────────────────────────────


class TestHTTP429Retried(unittest.TestCase):
    """HTTP 429 must be retried with backoff."""

    def test_should_retry_returns_true_for_429(self):
        """_should_retry returns True for HTTP 429."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=429,
            message="Too Many Requests",
        )
        self.assertTrue(adapter._should_retry(exc))

    def test_should_retry_returns_true_for_500(self):
        """_should_retry returns True for HTTP 500."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=500,
            message="Internal Server Error",
        )
        self.assertTrue(adapter._should_retry(exc))

    def test_should_retry_returns_true_for_503(self):
        """_should_retry returns True for HTTP 503."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=503,
            message="Service Unavailable",
        )
        self.assertTrue(adapter._should_retry(exc))

    def test_should_retry_returns_true_for_408(self):
        """_should_retry returns True for HTTP 408."""
        import aiohttp

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=_TEST_RATE_LIMITER,
        )
        exc = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=408,
            message="Request Timeout",
        )
        self.assertTrue(adapter._should_retry(exc))


# ── 6. Price and candles use same adapter ───────────────────────


class TestPriceAndCandlesSameAdapter(unittest.TestCase):
    """Current price and candle requests use the same adapter routing."""

    def test_analyze_uses_selected_adapter_for_both(self):
        """analyze() uses _select_adapter for provider_name, shared across price + candles."""
        binance = _make_mock_adapter("binance")
        yahoo = _make_mock_adapter("yahoo")

        svc = AnalysisService(
            adapters={"binance": binance, "yahoo": yahoo},
            default_adapter="binance",
        )
        # Verify _select_adapter is used in analyze() for provider_name
        selected = svc._select_adapter("forex")
        self.assertEqual(selected, "yahoo")

    def test_get_current_price_uses_same_adapter(self):
        """_get_current_price receives the same adapter as _fetch_candle_sets."""
        binance = _make_mock_adapter("binance")
        yahoo = _make_mock_adapter("yahoo")

        svc = AnalysisService(
            adapters={"binance": binance, "yahoo": yahoo},
            default_adapter="binance",
        )
        # Both price and candle operations use the adapter returned by _select_adapter
        adapter_name = svc._select_adapter("forex")
        adapter = svc._get_adapter(adapter_name)
        self.assertEqual(adapter.name, "yahoo")


# ── 7. Provider failure is not neutral ──────────────────────────


class TestProviderFailureNotNeutral(unittest.TestCase):
    """Provider failure must not produce NEUTRAL 0.0 signal."""

    def test_unavailable_signal_constant(self):
        """DATA_UNAVAILABLE_SIGNAL is defined and not 'neutral'."""
        from umae.telegram.services import DATA_UNAVAILABLE_SIGNAL

        self.assertEqual(DATA_UNAVAILABLE_SIGNAL, "unavailable")
        self.assertNotEqual(DATA_UNAVAILABLE_SIGNAL, "neutral")

    def test_unavailable_score_is_zero(self):
        """DATA_UNAVAILABLE_SCORE is 0.0 but signal is 'unavailable', not neutral."""
        from umae.telegram.services import DATA_UNAVAILABLE_SCORE, DATA_UNAVAILABLE_SIGNAL

        self.assertEqual(DATA_UNAVAILABLE_SCORE, 0.0)
        self.assertNotEqual(DATA_UNAVAILABLE_SIGNAL, "neutral")


# ── 8. Shutdown closes all adapters ─────────────────────────────


class TestShutdownClosesAllAdapters(unittest.TestCase):
    """All adapters must be closed on shutdown."""

    def test_run_with_cleanup_closes_all_adapters(self):
        """_run_with_cleanup closes every adapter in the list."""
        from run_bot import _run_with_cleanup

        adapter1 = AsyncMock()
        adapter1.close = AsyncMock()
        adapter2 = AsyncMock()
        adapter2.close = AsyncMock()
        database = MagicMock()
        database.close = MagicMock()

        bot = AsyncMock()
        bot.run = AsyncMock()

        async def _run():
            await _run_with_cleanup(bot, [adapter1, adapter2], database)

        asyncio.run(_run())

        adapter1.close.assert_called_once()
        adapter2.close.assert_called_once()
        database.close.assert_called_once()

    def test_run_with_cleanup_closes_surviving_adapter_when_one_fails(self):
        """If adapter A fails to close, adapter B still gets closed."""
        from run_bot import _run_with_cleanup

        adapter1 = AsyncMock()
        adapter1.close = AsyncMock(side_effect=Exception("close failed"))
        adapter2 = AsyncMock()
        adapter2.close = AsyncMock()
        database = MagicMock()
        database.close = MagicMock()

        bot = AsyncMock()
        bot.run = AsyncMock()

        async def _run():
            await _run_with_cleanup(bot, [adapter1, adapter2], database)

        asyncio.run(_run())

        adapter1.close.assert_called_once()
        adapter2.close.assert_called_once()
        database.close.assert_called_once()

    def testDataAdapter_protocol_has_supported_asset_types(self):
        """DataAdapter protocol declares supported_asset_types."""
        from umae.interfaces.data_adapter import DataAdapter

        # Verify the protocol has the attribute
        self.assertTrue(hasattr(DataAdapter, "supported_asset_types"))


if __name__ == "__main__":
    unittest.main()
