"""Phase 2 hardening tests — signal consistency and auditability."""

from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal

from umae.domain.enums import AssetType, MarketRegime, SignalType, Timeframe
from umae.domain.models import (
    CompositeSignal,
    SignalScore,
    TimeframeSignal,
)
from umae.interfaces.analysis_service import AnalysisResult, TimeframeAnalysis
from umae.scoring.signal_composer import SignalComposer
from umae.telegram.formatter import TelegramFormatter
from umae.telegram.models import (
    AnalysisResult as TgAnalysisResult,
)
from umae.telegram.models import (
    DataQuality,
    FeatureSummary,
    ScoreBreakdown,
)


def _make_ts(
    tf: Timeframe,
    signal: SignalType,
    score: float,
    reasons: list[str] | None = None,
    regime: MarketRegime = MarketRegime.UNCERTAIN,
) -> TimeframeSignal:
    return TimeframeSignal(
        timestamp=datetime.utcnow(),
        symbol="BTCUSDT",
        timeframe=tf,
        signal=signal,
        score=SignalScore(raw_score=score),
        features_used={},
        regime=None,
        reason_codes=reasons or [],
    )


class TestHTFUnanimousBullish(unittest.TestCase):
    def test_all_htf_up(self):
        composer = SignalComposer()
        signals = {
            Timeframe.H4: _make_ts(Timeframe.H4, SignalType.UP, 0.3),
            Timeframe.D1: _make_ts(Timeframe.D1, SignalType.UP, 0.4),
            Timeframe.W1: _make_ts(Timeframe.W1, SignalType.UP, 0.2),
        }
        composite = CompositeSignal(
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("80000"),
            signal=SignalType.UP,
            score=SignalScore(raw_score=0.3),
            timeframe_signals=signals,
            regime=MarketRegime.TRENDING_UP,
        )
        result = composer.compose(composite)
        self.assertIn("htf_unanimous_bullish", result.reason_codes)
        self.assertNotIn("htf_unanimous_bearish", result.reason_codes)
        self.assertNotIn("htf_mixed", result.reason_codes)


class TestHTFUnanimousBearish(unittest.TestCase):
    def test_all_htf_down(self):
        composer = SignalComposer()
        signals = {
            Timeframe.H4: _make_ts(Timeframe.H4, SignalType.DOWN, -0.3),
            Timeframe.D1: _make_ts(Timeframe.D1, SignalType.DOWN, -0.4),
        }
        composite = CompositeSignal(
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("80000"),
            signal=SignalType.DOWN,
            score=SignalScore(raw_score=-0.3),
            timeframe_signals=signals,
            regime=MarketRegime.TRENDING_DOWN,
        )
        result = composer.compose(composite)
        self.assertIn("htf_unanimous_bearish", result.reason_codes)
        self.assertNotIn("htf_unanimous_bullish", result.reason_codes)
        self.assertNotIn("htf_mixed", result.reason_codes)


class TestHTFMixed(unittest.TestCase):
    def test_mixed_htf_signals(self):
        composer = SignalComposer()
        signals = {
            Timeframe.H4: _make_ts(Timeframe.H4, SignalType.UP, 0.3),
            Timeframe.D1: _make_ts(Timeframe.D1, SignalType.DOWN, -0.3),
            Timeframe.W1: _make_ts(Timeframe.W1, SignalType.UP, 0.2),
        }
        composite = CompositeSignal(
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("80000"),
            signal=SignalType.NEUTRAL,
            score=SignalScore(raw_score=0.05),
            timeframe_signals=signals,
            regime=MarketRegime.RANGING,
        )
        result = composer.compose(composite)
        self.assertIn("htf_mixed", result.reason_codes)
        self.assertNotIn("htf_unanimous_bullish", result.reason_codes)
        self.assertNotIn("htf_unanimous_bearish", result.reason_codes)


class TestHTFMissing(unittest.TestCase):
    def test_no_htf_data(self):
        composer = SignalComposer()
        signals = {
            Timeframe.M5: _make_ts(Timeframe.M5, SignalType.UP, 0.2),
            Timeframe.M15: _make_ts(Timeframe.M15, SignalType.UP, 0.15),
        }
        composite = CompositeSignal(
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("80000"),
            signal=SignalType.NO_SIGNAL,
            score=SignalScore(raw_score=0.0),
            timeframe_signals=signals,
        )
        result = composer.compose(composite)
        # No HTF signals → no htf_unanimous/mixed reason
        self.assertNotIn("htf_unanimous_bullish", result.reason_codes)
        self.assertNotIn("htf_unanimous_bearish", result.reason_codes)
        self.assertNotIn("htf_mixed", result.reason_codes)


