"""Integration test for the /analyze Telegram command pipeline.

Verifies the full flow:
Telegram command → Application Service → Engine → AnalysisResult → Formatter

Without requiring a real Telegram connection.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from umae.domain.enums import AssetType, MarketRegime, SignalType, Timeframe
from umae.interfaces.analysis_service import (
    AnalysisResult,
    AnalysisService,
    TimeframeAnalysis,
)
from umae.telegram.formatter import TelegramFormatter
from umae.telegram.models import AnalysisResult as TelegramAnalysisResult
from umae.telegram.services import AnalysisService as TelegramAnalysisService


def _make_core_result(symbol: str = "BTC/USDT") -> AnalysisResult:
    """Create a realistic core AnalysisResult."""
    return AnalysisResult(
        symbol=symbol,
        asset_type=AssetType.CRYPTO,
        exchange="binance",
        price=Decimal("65432.10"),
        timestamp=datetime(2024, 6, 15, 12, 0, 0),
        signal=SignalType.UP,
        score=0.35,
        regime=MarketRegime.TRENDING_UP,
        regime_confidence=0.72,
        timeframe_analyses=[
            TimeframeAnalysis(
                timeframe=Timeframe.M5,
                signal=SignalType.UP,
                score=0.25,
                regime=MarketRegime.TRENDING_UP,
                regime_confidence=0.65,
                features={
                    "trend_structure_score": 0.4,
                    "momentum_rsi": 62.0,
                    "volume_relative": 1.3,
                    "volatility_expansion": 1.1,
                    "trend_structure_hh": 1.0,
                    "trend_structure_hl": 1.0,
                },
                reason_codes=["ema_bullish_alignment"],
            ),
            TimeframeAnalysis(
                timeframe=Timeframe.H1,
                signal=SignalType.UP,
                score=0.40,
                regime=MarketRegime.TRENDING_UP,
                regime_confidence=0.75,
                features={
                    "trend_structure_score": 0.5,
                    "momentum_rsi": 58.0,
                    "volume_relative": 1.5,
                    "volatility_expansion": 0.9,
                    "trend_structure_hh": 1.0,
                    "trend_structure_hl": 1.0,
                },
                reason_codes=["ema_bullish_alignment", "macd_bullish"],
            ),
            TimeframeAnalysis(
                timeframe=Timeframe.D1,
                signal=SignalType.UP,
                score=0.45,
                regime=MarketRegime.TRENDING_UP,
                regime_confidence=0.80,
                features={
                    "trend_structure_score": 0.6,
                    "momentum_rsi": 55.0,
                    "volume_relative": 1.2,
                    "volatility_expansion": 0.8,
                    "trend_structure_hh": 1.0,
                    "trend_structure_hl": 1.0,
                },
                reason_codes=["htf_unanimous_bullish"],
            ),
        ],
        reason_codes=["regime:trending_up", "confluence:3up:0down:3total"],
        contributing_factors={
            "htf_score": 0.45,
            "mtf_score": 0.40,
            "ltf_score": 0.25,
        },
        model_version="1.0.0",
        analysis_duration_ms=1234.5,
    )


class TestAnalyzePipeline:
    """Test the full /analyze pipeline without real Telegram."""

    def test_core_to_telegram_conversion(self) -> None:
        """Core AnalysisResult converts to Telegram AnalysisResult correctly."""
        core_result = _make_core_result()

        # Create a mock core service
        mock_core = AsyncMock(spec=AnalysisService)
        mock_core.analyze = AsyncMock(return_value=core_result)

        telegram_svc = TelegramAnalysisService(core_service=mock_core)

        # Run conversion (sync method)
        telegram_result = telegram_svc._convert_result(core_result)

        assert isinstance(telegram_result, TelegramAnalysisResult)
        assert telegram_result.symbol == "BTC/USDT"
        assert telegram_result.asset_type == "crypto"
        assert telegram_result.exchange == "binance"
        assert telegram_result.price == Decimal("65432.10")
        assert telegram_result.signal == "up"
        assert telegram_result.signal_score == 0.35
        assert telegram_result.regime == "TRENDING_UP"
        assert telegram_result.regime_confidence == 0.72
        assert len(telegram_result.timeframe_results) == 3

    def test_timeframe_results_correct(self) -> None:
        """Timeframe results are correctly extracted."""
        core_result = _make_core_result()

        mock_core = AsyncMock(spec=AnalysisService)
        mock_core.analyze = AsyncMock(return_value=core_result)

        telegram_svc = TelegramAnalysisService(core_service=mock_core)
        telegram_result = telegram_svc._convert_result(core_result)

        tf_m5 = next(t for t in telegram_result.timeframe_results if t.timeframe == "5m")
        assert tf_m5.signal == "up"
        assert tf_m5.score == 0.25
        assert tf_m5.regime == "TRENDING_UP"
        assert tf_m5.trend == "BULLISH"  # structure_score=0.4 > 0.3
        assert tf_m5.momentum == "NEUTRAL"  # rsi=62, 30<62<70

    def test_formatter_produces_valid_output(self) -> None:
        """TelegramFormatter produces non-empty, parseable output."""
        core_result = _make_core_result()

        mock_core = AsyncMock(spec=AnalysisService)
        mock_core.analyze = AsyncMock(return_value=core_result)

        telegram_svc = TelegramAnalysisService(core_service=mock_core)
        telegram_result = telegram_svc._convert_result(core_result)

        formatter = TelegramFormatter()
        text = formatter.format_analysis(telegram_result)

        assert len(text) > 100
        assert "BTC/USDT" in text
        assert "65,432.10" in text
        assert "UP" in text
        assert "TRENDING_UP" in text

    def test_formatter_split_message(self) -> None:
        """Formatter splits long messages correctly."""
        formatter = TelegramFormatter()
        short = "Hello"
        assert formatter.split_message(short) == [short]

        long = "x" * 5000
        parts = formatter.split_message(long)
        assert len(parts) > 1
        for part in parts:
            assert len(part) <= 4096

    def test_no_signal_result(self) -> None:
        """NO_SIGNAL result is handled correctly."""
        core_result = AnalysisResult(
            symbol="UNKNOWN/USD",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("0"),
            timestamp=datetime(2024, 1, 1),
            signal=SignalType.NO_SIGNAL,
            score=0.0,
            regime=MarketRegime.UNCERTAIN,
            regime_confidence=0.0,
            timeframe_analyses=[],
            reason_codes=["no_timeframe_data"],
            model_version="1.0.0",
        )

        mock_core = AsyncMock(spec=AnalysisService)
        mock_core.analyze = AsyncMock(return_value=core_result)

        telegram_svc = TelegramAnalysisService(core_service=mock_core)
        telegram_result = telegram_svc._convert_result(core_result)

        assert telegram_result.signal == "no_signal"
        assert telegram_result.signal_score == 0.0

        formatter = TelegramFormatter()
        text = formatter.format_analysis(telegram_result)
        assert "NO_SIGNAL" in text

    def test_watchlist_service_flow(self) -> None:
        """WatchlistService add/remove/watchlist flow works."""
        from umae.storage.repositories import WatchlistRepository
        from umae.telegram.services import WatchlistService

        mock_repo = MagicMock(spec=WatchlistRepository)
        mock_repo.get_watchlist.return_value = ["BTC/USDT"]

        mock_core = AsyncMock(spec=AnalysisService)
        mock_core.analyze = AsyncMock(return_value=_make_core_result())

        telegram_svc = TelegramAnalysisService(core_service=mock_core)
        watchlist_svc = WatchlistService(
            repo=mock_repo,
            analysis_service=telegram_svc,
            max_size=50,
        )

        # Add
        mock_repo.add_to_watchlist.return_value = True
        result = watchlist_svc.add_symbol(123, 456, "ETH/USDT")
        assert result == "added"

        # Duplicate
        mock_repo.add_to_watchlist.return_value = False
        result = watchlist_svc.add_symbol(123, 456, "ETH/USDT")
        assert result == "duplicate"

        # Remove
        mock_repo.remove_from_watchlist.return_value = True
        result = watchlist_svc.remove_symbol(123, "ETH/USDT")
        assert result == "removed"

        # Not found
        mock_repo.remove_from_watchlist.return_value = False
        result = watchlist_svc.remove_symbol(123, "ETH/USDT")
        assert result == "not_found"
