"""Tests for Telegram layer: formatter, security, and validator."""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from umae.telegram.formatter import TelegramFormatter
from umae.telegram.models import (
    AnalysisResult,
    DataQuality,
    FeatureSummary,
    ProviderStatus,
    SystemStatus,
    TimeframeResult,
    WatchlistItem,
    WatchlistResult,
)
from umae.telegram.security import (
    InputValidator,
    UpdateDeduplicator,
    UserRateLimiter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def formatter() -> TelegramFormatter:
    return TelegramFormatter()


@pytest.fixture
def sample_analysis() -> AnalysisResult:
    return AnalysisResult(
        symbol="BTCUSDT",
        asset_type="crypto",
        exchange="binance",
        timestamp="2026-09-03 12:00:00",
        price=Decimal("58432.50"),
        data_quality=DataQuality(
            state="GOOD",
            freshness_seconds=30,
            completeness=0.99,
            candle_count=1000,
            missing_candles=0,
        ),
        regime="uptrend",
        regime_confidence=0.82,
        signal="up",
        signal_score=0.65,
        timeframe_results=[
            TimeframeResult(
                timeframe="5m",
                signal="up",
                score=0.72,
                regime="uptrend",
                regime_confidence=0.85,
                trend="BULLISH",
                momentum="NEUTRAL",
                volume="HIGH",
                volatility="NORMAL",
                structure="BULLISH",
            ),
            TimeframeResult(
                timeframe="1h",
                signal="neutral",
                score=0.15,
                regime="sideways",
                regime_confidence=0.60,
                trend="NEUTRAL",
                momentum="NEUTRAL",
                volume="NORMAL",
                volatility="LOW",
                structure="MIXED",
            ),
        ],
        calibrated_confidence=0.78,
        feature_summary=FeatureSummary(
            trend="BULLISH",
            momentum="NEUTRAL",
            volume="NORMAL",
            volatility="LOW",
            structure="BULLISH",
        ),
        reason_codes=["htf_unanimous_bullish", "ema_bullish_alignment"],
        warnings=["5m: DATA_UNAVAILABLE"],
        model_version="1.2.0",
        feature_version="features-1.0.0",
        data_version="binance-rest-v1",
        provider="binance",
        provider_symbol="BTCUSDT",
    )


@pytest.fixture
def sample_status() -> SystemStatus:
    return SystemStatus(
        providers=[
            ProviderStatus(name="binance", status="ok"),
            ProviderStatus(name="yahoo", status="error", error_message="timeout"),
            ProviderStatus(name="ecb", status="degraded"),
        ],
        database_status="ok",
        analysis_engine_status="ok",
        last_update="2026-09-03 12:00:00",
        uptime_seconds=90061,
        active_users=42,
        symbols_tracked=128,
        warnings=["Memory usage high"],
        version="0.3.0",
    )


@pytest.fixture
def sample_watchlist() -> WatchlistResult:
    return WatchlistResult(
        user_id=12345,
        items=[
            WatchlistItem(
                symbol="BTCUSDT",
                exchange="binance",
                signal="up",
                score=0.65,
                price=Decimal("58432.50"),
            ),
            WatchlistItem(
                symbol="ETHUSDT",
                exchange="binance",
                signal="down",
                score=-0.40,
                price=Decimal("3200.10"),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# TelegramFormatter tests
# ---------------------------------------------------------------------------


class TestTelegramFormatter:
    def test_format_analysis(
        self, formatter: TelegramFormatter, sample_analysis: AnalysisResult
    ) -> None:
        text = formatter.format_analysis(sample_analysis)

        assert "BTCUSDT" in text
        assert "$58,432.50" in text
        assert "UMAE ANALYSIS" in text
        assert "uptrend" in text
        assert "82%" in text
        assert "5m" in text
        assert "1h" in text
        assert "UP" in text
        assert "+0.65" in text
        assert "78%" in text  # calibrated_confidence
        assert "htf_unanimous_bullish" in text
        assert "5m: DATA_UNAVAILABLE" in text
        assert "1.2.0" in text
        assert "features-1.0.0" in text
        assert "binance-rest-v1" in text
        assert "not advice" in text

    def test_format_analysis_no_timeframes(self, formatter: TelegramFormatter) -> None:
        result = AnalysisResult(
            symbol="ETHUSDT",
            asset_type="crypto",
            exchange="binance",
            timestamp="2026-09-03",
            price=Decimal("3200"),
            data_quality=DataQuality(
                state="DEGRADED",
                freshness_seconds=60,
                completeness=0.95,
                candle_count=500,
                missing_candles=5,
            ),
            regime="sideways",
            regime_confidence=0.50,
            signal="neutral",
            signal_score=0.05,
        )
        text = formatter.format_analysis(result)
        assert "ETHUSDT" in text
        assert "TIMEFRAME ANALYSIS" not in text

    def test_format_status(self, formatter: TelegramFormatter, sample_status: SystemStatus) -> None:
        text = formatter.format_status(sample_status)

        assert "SYSTEM STATUS" in text
        assert "binance" in text
        assert "yahoo" in text
        assert "ecb" in text
        assert "OK" in text
        assert "ERROR" in text
        assert "Database:" in text
        assert "Analysis Engine:" in text
        assert "2026-09-03 12:00:00" in text
        assert "Active Users:" in text
        assert "42" in text
        assert "128" in text
        assert "Memory usage high" in text
        assert "1d 1h 1m" in text
        assert "0.3.0" in text

    def test_format_status_no_providers(self, formatter: TelegramFormatter) -> None:
        result = SystemStatus()
        text = formatter.format_status(result)
        assert "Providers:" in text
        assert "Never" in text

    def test_format_watchlist(
        self, formatter: TelegramFormatter, sample_watchlist: WatchlistResult
    ) -> None:
        text = formatter.format_watchlist(sample_watchlist)

        assert "Your Watchlist:" in text
        assert "1. BTCUSDT (binance)" in text
        assert "2. ETHUSDT (binance)" in text
        assert "UP" in text
        assert "DOWN" in text
        assert "+0.65" in text
        assert "-0.40" in text
        assert "$58,432.50" in text
        assert "$3,200.10" in text
        assert "/add" in text
        assert "/remove" in text

    def test_format_watchlist_empty(self, formatter: TelegramFormatter) -> None:
        result = WatchlistResult(user_id=1)
        text = formatter.format_watchlist(result)
        assert "empty" in text
        assert "/add" in text

    def test_format_watchlist_no_price(self, formatter: TelegramFormatter) -> None:
        result = WatchlistResult(
            user_id=1,
            items=[
                WatchlistItem(
                    symbol="XYZ",
                    exchange="test",
                    signal="neutral",
                    score=0.0,
                    price=None,
                ),
            ],
        )
        text = formatter.format_watchlist(result)
        assert "N/A" in text

    def test_format_help(self, formatter: TelegramFormatter) -> None:
        text = formatter.format_help()
        assert "UMAE Commands:" in text
        assert "/analyze" in text
        assert "/status" in text
        assert "/watchlist" in text
        assert "/add" in text
        assert "/remove" in text
        assert "Disclaimer" in text

    def test_format_welcome(self, formatter: TelegramFormatter) -> None:
        text = formatter.format_welcome()
        assert "UMAE" in text
        assert "Universal Market Analysis Engine" in text

    def test_format_error(self, formatter: TelegramFormatter) -> None:
        text = formatter.format_error("Something broke")
        assert "Error" in text
        assert "Something broke" in text
        assert "/help" in text

    def test_split_message_short(self, formatter: TelegramFormatter) -> None:
        parts = formatter.split_message("hello")
        assert parts == ["hello"]

    def test_split_message_exact_limit(self, formatter: TelegramFormatter) -> None:
        msg = "x" * 4096
        parts = formatter.split_message(msg)
        assert parts == [msg]

    def test_split_message_over_limit(self, formatter: TelegramFormatter) -> None:
        lines = [f"line {i}" for i in range(500)]
        msg = "\n".join(lines)
        parts = formatter.split_message(msg)

        assert len(parts) > 1
        for part in parts:
            assert len(part) <= 4096
        reassembled = "\n".join(parts)
        assert len(reassembled) >= len(msg) - 100  # small loss from split is OK

    def test_split_message_very_long_line(self, formatter: TelegramFormatter) -> None:
        msg = "a" * 10000
        parts = formatter.split_message(msg)
        assert len(parts) > 1
        for part in parts:
            assert len(part) <= 4096


# ---------------------------------------------------------------------------
# UserRateLimiter tests
# ---------------------------------------------------------------------------


class TestUserRateLimiter:
    def test_rate_limit_allows(self) -> None:
        limiter = UserRateLimiter(max_commands=5, window=60)
        assert limiter.is_allowed(1) is True
        assert limiter.is_allowed(1) is True
        assert limiter.remaining(1) == 3

    def test_rate_limit_blocks(self) -> None:
        limiter = UserRateLimiter(max_commands=3, window=60)
        assert limiter.is_allowed(1) is True
        assert limiter.is_allowed(1) is True
        assert limiter.is_allowed(1) is True
        assert limiter.is_allowed(1) is False
        assert limiter.remaining(1) == 0

    def test_rate_limit_independent_users(self) -> None:
        limiter = UserRateLimiter(max_commands=1, window=60)
        assert limiter.is_allowed(1) is True
        assert limiter.is_allowed(1) is False
        assert limiter.is_allowed(2) is True

    def test_rate_limit_reset(self) -> None:
        limiter = UserRateLimiter(max_commands=1, window=60)
        limiter.is_allowed(1)
        limiter.reset(1)
        assert limiter.is_allowed(1) is True

    def test_rate_limit_window_expiry(self) -> None:
        limiter = UserRateLimiter(max_commands=1, window=0)
        limiter.is_allowed(1)
        time.sleep(0.01)
        assert limiter.is_allowed(1) is True


# ---------------------------------------------------------------------------
# UpdateDeduplicator tests
# ---------------------------------------------------------------------------


class TestUpdateDeduplicator:
    def test_not_duplicate(self) -> None:
        dedup = UpdateDeduplicator()
        assert dedup.is_duplicate(1001) is False
        assert dedup.is_duplicate(1002) is False

    def test_is_duplicate(self) -> None:
        dedup = UpdateDeduplicator()
        assert dedup.is_duplicate(1001) is False
        assert dedup.is_duplicate(1001) is True

    def test_max_size_eviction(self) -> None:
        dedup = UpdateDeduplicator(max_size=3)
        dedup.is_duplicate(1)
        dedup.is_duplicate(2)
        dedup.is_duplicate(3)
        assert dedup.is_duplicate(4) is False
        # Old entries may have been evicted
        assert dedup.is_duplicate(4) is True

    def test_many_updates(self) -> None:
        dedup = UpdateDeduplicator(max_size=100)
        for i in range(200):
            dedup.is_duplicate(i)
        # After 200, max_size=100, some old IDs evicted
        # New ID should not be a duplicate
        assert dedup.is_duplicate(999) is False


# ---------------------------------------------------------------------------
# InputValidator tests
# ---------------------------------------------------------------------------


class TestInputValidator:
    def test_valid_symbol(self) -> None:
        assert InputValidator.validate_symbol("BTCUSDT") is True
        assert InputValidator.validate_symbol("BTC/USDT") is True
        assert InputValidator.validate_symbol("AAPL") is True
        assert InputValidator.validate_symbol("EURUSD") is True
        assert InputValidator.validate_symbol("^GSPC") is True
        assert InputValidator.validate_symbol("ETH-USDT") is True
        assert InputValidator.validate_symbol("BRK.A") is True
        assert InputValidator.validate_symbol("btcusdt") is True

    def test_invalid_symbol(self) -> None:
        assert InputValidator.validate_symbol("") is False
        assert InputValidator.validate_symbol("A" * 21) is False
        assert InputValidator.validate_symbol("BTC USDT") is False
        assert InputValidator.validate_symbol("BTC@USDT") is False
        assert InputValidator.validate_symbol("BTC!USDT") is False
        assert InputValidator.validate_symbol("$AAPL") is False

    def test_valid_command(self) -> None:
        assert InputValidator.is_valid_command("/start") is True
        assert InputValidator.is_valid_command("/help") is True
        assert InputValidator.is_valid_command("/analyze") is True
        assert InputValidator.is_valid_command("/status") is True
        assert InputValidator.is_valid_command("/watchlist") is True
        assert InputValidator.is_valid_command("/add") is True
        assert InputValidator.is_valid_command("/remove") is True
        assert InputValidator.is_valid_command("/analyze BTCUSDT") is True
        assert InputValidator.is_valid_command("/add AAPL") is True

    def test_invalid_command(self) -> None:
        assert InputValidator.is_valid_command("/unknown") is False
        assert InputValidator.is_valid_command("/delete") is False
        assert InputValidator.is_valid_command("hello") is False

    def test_empty_command_raises(self) -> None:
        with pytest.raises(IndexError):
            InputValidator.is_valid_command("")

    def test_sanitize_symbol(self) -> None:
        assert InputValidator.sanitize_symbol("  btcusdt  ") == "BTCUSDT"
        assert InputValidator.sanitize_symbol("aapl") == "AAPL"
        assert InputValidator.sanitize_symbol("^GSPC") == "^GSPC"

    def test_parse_analyze_args_valid(self) -> None:
        assert InputValidator.parse_analyze_args(["BTCUSDT"]) == "BTCUSDT"
        assert InputValidator.parse_analyze_args(["aapl"]) == "AAPL"
        assert InputValidator.parse_analyze_args(["BTC/USDT"]) == "BTC/USDT"

    def test_parse_analyze_args_invalid(self) -> None:
        assert InputValidator.parse_analyze_args([]) is None
        assert InputValidator.parse_analyze_args([""]) is None
        assert InputValidator.parse_analyze_args(["BTC USDT"]) is None
        assert InputValidator.parse_analyze_args(["$" * 21]) is None

    def test_truncate_short(self) -> None:
        assert InputValidator.truncate("hello", max_length=100) == "hello"

    def test_truncate_long(self) -> None:
        long_text = "a" * 5000
        result = InputValidator.truncate(long_text, max_length=4096)
        assert len(result) <= 4096
        assert "truncated" in result
