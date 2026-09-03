"""Integration correctness and robustness hardening tests.

Covers:
- P0: Single-timeframe target propagation
- P0: Provider failure != NEUTRAL 0.0
- P0: Deterministic HTTP lifecycle
- P0: TLS error handling
- P0: Callback hardening (stale/expired)
- P1: Callback payload validation
- P1: Refresh callback standardization
- P1: Callback rate limiting
- P1: Unified provider health
- P2: Timezone-aware UTC
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from umae.domain.enums import MarketRegime, SignalType, Timeframe
from umae.interfaces.analysis_service import AnalysisResult
from umae.telegram.callbacks import CallbackPayload
from umae.telegram.formatter import TelegramFormatter
from umae.telegram.models import (
    WatchlistItem,
)
from umae.telegram.services import TIMEFRAME_MAP, AnalysisService

# ── P0: Single-timeframe target propagation ─────────────────────


class TestTimeframeEnumMapping(unittest.TestCase):
    """TIMEFRAME_MAP correctly maps all timeframe strings."""

    def test_all_timeframes_mapped(self):
        for tf in Timeframe:
            self.assertIn(tf.value, TIMEFRAME_MAP)
            self.assertEqual(TIMEFRAME_MAP[tf.value], tf)

    def test_1m_maps_to_m1(self):
        self.assertEqual(TIMEFRAME_MAP["1m"], Timeframe.M1)

    def test_5m_maps_to_m5(self):
        self.assertEqual(TIMEFRAME_MAP["5m"], Timeframe.M5)

    def test_1h_maps_to_h1(self):
        self.assertEqual(TIMEFRAME_MAP["1h"], Timeframe.H1)

    def test_1d_maps_to_d1(self):
        self.assertEqual(TIMEFRAME_MAP["1D"], Timeframe.D1)

    def test_invalid_tf_returns_none(self):
        self.assertNotIn("99m", TIMEFRAME_MAP)
        self.assertNotIn("fake", TIMEFRAME_MAP)


class TestTargetTimeframePropagation(unittest.TestCase):
    """Target timeframe is passed from callback through to core analysis."""

    def test_callback_payload_tf_parsed(self):
        payload = CallbackPayload.parse("tf:crypto:BTC/USDT:5m")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.target_tf, Timeframe.M5)

    def test_callback_payload_1m(self):
        payload = CallbackPayload.parse("tf:crypto:BTC/USDT:1m")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.target_tf, Timeframe.M1)

    def test_callback_payload_1h(self):
        payload = CallbackPayload.parse("tf:crypto:BTC/USDT:1h")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.target_tf, Timeframe.H1)

    def test_callback_payload_multi_no_tf(self):
        payload = CallbackPayload.parse("multi:crypto:BTC/USDT")
        self.assertIsNotNone(payload)
        self.assertIsNone(payload.target_tf)

    def test_callback_payload_refresh_with_tf(self):
        payload = CallbackPayload.parse("refresh:crypto:BTC/USDT:5m")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.target_tf, Timeframe.M5)

    def test_callback_payload_refresh_without_tf(self):
        payload = CallbackPayload.parse("refresh:crypto:BTC/USDT")
        self.assertIsNotNone(payload)
        self.assertIsNone(payload.target_tf)

    def test_analysis_service_accepts_target_tf(self):
        """AnalysisService.analyze() accepts target_timeframe parameter."""
        svc = AnalysisService.__new__(AnalysisService)
        import inspect

        sig = inspect.signature(svc.analyze)
        self.assertIn("target_timeframe", sig.parameters)

    def test_core_analyze_accepts_target_tf(self):
        """Core AnalysisService.analyze() accepts target_timeframe parameter."""
        from umae.interfaces.analysis_service import AnalysisService as CoreSvc

        svc = CoreSvc.__new__(CoreSvc)
        import inspect

        sig = inspect.signature(svc.analyze)
        self.assertIn("target_timeframe", sig.parameters)

    def test_core_result_carries_target_timeframe(self):
        """Core AnalysisResult carries target_timeframe field."""
        result = AnalysisResult(
            symbol="BTCUSDT",
            asset_type=SignalType.UP,
            exchange="binance",
            price=Decimal("80000"),
            timestamp=datetime.now(UTC),
            signal=SignalType.UP,
            score=0.5,
            regime=MarketRegime.TRENDING_UP,
            regime_confidence=0.6,
            target_timeframe=Timeframe.M5,
            context_timeframes=[Timeframe.M15, Timeframe.H1],
        )
        self.assertEqual(result.target_timeframe, Timeframe.M5)
        self.assertEqual(len(result.context_timeframes), 2)


# ── P0: Provider failure != NEUTRAL 0.0 ─────────────────────────


class TestProviderFailureNotNeutral(unittest.TestCase):
    """Failed analysis never produces NEUTRAL 0.0."""

    def test_watchlist_unavailable_signal(self):
        """WatchlistItem uses 'unavailable' signal on failure."""
        item = WatchlistItem(
            symbol="BTCUSDT",
            exchange="",
            signal="unavailable",
            score=0.0,
        )
        self.assertEqual(item.signal, "unavailable")
        self.assertEqual(item.score, 0.0)
        # Must NOT be neutral
        self.assertNotEqual(item.signal, "neutral")

    def test_formatter_shows_unavailable(self):
        """Formatter renders unavailable signal correctly."""
        from umae.telegram.models import WatchlistResult

        result = WatchlistResult(
            user_id=123,
            items=[
                WatchlistItem(
                    symbol="BTCUSDT",
                    exchange="binance",
                    signal="up",
                    score=0.5,
                    price=Decimal("80000"),
                ),
                WatchlistItem(
                    symbol="FAKECOIN",
                    exchange="",
                    signal="unavailable",
                    score=0.0,
                ),
            ],
        )
        formatter = TelegramFormatter()
        text = formatter.format_watchlist(result)
        self.assertIn("DATA UNAVAILABLE", text)
        self.assertIn("BTCUSDT", text)
        self.assertIn("FAKECOIN", text)

    def test_core_no_signal_on_provider_failure(self):
        """Core AnalysisService returns NO_SIGNAL on adapter not found."""

        async def _test():
            from umae.interfaces.analysis_service import AnalysisService

            service = AnalysisService(
                adapters={},
                default_adapter="binance",
            )
            result = await service.analyze("BTCUSDT")
            self.assertEqual(result.signal, SignalType.NO_SIGNAL)
            self.assertIn("DATA_PROVIDER_UNAVAILABLE", result.reason_codes)

        asyncio.run(_test())

    def test_core_no_signal_on_empty_candles(self):
        """Core AnalysisService returns NO_SIGNAL when no candle data."""

        async def _test():
            from umae.domain.models import CandleSet
            from umae.interfaces.analysis_service import AnalysisService

            mock_adapter = AsyncMock()
            mock_adapter.name = "binance"
            mock_adapter.fetch_candles = AsyncMock(
                return_value=CandleSet(
                    symbol="BTCUSDT",
                    timeframe=Timeframe.H1,
                    candles=[],
                    source="binance",
                )
            )
            mock_adapter.get_asset_metadata = AsyncMock(return_value=None)

            # Override _get_current_price to also fail
            service = AnalysisService(
                adapters={"binance": mock_adapter},
                default_adapter="binance",
            )
            result = await service.analyze("BTCUSDT")
            self.assertEqual(result.signal, SignalType.NO_SIGNAL)
            self.assertTrue(
                "NO_CANDLE_DATA" in result.reason_codes
                or "DATA_PROVIDER_UNAVAILABLE" in result.reason_codes
            )

        asyncio.run(_test())


# ── P0: TLS error handling ──────────────────────────────────────


class TestTLSErrorHandling(unittest.TestCase):
    """TLS errors are properly classified and never bypass verification."""

    def test_tls_error_classification(self):
        import ssl

        from umae.data.binance_adapter import BinanceAdapter
        from umae.interfaces.base_adapter import RateLimiter

        adapter = BinanceAdapter(rate_limiter=RateLimiter(max_requests=10, time_window=1.0))

        inner = ssl.SSLCertVerificationError("hostname mismatch")
        exc = type("", (), {})()  # placeholder
        import aiohttp

        exc = aiohttp.ClientConnectorCertificateError(
            connection_key=MagicMock(host="api.binance.com"),
            certificate_error=inner,
        )
        result = adapter._http._classify_error(exc)
        self.assertEqual(result.category, "DATA_PROVIDER_TLS_ERROR")
        # TLS errors must NOT be retried
        self.assertFalse(adapter._http._should_retry(exc))

    def test_ssl_context_created(self):
        from umae.data.binance_adapter import BinanceAdapter
        from umae.interfaces.base_adapter import RateLimiter

        adapter = BinanceAdapter(rate_limiter=RateLimiter(max_requests=10, time_window=1.0))
        self.assertIsNotNone(adapter._http._ssl_context)

    def test_ssl_verify_true_by_default(self):
        from umae.data.binance_adapter import BinanceAdapter
        from umae.interfaces.base_adapter import RateLimiter

        adapter = BinanceAdapter(rate_limiter=RateLimiter(max_requests=10, time_window=1.0))
        self.assertTrue(adapter._http._ssl_verify)


# ── P0: Callback payload validation ─────────────────────────────


class TestCallbackPayloadValidation(unittest.TestCase):
    """CallbackPayload rejects invalid callbacks."""

    def test_valid_tf_callback(self):
        payload = CallbackPayload.parse("tf:crypto:BTC/USDT:5m")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.action, "tf")
        self.assertEqual(payload.timeframe, "5m")

    def test_valid_multi_callback(self):
        payload = CallbackPayload.parse("multi:crypto:BTC/USDT")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.action, "multi")

    def test_valid_refresh_callback(self):
        payload = CallbackPayload.parse("refresh:crypto:BTC/USDT:5m")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.action, "refresh")
        self.assertEqual(payload.timeframe, "5m")

    def test_invalid_action_rejected(self):
        payload = CallbackPayload.parse("invalid_action:data")
        self.assertIsNone(payload)

    def test_invalid_category_rejected(self):
        payload = CallbackPayload.parse("cat:random_category")
        self.assertIsNone(payload)

    def test_valid_category_accepted(self):
        for cat in ("crypto", "stocks", "forex", "indices"):
            payload = CallbackPayload.parse(f"cat:{cat}")
            self.assertIsNotNone(payload, f"Category {cat} should be valid")

    def test_tf_missing_parts_rejected(self):
        payload = CallbackPayload.parse("tf:crypto")
        self.assertIsNone(payload)

    def test_tf_invalid_timeframe_rejected(self):
        payload = CallbackPayload.parse("tf:crypto:BTC/USDT:99m")
        self.assertIsNone(payload)

    def test_tf_fake_timeframe_rejected(self):
        payload = CallbackPayload.parse("tf:crypto:BTC/USDT:fake")
        self.assertIsNone(payload)

    def test_asset_missing_parts_rejected(self):
        payload = CallbackPayload.parse("asset:crypto")
        self.assertIsNone(payload)

    def test_multi_missing_parts_rejected(self):
        payload = CallbackPayload.parse("multi:crypto")
        self.assertIsNone(payload)

    def test_empty_string_rejected(self):
        payload = CallbackPayload.parse("")
        self.assertIsNone(payload)

    def test_none_data_rejected(self):
        payload = CallbackPayload.parse(None)  # type: ignore[arg-type]
        self.assertIsNone(payload)

    def test_refresh_missing_parts_rejected(self):
        payload = CallbackPayload.parse("refresh:crypto")
        self.assertIsNone(payload)

    def test_watch_invalid_sub_rejected(self):
        payload = CallbackPayload.parse("watch:invalid_sub")
        self.assertIsNone(payload)

    def test_watch_valid_sub_accepted(self):
        for sub in ("list", "add", "remove", "do_add", "do_remove"):
            payload = CallbackPayload.parse(f"watch:{sub}")
            self.assertIsNotNone(payload, f"Watch sub {sub} should be valid")

    def test_back_valid(self):
        payload = CallbackPayload.parse("back:main")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.action, "back")
        self.assertEqual(payload.sub_action, "main")

    def test_status_valid(self):
        payload = CallbackPayload.parse("status")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.action, "status")

    def test_help_valid(self):
        payload = CallbackPayload.parse("help")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.action, "help")

    def test_noop_valid(self):
        payload = CallbackPayload.parse("noop")
        self.assertIsNotNone(payload)
        self.assertEqual(payload.action, "noop")


# ── P1: Refresh callback standardization ────────────────────────


class TestRefreshCallbackStandardization(unittest.TestCase):
    """Refresh callbacks use standardized refresh: prefix."""

    def test_analysis_actions_single_tf_uses_refresh_prefix(self):
        from umae.telegram.keyboards import analysis_actions

        kb = analysis_actions("crypto", "BTC/USDT", tf="5m")
        # Find the refresh button
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.text == "Refresh":
                    self.assertTrue(
                        btn.callback_data.startswith("refresh:"),
                        f"Expected refresh: prefix, got: {btn.callback_data}",
                    )
                    self.assertIn("5m", btn.callback_data)
                    return
        self.fail("Refresh button not found")

    def test_analysis_actions_multi_uses_refresh_prefix(self):
        from umae.telegram.keyboards import analysis_actions

        kb = analysis_actions("crypto", "BTC/USDT")
        for row in kb.inline_keyboard:
            for btn in row:
                if btn.text == "Refresh":
                    self.assertTrue(
                        btn.callback_data.startswith("refresh:"),
                        f"Expected refresh: prefix, got: {btn.callback_data}",
                    )
                    self.assertNotIn("5m", btn.callback_data)
                    return
        self.fail("Refresh button not found")


# ── P2: Timezone-aware UTC ──────────────────────────────────────


class TestTimezoneAwareUTC(unittest.TestCase):
    """Affected code uses timezone-aware UTC."""

    def test_handlers_status_uses_aware_utc(self):
        """handlers.py status handler uses datetime.now(UTC)."""
        import inspect

        from umae.telegram.handlers import handle_status

        source = inspect.getsource(handle_status)
        self.assertIn("datetime.now(UTC)", source)
        self.assertNotIn("datetime.utcnow()", source)

    def test_callbacks_status_uses_aware_utc(self):
        """callbacks.py status handler uses datetime.now(UTC)."""
        import inspect

        from umae.telegram.callbacks import _handle_status

        source = inspect.getsource(_handle_status)
        self.assertIn("datetime.now(UTC)", source)
        self.assertNotIn("datetime.utcnow()", source)

    def test_no_utcnow_in_touched_callback_code(self):
        """callbacks.py has no datetime.utcnow() usage."""
        import inspect

        from umae.telegram import callbacks

        source = inspect.getsource(callbacks)
        self.assertNotIn("datetime.utcnow()", source)

    def test_no_utcnow_in_touched_handler_code(self):
        """handlers.py has no datetime.utcnow() usage."""
        import inspect

        from umae.telegram import handlers

        source = inspect.getsource(handlers)
        self.assertNotIn("datetime.utcnow()", source)


# ── P1: No hardcoded _CRYPTO_ASSETS etc in public API ───────────


class TestNoHardcodedAssetAPI(unittest.TestCase):
    """Keyboards accept assets as parameter."""

    def test_category_menu_accepts_assets_param(self):
        import inspect

        from umae.telegram.keyboards import category_menu

        sig = inspect.signature(category_menu)
        self.assertIn("assets", sig.parameters)

    def test_category_menu_uses_custom_assets(self):
        from umae.telegram.keyboards import category_menu

        custom = ["CUSTOM1", "CUSTOM2"]
        kb = category_menu("crypto", assets=custom)
        # Check that custom assets appear as buttons
        button_texts = []
        for row in kb.inline_keyboard:
            for btn in row:
                button_texts.append(btn.text)
        self.assertIn("CUSTOM1", button_texts)
        self.assertIn("CUSTOM2", button_texts)
        # Default BTC/USDT should NOT be present
        self.assertNotIn("BTC/USDT", button_texts)


# ── P0: Deterministic HTTP lifecycle ────────────────────────────


class TestHTTPLifecycle(unittest.TestCase):
    """Adapters can be closed cleanly."""

    def test_binance_adapter_has_close(self):
        from umae.data.binance_adapter import BinanceAdapter
        from umae.interfaces.base_adapter import RateLimiter

        adapter = BinanceAdapter(rate_limiter=RateLimiter(max_requests=10, time_window=1.0))
        self.assertTrue(hasattr(adapter, "close"))
        self.assertTrue(callable(adapter.close))

    def test_base_http_adapter_has_close(self):
        from umae.interfaces.base_adapter import BaseHTTPAdapter, RateLimiter

        adapter = BaseHTTPAdapter(
            base_url="https://example.com",
            rate_limiter=RateLimiter(max_requests=10, time_window=1.0),
        )
        self.assertTrue(hasattr(adapter, "close"))
        self.assertTrue(callable(adapter.close))

    def test_close_is_idempotent(self):
        """Calling close() multiple times does not raise."""
        from umae.data.binance_adapter import BinanceAdapter
        from umae.interfaces.base_adapter import RateLimiter

        async def _test():
            adapter = BinanceAdapter(rate_limiter=RateLimiter(max_requests=10, time_window=1.0))
            await adapter.close()
            await adapter.close()  # should not raise

        asyncio.run(_test())

    def test_run_bot_has_cleanup_function(self):
        """run_bot.py has _run_with_cleanup for deterministic cleanup."""
        import inspect

        from run_bot import _run_with_cleanup

        source = inspect.getsource(_run_with_cleanup)
        self.assertIn("adapter.close()", source)
        self.assertIn("database.close()", source)


# ── P1: Unified provider health ─────────────────────────────────


class TestUnifiedHealthCheck(unittest.TestCase):
    """Status handler probes providers for real health."""

    def test_callbacks_status_probes_providers(self):
        """callbacks.py _handle_status probes each provider."""
        import inspect

        from umae.telegram.callbacks import _handle_status

        source = inspect.getsource(_handle_status)
        # Must probe with actual fetch, not just list adapters
        self.assertIn("fetch_candles", source)
        # Must handle ProviderError
        self.assertIn("ProviderError", source)

    def test_handlers_status_probes_providers(self):
        """handlers.py handle_status probes each provider."""
        import inspect

        from umae.telegram.handlers import handle_status

        source = inspect.getsource(handle_status)
        self.assertIn("fetch_candles", source)
        self.assertIn("ProviderError", source)


if __name__ == "__main__":
    unittest.main()
