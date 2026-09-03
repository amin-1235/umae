"""Tests for ProviderError hierarchy, symbol resolution, and error display."""

from __future__ import annotations

import asyncio
import ssl
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import aiohttp

from umae.data.binance_adapter import BinanceAdapter
from umae.domain.models import Candle, CandleSet, Timeframe
from umae.interfaces.analysis_service import AnalysisService
from umae.interfaces.base_adapter import (
    ProviderError,
    RateLimiter,
    _build_ssl_context,
)
from umae.telegram.formatter import TelegramFormatter


def _make_adapter() -> BinanceAdapter:
    rl = RateLimiter(max_requests=10, time_window=1.0)
    return BinanceAdapter(rate_limiter=rl)


def _tls_exc() -> aiohttp.ClientConnectorCertificateError:
    inner = ssl.SSLCertVerificationError("hostname mismatch")
    return aiohttp.ClientConnectorCertificateError(
        connection_key=MagicMock(host="api.binance.com"),
        certificate_error=inner,
    )


def _conn_exc() -> aiohttp.ClientConnectorError:
    return aiohttp.ClientConnectorError(
        connection_key=MagicMock(host="api.binance.com"),
        os_error=ConnectionRefusedError(),
    )


class TestProviderErrorHierarchy(unittest.TestCase):
    def test_tls_error_category(self):
        err = ProviderError(
            category="DATA_PROVIDER_TLS_ERROR",
            message="TLS certificate verification failed",
            provider="binance",
        )
        self.assertEqual(err.category, "DATA_PROVIDER_TLS_ERROR")
        self.assertEqual(err.provider, "binance")
        self.assertIn("TLS", str(err))

    def test_unavailable_error_category(self):
        err = ProviderError(
            category="DATA_PROVIDER_UNAVAILABLE",
            message="Connection refused",
            provider="yahoo",
        )
        self.assertEqual(err.category, "DATA_PROVIDER_UNAVAILABLE")

    def test_timeout_error_category(self):
        err = ProviderError(
            category="DATA_PROVIDER_TIMEOUT",
            message="Request timed out",
            provider="binance",
        )
        self.assertEqual(err.category, "DATA_PROVIDER_TIMEOUT")

    def test_http_error_category(self):
        err = ProviderError(
            category="DATA_PROVIDER_HTTP_ERROR",
            message="HTTP 429: Rate limited",
            provider="binance",
        )
        self.assertEqual(err.category, "DATA_PROVIDER_HTTP_ERROR")

    def test_is_exception(self):
        err = ProviderError(
            category="DATA_PROVIDER_ERROR",
            message="test",
            provider="test",
        )
        self.assertIsInstance(err, Exception)

    def test_string_repr(self):
        err = ProviderError(
            category="DATA_PROVIDER_TLS_ERROR",
            message="TLS cert mismatch",
            provider="binance",
        )
        s = str(err)
        self.assertIn("DATA_PROVIDER_TLS_ERROR", s)
        self.assertIn("TLS cert mismatch", s)


class TestErrorClassification(unittest.TestCase):
    def test_tls_error_classification(self):
        adapter = _make_adapter()
        result = adapter._http._classify_error(_tls_exc())
        self.assertEqual(result.category, "DATA_PROVIDER_TLS_ERROR")
        self.assertEqual(result.provider, "binance")

    def test_connection_error_classification(self):
        adapter = _make_adapter()
        result = adapter._http._classify_error(_conn_exc())
        self.assertEqual(result.category, "DATA_PROVIDER_UNAVAILABLE")

    def test_timeout_error_classification(self):
        adapter = _make_adapter()
        exc = TimeoutError("request timed out")
        result = adapter._http._classify_error(exc)
        self.assertEqual(result.category, "DATA_PROVIDER_TIMEOUT")

    def test_generic_error_classification(self):
        adapter = _make_adapter()
        exc = ValueError("something went wrong")
        result = adapter._http._classify_error(exc)
        self.assertEqual(result.category, "DATA_PROVIDER_ERROR")

    def test_tls_error_is_not_retried(self):
        adapter = _make_adapter()
        result = adapter._http._classify_error(_tls_exc())
        self.assertEqual(result.category, "DATA_PROVIDER_TLS_ERROR")


