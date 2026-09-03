"""Tests for candle aggregation."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from umae.candles.aggregation import (
    AggregationError,
    aggregate_candles,
    can_aggregate,
    validate_aggregation,
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


class TestCanAggregate:
    """Tests for can_aggregate function."""

    def test_valid_aggregation(self) -> None:
        """Test valid aggregation combinations."""
        assert can_aggregate(Timeframe.M1, Timeframe.M3)
        assert can_aggregate(Timeframe.M1, Timeframe.M5)
        assert can_aggregate(Timeframe.M5, Timeframe.M15)
        assert can_aggregate(Timeframe.M5, Timeframe.H1)
        assert can_aggregate(Timeframe.H1, Timeframe.D1)
        assert can_aggregate(Timeframe.D1, Timeframe.W1)

    def test_invalid_aggregation(self) -> None:
        """Test invalid aggregation combinations."""
        assert not can_aggregate(Timeframe.M5, Timeframe.M3)
        assert not can_aggregate(Timeframe.M1, Timeframe.M1)
        assert not can_aggregate(Timeframe.H1, Timeframe.M5)


class TestAggregateCandles:
    """Tests for aggregate_candles function."""

    def test_empty_candle_set(self) -> None:
        """Test aggregating empty candle set."""
        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M1,
        )
        result = aggregate_candles(cs, Timeframe.M5)
        assert result.count == 0

    def test_basic_aggregation(self) -> None:
        """Test basic 1m to 5m aggregation."""
        # Create 5 candles for 1 minute
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        candles = [
            create_candle(
                timestamp=base_time + timedelta(minutes=i),
                open_price=100 + i,
                high_price=110 + i,
                low_price=90 + i,
                close_price=105 + i,
                volume=1000 + i * 100,
            )
            for i in range(5)
        ]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M1,
            candles=candles,
        )

        result = aggregate_candles(cs, Timeframe.M5)

        assert result.count == 1
        assert result.timeframe == Timeframe.M5
        assert result.candles[0].timestamp == base_time
        assert result.candles[0].open == Decimal("100")  # First candle's open
        assert result.candles[0].close == Decimal("109")  # Last candle's close
        assert result.candles[0].high == Decimal("114")  # Max high
        assert result.candles[0].low == Decimal("90")  # Min low
        assert result.candles[0].volume == Decimal(
            "6000"
        )  # Sum of volumes: 1000+1100+1200+1300+1400

    def test_multiple_groups(self) -> None:
        """Test aggregation with multiple groups."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        candles = [
            create_candle(
                timestamp=base_time + timedelta(minutes=i),
                open_price=100,
                high_price=110,
                low_price=90,
                close_price=105,
                volume=1000,
            )
            for i in range(10)  # 2 groups of 5
        ]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M1,
            candles=candles,
        )

        result = aggregate_candles(cs, Timeframe.M5)

        assert result.count == 2

    def test_incomplete_candles_excluded(self) -> None:
        """Test that incomplete candles are excluded."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        candles = [
            create_candle(
                timestamp=base_time + timedelta(minutes=i),
                is_complete=i < 4,  # Last candle incomplete
            )
            for i in range(5)
        ]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M1,
            candles=candles,
        )

        result = aggregate_candles(cs, Timeframe.M5)

        # Should only aggregate the 4 complete candles
        assert result.count == 1

    def test_invalid_aggregation_raises(self) -> None:
        """Test that invalid aggregation raises error."""
        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M5,
        )

        with pytest.raises(AggregationError):
            aggregate_candles(cs, Timeframe.M3)

    def test_aggregation_preserves_source(self) -> None:
        """Test that aggregation preserves source info."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        candles = [create_candle(timestamp=base_time + timedelta(minutes=i)) for i in range(5)]

        cs = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M1,
            candles=candles,
            source="binance",
            data_version="test_v1",
        )

        result = aggregate_candles(cs, Timeframe.M5)

        assert result.source == "binance"
        assert result.data_version == "test_v1"


class TestValidateAggregation:
    """Tests for validate_aggregation function."""

    def test_valid_aggregation(self) -> None:
        """Test validation of valid aggregation."""
        base_time = datetime(2024, 1, 1, 12, 0, 0)
        source_candles = [
            create_candle(timestamp=base_time + timedelta(minutes=i)) for i in range(5)
        ]
        target_candles = [
            create_candle(
                timestamp=base_time, open_price=100, high_price=114, low_price=90, close_price=109
            )
        ]

        source = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M1,
            candles=source_candles,
        )
        target = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M5,
            candles=target_candles,
        )

        errors = validate_aggregation(source, target)
        assert len(errors) == 0

    def test_empty_target(self) -> None:
        """Test validation with empty target."""
        source = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M1,
            candles=[create_candle(timestamp=datetime(2024, 1, 1))],
        )
        target = CandleSet(
            symbol="BTC/USDT",
            timeframe=Timeframe.M5,
            candles=[],
        )

        errors = validate_aggregation(source, target)
        assert any("no candles" in e.lower() for e in errors)
