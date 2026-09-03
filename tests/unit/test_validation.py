"""Tests for data validation."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from umae.candles.validation import (
    CandleValidator,
    ValidationSeverity,
    validate_candle,
)
from umae.domain.enums import Timeframe
from umae.domain.models import Candle, CandleSet


def create_candle(
    timestamp: datetime,
    open_price: float = 100.0,
    high_price: float = 110.0,
    low_price: float = 90.0,
    close_price: float = 105.0,
    volume: float = 1000.0,
    is_complete: bool = True,
) -> Candle:
    """Create a test candle."""
    return Candle(
        timestamp=timestamp,
        open=Decimal(str(open_price)),
        high=Decimal(str(high_price)),
        low=Decimal(str(low_price)),
        close=Decimal(str(close_price)),
        volume=Decimal(str(volume)),
        is_complete=is_complete,
    )


class TestCandleValidator:
    """Tests for CandleValidator."""

    def test_valid_candle_set(self) -> None:
        """Test validation of valid candle set."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        candles = [create_candle(timestamp=base_time + timedelta(hours=i)) for i in range(5)]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=candles,
        )

        validator = CandleValidator()
        result = validator.validate(cs)

        assert result.is_valid is True
        assert result.error_count == 0
        assert len(result.valid_candles) == 5

    def test_invalid_ohlc(self) -> None:
        """Test detection of invalid OHLC using raw model data."""
        from unittest.mock import MagicMock

        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create a mock candle that bypasses domain validation
        invalid_candle = MagicMock()
        invalid_candle.timestamp = base_time
        invalid_candle.open = Decimal("100")
        invalid_candle.high = Decimal("90")  # High < Low (invalid)
        invalid_candle.low = Decimal("110")
        invalid_candle.close = Decimal("105")
        invalid_candle.volume = Decimal("1000")
        invalid_candle.is_complete = True

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=[invalid_candle],
        )

        validator = CandleValidator()
        result = validator.validate(cs)

        assert result.is_valid is False
        assert result.error_count > 0

    def test_duplicate_detection(self) -> None:
        """Test duplicate timestamp detection."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        candles = [
            create_candle(timestamp=base_time),
            create_candle(timestamp=base_time),  # Duplicate
            create_candle(timestamp=base_time + timedelta(hours=1)),
        ]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=candles,
        )

        validator = CandleValidator()
        result = validator.validate(cs)

        assert result.is_valid is False
        assert any(issue.code == "DUPLICATE_TIMESTAMP" for issue in result.issues)

    def test_negative_volume(self) -> None:
        """Test negative volume detection using mock."""
        from unittest.mock import MagicMock

        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create a mock candle with negative volume
        invalid_candle = MagicMock()
        invalid_candle.timestamp = base_time
        invalid_candle.open = Decimal("100")
        invalid_candle.high = Decimal("110")
        invalid_candle.low = Decimal("90")
        invalid_candle.close = Decimal("105")
        invalid_candle.volume = Decimal("-100")
        invalid_candle.is_complete = True

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=[invalid_candle],
        )

        validator = CandleValidator()
        result = validator.validate(cs)

        assert result.is_valid is False
        assert any(issue.code == "VOLUME_NEGATIVE" for issue in result.issues)

    def test_missing_candles_detection(self) -> None:
        """Test missing candles detection."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        candles = [
            create_candle(timestamp=base_time),
            create_candle(timestamp=base_time + timedelta(hours=2)),  # Missing 1 hour
        ]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=candles,
        )

        validator = CandleValidator()
        result = validator.validate(cs)

        assert any(issue.code == "MISSING_CANDLES" for issue in result.issues)

    def test_stale_data_detection(self) -> None:
        """Test stale data detection."""
        # Create candle from 2 hours ago (stale)
        base_time = datetime.utcnow() - timedelta(hours=2)
        candles = [
            create_candle(timestamp=base_time),
        ]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=candles,
        )

        validator = CandleValidator(stale_threshold_seconds=3600)
        result = validator.validate(cs)

        assert any(issue.code == "STALE_DATA" for issue in result.issues)

    def test_quality_score(self) -> None:
        """Test quality score calculation using mock."""
        from unittest.mock import MagicMock

        base_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create mock invalid candle
        invalid_candle = MagicMock()
        invalid_candle.timestamp = base_time + timedelta(hours=3)
        invalid_candle.open = Decimal("100")
        invalid_candle.high = Decimal("90")  # Invalid: high < low
        invalid_candle.low = Decimal("110")
        invalid_candle.close = Decimal("105")
        invalid_candle.volume = Decimal("1000")
        invalid_candle.is_complete = True

        # 3 valid, 1 invalid
        candles = [
            create_candle(timestamp=base_time),
            create_candle(timestamp=base_time + timedelta(hours=1)),
            create_candle(timestamp=base_time + timedelta(hours=2)),
            invalid_candle,
        ]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            candles=candles,
        )

        validator = CandleValidator()
        result = validator.validate(cs)

        assert result.quality_score == pytest.approx(0.75, rel=0.01)


class TestValidateCandle:
    """Tests for validate_candle convenience function."""

    def test_valid_candle(self) -> None:
        """Test validation of valid candle."""
        candle = create_candle(timestamp=datetime(2024, 1, 1))
        issues = validate_candle(candle)
        assert len(issues) == 0

    def test_invalid_ohlc(self) -> None:
        """Test validation of invalid OHLC using mock."""
        from unittest.mock import MagicMock

        # Create a mock candle with invalid OHLC
        invalid_candle = MagicMock()
        invalid_candle.timestamp = datetime(2024, 1, 1)
        invalid_candle.open = Decimal("100")
        invalid_candle.high = Decimal("90")  # High < Low
        invalid_candle.low = Decimal("110")
        invalid_candle.close = Decimal("105")
        invalid_candle.volume = Decimal("1000")

        issues = validate_candle(invalid_candle)
        assert len(issues) > 0
        assert any(i.severity == ValidationSeverity.ERROR for i in issues)
