"""Candle aggregation engine for UMAE."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from umae.domain.models import Candle, CandleSet

if TYPE_CHECKING:
    from umae.domain.enums import Timeframe

logger = logging.getLogger(__name__)


class AggregationError(Exception):
    """Error during candle aggregation."""


def can_aggregate(source: Timeframe, target: Timeframe) -> bool:
    """Check if source timeframe can be aggregated to target.

    Args:
        source: Source timeframe
        target: Target timeframe

    Returns:
        True if aggregation is valid
    """
    return target.minutes % source.minutes == 0 and target.minutes > source.minutes


def aggregate_candles(
    candle_set: CandleSet,
    target_timeframe: Timeframe,
    source_timeframe: Timeframe | None = None,
) -> CandleSet:
    """Aggregate candles from source to target timeframe.

    Args:
        candle_set: Source candle set
        target_timeframe: Target timeframe to aggregate to
        source_timeframe: Source timeframe (inferred from CandleSet if not provided)

    Returns:
        New CandleSet with aggregated candles

    Raises:
        AggregationError: If aggregation is not possible
    """
    if source_timeframe is None:
        source_timeframe = candle_set.timeframe

    if not can_aggregate(source_timeframe, target_timeframe):
        msg = f"Cannot aggregate from {source_timeframe.value} to {target_timeframe.value}"
        raise AggregationError(msg)

    if not candle_set.candles:
        return CandleSet(
            symbol=candle_set.symbol,
            timeframe=target_timeframe,
            candles=[],
            source=candle_set.source,
            data_version=candle_set.data_version,
        )

    # Filter out incomplete candles
    complete_candles = [c for c in candle_set.candles if c.is_complete]

    if not complete_candles:
        return CandleSet(
            symbol=candle_set.symbol,
            timeframe=target_timeframe,
            candles=[],
            source=candle_set.source,
            data_version=candle_set.data_version,
        )

    # Sort by timestamp
    complete_candles.sort(key=lambda c: c.timestamp)

    # Group candles by target timeframe boundaries
    grouped = _group_candles_by_boundary(complete_candles, target_timeframe)

    # Aggregate each group
    aggregated: list[Candle] = []
    for group in grouped:
        if group:
            candle = _aggregate_group(group)
            if candle:
                aggregated.append(candle)

    return CandleSet(
        symbol=candle_set.symbol,
        timeframe=target_timeframe,
        candles=aggregated,
        source=candle_set.source,
        data_version=candle_set.data_version,
    )


def _group_candles_by_boundary(
    candles: list[Candle],
    target_timeframe: Timeframe,
) -> list[list[Candle]]:
    """Group candles by target timeframe boundaries.

    Args:
        candles: Sorted list of candles
        target_timeframe: Target timeframe for grouping

    Returns:
        List of candle groups
    """
    if not candles:
        return []

    target_minutes = target_timeframe.minutes
    groups: list[list[Candle]] = []
    current_group: list[Candle] = []
    current_boundary: datetime | None = None

    for candle in candles:
        # Calculate boundary for this candle
        boundary = _get_boundary(candle.timestamp, target_minutes)

        if current_boundary is None:
            current_boundary = boundary

        if boundary != current_boundary:
            # New boundary, save current group and start new one
            if current_group:
                groups.append(current_group)
            current_group = [candle]
            current_boundary = boundary
        else:
            current_group.append(candle)

    # Add the last group
    if current_group:
        groups.append(current_group)

    return groups


def _get_boundary(timestamp: datetime, target_minutes: int) -> datetime:
    """Get the boundary timestamp for a given target timeframe.

    Args:
        timestamp: Input timestamp
        target_minutes: Target timeframe in minutes

    Returns:
        Boundary timestamp
    """
    # Convert to minutes since epoch
    epoch = datetime(2000, 1, 1)
    minutes_since_epoch = int((timestamp - epoch).total_seconds() / 60)

    # Find the boundary
    boundary_minutes = (minutes_since_epoch // target_minutes) * target_minutes

    return epoch + timedelta(minutes=boundary_minutes)


def _aggregate_group(group: list[Candle]) -> Candle | None:
    """Aggregate a group of candles into a single candle.

    Args:
        group: List of candles to aggregate (same boundary)

    Returns:
        Aggregated candle or None if group is empty
    """
    if not group:
        return None

    # Use first candle's timestamp as the aggregated timestamp
    timestamp = group[0].timestamp

    # Aggregate OHLCV
    open_price = group[0].open
    close_price = group[-1].close
    high_price = max(c.high for c in group)
    low_price = min(c.low for c in group)
    volume = sum((c.volume for c in group), Decimal("0"))

    # Optional fields
    quote_volume = None
    if any(c.quote_volume is not None for c in group):
        quote_volume = sum((c.quote_volume or Decimal("0") for c in group), Decimal("0"))

    trades_count = None
    if any(c.trades_count is not None for c in group):
        trades_count = sum(c.trades_count or 0 for c in group)

    return Candle(
        timestamp=timestamp,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        quote_volume=quote_volume,
        trades_count=trades_count,
        is_complete=True,
    )


def aggregate_to_timeframes(
    candle_set: CandleSet,
    target_timeframes: list[Timeframe],
) -> dict[Timeframe, CandleSet]:
    """Aggregate a candle set to multiple target timeframes.

    Args:
        candle_set: Source candle set
        target_timeframes: List of target timeframes

    Returns:
        Dictionary mapping timeframe to aggregated CandleSet
    """
    results: dict[Timeframe, CandleSet] = {}

    for target in target_timeframes:
        if can_aggregate(candle_set.timeframe, target):
            results[target] = aggregate_candles(candle_set, target)
        else:
            logger.warning(f"Cannot aggregate from {candle_set.timeframe.value} to {target.value}")

    return results


def validate_aggregation(
    source: CandleSet,
    target: CandleSet,
    tolerance: float = 1.0,
) -> list[str]:
    """Validate aggregation results.

    Args:
        source: Source candle set
        target: Aggregated candle set
        tolerance: Tolerance for numeric comparisons

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    if not target.candles:
        errors.append("Target has no candles")
        return errors

    # Check timestamp alignment
    for candle in target.candles:
        boundary = _get_boundary(candle.timestamp, target.timeframe.minutes)
        if candle.timestamp != boundary:
            errors.append(f"Candle at {candle.timestamp} not aligned to boundary {boundary}")

    # Check OHLC consistency
    for candle in target.candles:
        if candle.high < candle.low:
            errors.append(f"Candle at {candle.timestamp}: high < low")
        if candle.open > candle.high or candle.open < candle.low:
            errors.append(f"Candle at {candle.timestamp}: open outside range")
        if candle.close > candle.high or candle.close < candle.low:
            errors.append(f"Candle at {candle.timestamp}: close outside range")

    # Check ordering
    for i in range(1, len(target.candles)):
        if target.candles[i].timestamp <= target.candles[i - 1].timestamp:
            errors.append(
                f"Candles not in order at index {i}: "
                f"{target.candles[i].timestamp} <= {target.candles[i - 1].timestamp}"
            )

    return errors