class TestSymbolResolution(unittest.TestCase):
    def test_btc_to_btcusdt(self):
        self.assertEqual(_make_adapter()._normalize_symbol("BTC"), "BTCUSDT")

    def test_eth_to_ethusdt(self):
        self.assertEqual(_make_adapter()._normalize_symbol("ETH"), "ETHUSDT")

    def test_already_normalized(self):
        self.assertEqual(_make_adapter()._normalize_symbol("BTCUSDT"), "BTCUSDT")

    def test_slash_separator(self):
        self.assertEqual(_make_adapter()._normalize_symbol("BTC/USDT"), "BTCUSDT")

    def test_dash_separator(self):
        self.assertEqual(_make_adapter()._normalize_symbol("BTC-USDT"), "BTCUSDT")

    def test_lowercase_input(self):
        self.assertEqual(_make_adapter()._normalize_symbol("btc"), "BTCUSDT")

    def test_mixed_case_input(self):
        self.assertEqual(_make_adapter()._normalize_symbol("Btc"), "BTCUSDT")

    def test_non_crypto_no_quote_gets_usdt_appended(self):
        """4-letter tickers without known quote get USDT appended for Binance."""
        result = _make_adapter()._normalize_symbol("AAPL")
        self.assertEqual(result, "AAPLUSDT")

    def test_already_has_usdt_suffix(self):
        self.assertEqual(_make_adapter()._normalize_symbol("SOLUSDT"), "SOLUSDT")

    def test_btcusdt_not_doubled(self):
        self.assertEqual(_make_adapter()._normalize_symbol("BTCUSDT"), "BTCUSDT")

    def test_eurusd_passthrough(self):
        """EURUSD already has a quote suffix, passes through."""
        self.assertEqual(_make_adapter()._normalize_symbol("EURUSD"), "EURUSD")


class TestSSLErrorHandling(unittest.TestCase):
    def test_ssl_context_created_with_verify(self):
        adapter = _make_adapter()
        self.assertIsNotNone(adapter._http._ssl_context)

    def test_ssl_context_no_verify(self):
        rl = RateLimiter(max_requests=10, time_window=1.0)
        adapter = BinanceAdapter(rate_limiter=rl)
        adapter._http._ssl_verify = False
        adapter._http._ssl_context = None
        self.assertIsNone(adapter._http._ssl_context)

    def test_build_ssl_context_default(self):
        ctx = _build_ssl_context()
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.protocol, ssl.PROTOCOL_TLS_CLIENT)

    def test_tls_error_classification_at_http_level(self):
        """TLS error is classified correctly at the HTTP layer."""
        adapter = _make_adapter()
        result = adapter._http._classify_error(_tls_exc())
        self.assertEqual(result.category, "DATA_PROVIDER_TLS_ERROR")
        self.assertEqual(result.provider, "binance")
        # Verify TLS errors are NOT retryable (won't fix ISP hijacking)
        self.assertFalse(adapter._http._should_retry(_tls_exc()))

    def test_tls_error_returns_empty_candles(self):
        """When TLS fails, fetch_candles returns empty CandleSet (caught internally)."""

        async def _test():
            adapter = _make_adapter()

            async def mock_request(method, path, params=None, headers=None):
                raise _tls_exc()

            adapter._http._request = mock_request

            result = await adapter.fetch_candles(
                "BTCUSDT", Timeframe.H1, "2024-01-01", "2024-01-02"
            )
            # fetch_candles catches exceptions internally and returns empty CandleSet
            self.assertEqual(len(result.candles), 0)

        asyncio.run(_test())

    def test_tls_error_no_signal_in_analysis_service(self):
        """AnalysisService returns NO_SIGNAL when provider has TLS error."""

        async def _test():
            adapter = _make_adapter()

            async def mock_request(method, path, params=None, headers=None):
                raise _tls_exc()

            adapter._http._request = mock_request

            service = AnalysisService(
                adapters={"binance": adapter},
                default_adapter="binance",
            )

            result = await service.analyze("BTCUSDT", lookback_days=30)
            self.assertEqual(result.signal.value, "no_signal")
            self.assertIn("DATA_PROVIDER_UNAVAILABLE", result.reason_codes)

        asyncio.run(_test())


