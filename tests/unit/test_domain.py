"""Tests for domain models."""

from datetime import datetime
from decimal import Decimal

import pytest

from umae.domain.enums import (
    Timeframe,
)
from umae.domain.models import (
    Candle,
    CandleSet,
    FeeModel,
    SignalScore,
)


class TestTimeframe:
    """Tests for Timeframe enum."""

    def test_minutes_conversion(self) -> None:
        """Test timeframe to minutes conversion."""
        assert Timeframe.M1.minutes == 1
        assert Timeframe.M3.minutes == 3
        assert Timeframe.M5.minutes == 5
        assert Timeframe.M15.minutes == 15
        assert Timeframe.M30.minutes == 30
        assert Timeframe.H1.minutes == 60
        assert Timeframe.H4.minutes == 240
        assert Timeframe.D1.minutes == 1440
        assert Timeframe.W1.minutes == 10080

    def test_can_aggregate_from(self) -> None:
        """Test aggregation validity."""
        # Valid aggregations
        assert Timeframe.M3.can_aggregate_from(Timeframe.M1)
        assert Timeframe.M5.can_aggregate_from(Timeframe.M1)
        assert Timeframe.M15.can_aggregate_from(Timeframe.M5)
        assert Timeframe.H1.can_aggregate_from(Timeframe.M5)
        assert Timeframe.D1.can_aggregate_from(Timeframe.H1)
        assert Timeframe.W1.can_aggregate_from(Timeframe.D1)

        # Invalid aggregations
        assert not Timeframe.M5.can_aggregate_from(Timeframe.M3)
        assert not Timeframe.M1.can_aggregate_from(Timeframe.M5)
        assert not Timeframe.M1.can_aggregate_from(Timeframe.M1)  # Same timeframe


class TestCandle:
    """Tests for Candle model."""

    def test_valid_candle(self) -> None:
        """Test creating a valid candle."""
        candle = Candle(
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1000"),
        )
        assert candle.open == Decimal("100")
        assert candle.high == Decimal("110")
        assert candle.low == Decimal("90")
        assert candle.close == Decimal("105")
        assert candle.is_complete is True

    def test_candle_high_low_mismatch(self) -> None:
        """Test candle with high < low raises error."""
        with pytest.raises(ValueError, match=r"High.*must be >= low"):
            Candle(
                timestamp=datetime(2024, 1, 1),
                open=Decimal("100"),
                high=Decimal("90"),  # Low
                low=Decimal("110"),  # High
                close=Decimal("100"),
                volume=Decimal("1000"),
            )

    def test_candle_open_outside_range(self) -> None:
        """Test candle with open outside high-low range."""
        with pytest.raises(ValueError, match=r"Open.*must be between"):
            Candle(
                timestamp=datetime(2024, 1, 1),
                open=Decimal("120"),  # Above high
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("100"),
                volume=Decimal("1000"),
            )

    def test_candle_negative_volume(self) -> None:
        """Test candle with negative volume raises error."""
        with pytest.raises(ValueError, match=r"Volume.*must be >= 0"):
            Candle(
                timestamp=datetime(2024, 1, 1),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("100"),
                volume=Decimal("-100"),
            )


class TestCandleSet:
    """Tests for CandleSet model."""

    def test_empty_candle_set(self) -> None:
        """Test empty candle set."""
        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
        )
        assert cs.count == 0
        assert cs.start is None
        assert cs.end is None
        assert cs.is_continuous() is True

    def test_candle_set_properties(self) -> None:
        """Test candle set properties."""
        candles = [
            Candle(
                timestamp=datetime(2024, 1, 1, i, 0, 0),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("1000"),
            )
            for i in range(5)
        ]
        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=candles,
        )
        assert cs.count == 5
        assert cs.start == datetime(2024, 1, 1, 0, 0, 0)
        assert cs.end == datetime(2024, 1, 1, 4, 0, 0)

    def test_candle_set_continuous(self) -> None:
        """Test continuous candle set."""
        candles = [
            Candle(
                timestamp=datetime(2024, 1, 1, i, 0, 0),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("1000"),
            )
            for i in range(5)
        ]
        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=candles,
        )
        assert cs.is_continuous() is True
        assert cs.gaps() == []

    def test_candle_set_with_gap(self) -> None:
        """Test candle set with gap."""
        candles = [
            Candle(
                timestamp=datetime(2024, 1, 1, i, 0, 0),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("1000"),
            )
            for i in [0, 1, 3, 4]  # Missing hour 2
        ]
        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=candles,
        )
        assert cs.is_continuous() is False
        gaps = cs.gaps()
        assert len(gaps) == 1


class TestFeeModel:
    """Tests for FeeModel."""

    def test_default_fees(self) -> None:
        """Test default fee calculation."""
        fee_model = FeeModel()
        fee = fee_model.calculate_fee(Decimal("1000"))
        assert fee == Decimal("1")  # 0.1% of 1000

    def test_custom_fees(self) -> None:
        """Test custom fee calculation."""
        fee_model = FeeModel(
            taker_fee=Decimal("0.002"),
            maker_fee=Decimal("0.001"),
        )
        taker_fee = fee_model.calculate_fee(Decimal("1000"), is_maker=False)
        maker_fee = fee_model.calculate_fee(Decimal("1000"), is_maker=True)
        assert taker_fee == Decimal("2")
        assert maker_fee == Decimal("1")

    def test_minimum_fee(self) -> None:
        """Test minimum fee enforcement."""
        fee_model = FeeModel(
            taker_fee=Decimal("0.001"),
            minimum_fee=Decimal("5"),
        )
        fee = fee_model.calculate_fee(Decimal("100"))  # 0.1% = 0.1
        assert fee == Decimal("5")  # Minimum enforced


class TestSignalScore:
    """Tests for SignalScore."""

    def test_raw_score_only(self) -> None:
        """Test raw score without calibration."""
        score = SignalScore(raw_score=0.75)
        assert score.raw_score == 0.75
        assert score.calibrated_confidence is None

    def test_calibrated_score(self) -> None:
        """Test calibrated score."""
        score = SignalScore(
            raw_score=0.75,
            calibrated_confidence=0.68,
            calibration_method="isotonic",
        )
        assert score.calibrated_confidence == 0.68