class TestHTFInsufficientData(unittest.TestCase):
    def test_partial_htf_data(self):
        composer = SignalComposer()
        # Only one HTF — cannot be "unanimous" with 1 signal, but also not "mixed"
        signals = {
            Timeframe.D1: _make_ts(Timeframe.D1, SignalType.UP, 0.4),
            Timeframe.M5: _make_ts(Timeframe.M5, SignalType.UP, 0.1),
        }
        composite = CompositeSignal(
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("80000"),
            signal=SignalType.UP,
            score=SignalScore(raw_score=0.2),
            timeframe_signals=signals,
        )
        result = composer.compose(composite)
        # Single HTF signal → unanimous_bullish (all 1 are UP)
        self.assertIn("htf_unanimous_bullish", result.reason_codes)


class TestCalibratedConfidenceNA(unittest.TestCase):
    def test_none_when_uncalibrated(self):
        result = TgAnalysisResult(
            symbol="BTCUSDT",
            asset_type="crypto",
            exchange="binance",
            timestamp="2026-09-03",
            price=Decimal("80000"),
            data_quality=DataQuality(
                state="GOOD",
                freshness_seconds=10,
                completeness=1.0,
                candle_count=100,
                missing_candles=0,
            ),
            regime="TRENDING_UP",
            regime_confidence=0.6,
            signal="up",
            signal_score=0.5,
            calibrated_confidence=None,
        )
        formatter = TelegramFormatter()
        text = formatter.format_analysis(result)
        self.assertIn("Calibrated Confidence: N/A", text)
        self.assertNotIn("Calibrated Confidence: 50%", text)


class TestFeatureSummaryConsistency(unittest.TestCase):
    def test_trend_bullish(self):
        from umae.telegram.services import AnalysisService

        features = {
            "trend_ema_fast": 100.0,
            "trend_ema_slow": 99.0,
            "trend_ema_trend": 98.0,
            "trend_structure_score": 0.5,
        }
        result = AnalysisService._extract_trend(features)
        self.assertEqual(result, "BULLISH")

    def test_trend_bearish(self):
        from umae.telegram.services import AnalysisService

        features = {
            "trend_ema_fast": 98.0,
            "trend_ema_slow": 99.0,
            "trend_ema_trend": 100.0,
            "trend_structure_score": -0.5,
        }
        result = AnalysisService._extract_trend(features)
        self.assertEqual(result, "BEARISH")

    def test_trend_neutral(self):
        from umae.telegram.services import AnalysisService

        features = {"trend_structure_score": 0.1}
        result = AnalysisService._extract_trend(features)
        self.assertEqual(result, "NEUTRAL")

    def test_volume_high(self):
        from umae.telegram.services import AnalysisService

        result = AnalysisService._extract_volume({"volume_spike": 1.0, "volume_relative": 2.5})
        self.assertEqual(result, "HIGH")

    def test_volume_normal(self):
        from umae.telegram.services import AnalysisService

        result = AnalysisService._extract_volume({"volume_relative": 1.0})
        self.assertEqual(result, "NORMAL")

    def test_structure_bullish(self):
        from umae.telegram.services import AnalysisService

        features = {
            "trend_structure_hh": 1.0,
            "trend_structure_hl": 1.0,
            "trend_structure_score": 0.5,
        }
        result = AnalysisService._extract_structure(features)
        self.assertEqual(result, "BULLISH")


class TestScoreBreakdown(unittest.TestCase):
    def test_breakdown_in_result(self):
        result = TgAnalysisResult(
            symbol="BTCUSDT",
            asset_type="crypto",
            exchange="binance",
            timestamp="2026-09-03",
            price=Decimal("80000"),
            data_quality=DataQuality(
                state="GOOD",
                freshness_seconds=10,
                completeness=1.0,
                candle_count=100,
                missing_candles=0,
            ),
            regime="TRENDING_UP",
            regime_confidence=0.6,
            signal="up",
            signal_score=0.51,
            score_breakdown=ScoreBreakdown(
                htf_bias=0.30,
                trend_alignment=0.20,
                momentum=0.0,
                volume=0.0,
                structure=-0.05,
                regime_adjustment=0.06,
                total=0.51,
            ),
        )
        formatter = TelegramFormatter()
        text = formatter.format_analysis(result)
        self.assertIn("SCORE BREAKDOWN", text)
        self.assertIn("htf_bias", text)
        self.assertIn("total:", text)
        self.assertIn("+0.51", text)

    def test_sum_matches_total(self):
        sb = ScoreBreakdown(
            htf_bias=0.30,
            trend_alignment=0.20,
            momentum=0.0,
            volume=0.0,
            structure=-0.05,
            regime_adjustment=0.06,
            total=0.51,
        )
        computed_total = (
            sb.htf_bias
            + sb.trend_alignment
            + sb.momentum
            + sb.volume
            + sb.structure
            + sb.regime_adjustment
        )
        self.assertAlmostEqual(computed_total, sb.total, places=2)