class TestFormatProviderError(unittest.TestCase):
    def setUp(self):
        self.formatter = TelegramFormatter()

    def test_tls_error_display(self):
        text = self.formatter.format_provider_error(
            symbol="BTC/USDT",
            category="DATA_PROVIDER_TLS_ERROR",
            message="TLS certificate verification failed",
            provider="binance",
        )
        self.assertIn("DATA UNAVAILABLE", text)
        self.assertIn("BTC/USDT", text)
        self.assertIn("TLS certificate verification failed", text)
        self.assertIn("binance", text)
        self.assertIn("No market signal was generated", text)
        self.assertIn("not advice", text)

    def test_unavailable_error_display(self):
        text = self.formatter.format_provider_error(
            symbol="ETHUSDT",
            category="DATA_PROVIDER_UNAVAILABLE",
            message="Connection refused",
            provider="yahoo",
        )
        self.assertIn("DATA UNAVAILABLE", text)
        self.assertIn("ETHUSDT", text)
        self.assertIn("Connection refused", text)
        self.assertIn("yahoo", text)

    def test_timeout_error_display(self):
        text = self.formatter.format_provider_error(
            symbol="AAPL",
            category="DATA_PROVIDER_TIMEOUT",
            message="Request timed out after 30s",
            provider="yahoo",
        )
        self.assertIn("DATA UNAVAILABLE", text)
        self.assertIn("timed out", text.lower())

    def test_symbol_not_found_display(self):
        text = self.formatter.format_provider_error(
            symbol="FAKECOIN",
            category="SYMBOL_NOT_FOUND",
            message="Symbol not found",
            provider="binance",
        )
        self.assertIn("FAKECOIN", text)
        self.assertIn("not found", text.lower())

    def test_generic_error_display(self):
        text = self.formatter.format_provider_error(
            symbol="BTCUSDT",
            category="DATA_PROVIDER_ERROR",
            message="Unknown error occurred",
            provider="binance",
        )
        self.assertIn("DATA UNAVAILABLE", text)
        self.assertIn("Unknown error occurred", text)


class TestGetCurrentPriceFromCandles(unittest.TestCase):
    def test_price_from_h1_candles(self):
        async def _test():
            mock_adapter = AsyncMock()
            mock_adapter.name = "binance"

            candle = Candle(
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                open=100.0,
                high=105.0,
                low=95.0,
                close=102.5,
                volume=1000.0,
            )
            cs = CandleSet(
                symbol="BTCUSDT",
                timeframe=Timeframe.H1,
                candles=[candle],
                source="binance",
            )
            mock_adapter.fetch_candles.return_value = cs

            service = AnalysisService(
                adapters={"binance": mock_adapter},
                default_adapter="binance",
            )

            price = await service._get_current_price(mock_adapter, "BTCUSDT")
            self.assertEqual(price, 102.5)
            mock_adapter.fetch_candles.assert_called_once()

        asyncio.run(_test())

    def test_price_fallback_to_m1(self):
        async def _test():
            mock_adapter = AsyncMock()
            mock_adapter.name = "binance"

            candle = Candle(
                timestamp=datetime.utcnow(),
                open=200.0,
                high=205.0,
                low=195.0,
                close=203.0,
                volume=500.0,
            )
            cs = CandleSet(
                symbol="ETHUSDT",
                timeframe=Timeframe.M1,
                candles=[candle],
                source="binance",
            )

            call_count = 0

            async def side_effect(symbol, tf, start, end):
                nonlocal call_count
                call_count += 1
                if tf == Timeframe.H1:
                    return CandleSet(symbol=symbol, timeframe=tf, candles=[], source="binance")
                return cs

            mock_adapter.fetch_candles = AsyncMock(side_effect=side_effect)
            service = AnalysisService(
                adapters={"binance": mock_adapter},
                default_adapter="binance",
            )

            price = await service._get_current_price(mock_adapter, "ETHUSDT")
            self.assertEqual(price, 203.0)
            self.assertEqual(call_count, 2)

        asyncio.run(_test())

    def test_price_raises_on_empty_candles(self):
        async def _test():
            mock_adapter = AsyncMock()
            mock_adapter.name = "binance"
            mock_adapter.fetch_candles = AsyncMock(
                return_value=CandleSet(
                    symbol="FAKE",
                    timeframe=Timeframe.H1,
                    candles=[],
                    source="binance",
                )
            )

            service = AnalysisService(
                adapters={"binance": mock_adapter},
                default_adapter="binance",
            )

            with self.assertRaises(ValueError):
                await service._get_current_price(mock_adapter, "FAKE")

        asyncio.run(_test())