class TestMissingTimeframeHandling(unittest.TestCase):
    def test_data_unavailable_in_analysis(self):
        ta = TimeframeAnalysis(
            timeframe=Timeframe.M5,
            signal=SignalType.NO_SIGNAL,
            score=0.0,
            regime=MarketRegime.UNCERTAIN,
            regime_confidence=0.0,
            features={},
            reason_codes=["DATA_UNAVAILABLE", "no_candle_data"],
        )
        self.assertIn("DATA_UNAVAILABLE", ta.reason_codes)
        self.assertEqual(ta.signal, SignalType.NO_SIGNAL)


class TestTargetContext(unittest.TestCase):
    def test_single_tf_target(self):
        result = AnalysisResult(
            symbol="BTCUSDT",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("80000"),
            timestamp=datetime.utcnow(),
            signal=SignalType.UP,
            score=0.5,
            regime=MarketRegime.TRENDING_UP,
            regime_confidence=0.6,
            target_timeframe=Timeframe.H1,
            context_timeframes=[Timeframe.M5, Timeframe.M15],
        )
        self.assertEqual(result.target_timeframe, Timeframe.H1)
        self.assertIn(Timeframe.M5, result.context_timeframes)
        self.assertIn(Timeframe.M15, result.context_timeframes)


class TestDataVersion(unittest.TestCase):
    def test_version_fields(self):
        result = AnalysisResult(
            symbol="BTCUSDT",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("80000"),
            timestamp=datetime.utcnow(),
            signal=SignalType.UP,
            score=0.5,
            regime=MarketRegime.TRENDING_UP,
            regime_confidence=0.6,
            model_version="0.1.0",
            feature_version="features-1.0.0",
            data_version="binance-rest-v1",
            provider="binance",
            provider_symbol="BTCUSDT",
        )
        self.assertEqual(result.model_version, "0.1.0")
        self.assertEqual(result.feature_version, "features-1.0.0")
        self.assertEqual(result.data_version, "binance-rest-v1")
        self.assertEqual(result.provider, "binance")


class TestDataQuality(unittest.TestCase):
    def test_quality_states(self):
        for state in ["GOOD", "DEGRADED", "STALE", "INCOMPLETE", "INVALID", "UNAVAILABLE"]:
            dq = DataQuality(
                state=state,
                freshness_seconds=0,
                completeness=1.0,
                candle_count=100,
                missing_candles=0,
            )
            self.assertEqual(dq.state, state)


class TestNO_SIGNALConditions(unittest.TestCase):
    def test_no_signal_on_insufficient_data(self):
        composer = SignalComposer()
        composite = CompositeSignal(
            timestamp=datetime.utcnow(),
            symbol="BTCUSDT",
            asset_type=AssetType.CRYPTO,
            exchange="binance",
            price=Decimal("80000"),
            signal=SignalType.NO_SIGNAL,
            score=SignalScore(raw_score=0.0),
            timeframe_signals={},
        )
        result = composer.compose(composite)
        self.assertEqual(result.signal, SignalType.NO_SIGNAL)
        self.assertIn("no_timeframe_data", result.reason_codes)


class TestFormatterOutput(unittest.TestCase):
    def test_all_sections_present(self):
        result = TgAnalysisResult(
            symbol="BTCUSDT",
            asset_type="crypto",
            exchange="binance",
            timestamp="2026-09-03",
            price=Decimal("80000"),
            data_quality=DataQuality(
                state="GOOD",
                freshness_seconds=10,
                completeness=1.0,
                candle_count=100,
                missing_candles=0,
            ),
            regime="TRENDING_UP",
            regime_confidence=0.6,
            signal="up",
            signal_score=0.5,
            feature_summary=FeatureSummary(
                trend="BULLISH",
                momentum="NEUTRAL",
                volume="NORMAL",
                volatility="NORMAL",
                structure="BULLISH",
            ),
            contributors=["+ HTF bullish bias", "+ 1D: EMA alignment"],
            reason_codes=["htf_unanimous_bullish", "ema_bullish_alignment"],
            score_breakdown=ScoreBreakdown(htf_bias=0.3, total=0.5),
        )
        formatter = TelegramFormatter()
        text = formatter.format_analysis(result)
        self.assertIn("UMAE ANALYSIS", text)
        self.assertIn("SIGNAL", text)
        self.assertIn("REGIME", text)
        self.assertIn("FEATURES", text)
        self.assertIn("CONTRIBUTORS", text)
        self.assertIn("REASONS", text)
        self.assertIn("META", text)
        self.assertIn("not advice", text)

    def test_no_confidence_percentage_when_none(self):
        result = TgAnalysisResult(
            symbol="BTCUSDT",
            asset_type="crypto",
            exchange="binance",
            timestamp="2026-09-03",
            price=Decimal("80000"),
            data_quality=DataQuality(
                state="GOOD",
                freshness_seconds=10,
                completeness=1.0,
                candle_count=100,
                missing_candles=0,
            ),
            regime="RANGING",
            regime_confidence=0.5,
            signal="neutral",
            signal_score=0.0,
        )
        formatter = TelegramFormatter()
        text = formatter.format_analysis(result)
        self.assertIn("Calibrated Confidence: N/A", text)
