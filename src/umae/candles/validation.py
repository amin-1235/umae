"""Data validation for candle data."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from umae.domain.enums import Timeframe
    from umae.domain.models import Candle, CandleSet

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    ERROR = "error"  # Data is invalid, cannot process
    WARNING = "warning"  # Data has issues but can be processed
    INFO = "info"  # Minor issues


@dataclass
class ValidationIssue:
    """Single validation issue."""

    severity: ValidationSeverity
    code: str
    message: str
    timestamp: datetime | None = None
    candle_index: int | None = None


@dataclass
class ValidationResult:
    """Result of data validation."""

    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    valid_candles: list[Candle] = field(default_factory=list)
    rejected_candles: list[Candle] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    @property
    def error_count(self) -> int:
        """Count of errors."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Count of warnings."""
        return len(self.warnings)

    @property
    def quality_score(self) -> float:
        """Data quality score (0.0 to 1.0)."""
        total = len(self.valid_candles) + len(self.rejected_candles)
        if total == 0:
            return 0.0
        return len(self.valid_candles) / total


class CandleValidator:
    """Validator for candle data."""

    def __init__(
        self,
        check_duplicates: bool = True,
        check_missing: bool = True,
        check_ohlc: bool = True,
        check_timestamps: bool = True,
        check_volume: bool = True,
        check_stale: bool = True,
        stale_threshold_seconds: int = 3600,
    ) -> None:
        """Initialize validator.

        Args:
            check_duplicates: Check for duplicate candles
            check_missing: Check for missing candles
            check_ohlc: Check OHLC consistency
            check_timestamps: Check timestamp ordering
            check_volume: Check volume validity
            check_stale: Check for stale data
            stale_threshold_seconds: Threshold for stale data
        """
        self.check_duplicates = check_duplicates
        self.check_missing = check_missing
        self.check_ohlc = check_ohlc
        self.check_timestamps = check_timestamps
        self.check_volume = check_volume
        self.check_stale = check_stale
        self.stale_threshold_seconds = stale_threshold_seconds

    def validate(self, candle_set: CandleSet) -> ValidationResult:
        """Validate a candle set.

        Args:
            candle_set: CandleSet to validate

        Returns:
            ValidationResult with issues and valid/rejected candles
        """
        issues: list[ValidationIssue] = []
        valid_candles: list[Candle] = []
        rejected_candles: list[Candle] = []

        candles = candle_set.candles
        if not candles:
            return ValidationResult(
                is_valid=True,
                issues=[],
                valid_candles=[],
                rejected_candles=[],
            )

        # Track seen timestamps for duplicate detection
        seen_timestamps: set[datetime] = set()

        for i, candle in enumerate(candles):
            candle_issues = self._validate_candle(candle, i, candle_set.timeframe, seen_timestamps)

            # Check if any errors (not warnings)
            has_errors = any(issue.severity == ValidationSeverity.ERROR for issue in candle_issues)

            issues.extend(candle_issues)

            if has_errors:
                rejected_candles.append(candle)
            else:
                valid_candles.append(candle)
                seen_timestamps.add(candle.timestamp)

        # Check for missing candles (whole set)
        if self.check_missing:
            missing_issues = self._check_missing_candles(valid_candles, candle_set.timeframe)
            issues.extend(missing_issues)

        # Check for stale data (last candle)
        if self.check_stale and valid_candles:
            stale_issues = self._check_stale_data(valid_candles[-1])
            issues.extend(stale_issues)

        # Determine validity
        has_errors = any(issue.severity == ValidationSeverity.ERROR for issue in issues)

        return ValidationResult(
            is_valid=not has_errors,
            issues=issues,
            valid_candles=valid_candles,
            rejected_candles=rejected_candles,
        )

    def _validate_candle(
        self,
        candle: Candle,
        index: int,
        timeframe: Timeframe,
        seen_timestamps: set[datetime],
    ) -> list[ValidationIssue]:
        """Validate a single candle.

        Args:
            candle: Candle to validate
            index: Index in the candle list
            timeframe: Timeframe of the candle
            seen_timestamps: Set of already seen timestamps

        Returns:
            List of validation issues
        """
        issues: list[ValidationIssue] = []

        # Check OHLC consistency
        if self.check_ohlc:
            issues.extend(self._check_ohlc(candle, index))

        # Check volume
        if self.check_volume:
            issues.extend(self._check_volume(candle, index))

        # Check duplicates
        if self.check_duplicates:
            issues.extend(self._check_duplicate(candle, index, seen_timestamps))

        # Check timestamp ordering
        if self.check_timestamps and seen_timestamps:
            last_timestamp = max(seen_timestamps)
            if candle.timestamp <= last_timestamp:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="TIMESTAMP_ORDER",
                        message=f"Timestamp {candle.timestamp} not after previous timestamp",
                        timestamp=candle.timestamp,
                        candle_index=index,
                    )
                )

        return issues

    def _check_ohlc(self, candle: Candle, index: int) -> list[ValidationIssue]:
        """Check OHLC consistency.

        Args:
            candle: Candle to check
            index: Index in the candle list

        Returns:
            List of validation issues
        """
        issues: list[ValidationIssue] = []

        # High must be >= all other prices
        if candle.high < candle.open:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="OHLC_HIGH_LOW",
                    message=f"High ({candle.high}) < Open ({candle.open})",
                    timestamp=candle.timestamp,
                    candle_index=index,
                )
            )
        if candle.high < candle.close:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="OHLC_HIGH_CLOSE",
                    message=f"High ({candle.high}) < Close ({candle.close})",
                    timestamp=candle.timestamp,
                    candle_index=index,
                )
            )
        if candle.high < candle.low:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="OHLC_HIGH_LOW",
                    message=f"High ({candle.high}) < Low ({candle.low})",
                    timestamp=candle.timestamp,
                    candle_index=index,
                )
            )

        # Low must be <= all other prices
        if candle.low > candle.open:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="OHLC_LOW_OPEN",
                    message=f"Low ({candle.low}) > Open ({candle.open})",
                    timestamp=candle.timestamp,
                    candle_index=index,
                )
            )
        if candle.low > candle.close:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="OHLC_LOW_CLOSE",
                    message=f"Low ({candle.low}) > Close ({candle.close})",
                    timestamp=candle.timestamp,
                    candle_index=index,
                )
            )

        # Prices should be positive
        for field_name, value in [
            ("open", candle.open),
            ("high", candle.high),
            ("low", candle.low),
            ("close", candle.close),
        ]:
            if value <= 0:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code="OHLC_NON_POSITIVE",
                        message=f"{field_name} ({value}) must be positive",
                        timestamp=candle.timestamp,
                        candle_index=index,
                    )
                )

        return issues

    def _check_volume(self, candle: Candle, index: int) -> list[ValidationIssue]:
        """Check volume validity.

        Args:
            candle: Candle to check
            index: Index in the candle list

        Returns:
            List of validation issues
        """
        issues: list[ValidationIssue] = []

        if candle.volume < 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="VOLUME_NEGATIVE",
                    message=f"Volume ({candle.volume}) is negative",
                    timestamp=candle.timestamp,
                    candle_index=index,
                )
            )

        # Zero volume might be valid for some assets, flag as info
        if candle.volume == 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    code="VOLUME_ZERO",
                    message="Volume is zero",
                    timestamp=candle.timestamp,
                    candle_index=index,
                )
            )

        return issues

    def _check_duplicate(
        self,
        candle: Candle,
        index: int,
        seen_timestamps: set[datetime],
    ) -> list[ValidationIssue]:
        """Check for duplicate candles.

        Args:
            candle: Candle to check
            index: Index in the candle list
            seen_timestamps: Set of already seen timestamps

        Returns:
            List of validation issues
        """
        if candle.timestamp in seen_timestamps:
            return [
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="DUPLICATE_TIMESTAMP",
                    message=f"Duplicate timestamp: {candle.timestamp}",
                    timestamp=candle.timestamp,
                    candle_index=index,
                )
            ]
        return []

    def _check_missing_candles(
        self,
        candles: list[Candle],
        timeframe: Timeframe,
    ) -> list[ValidationIssue]:
        """Check for missing candles in sequence.

        Args:
            candles: List of valid candles
            timeframe: Timeframe of the candles

        Returns:
            List of validation issues
        """
        issues: list[ValidationIssue] = []

        if len(candles) < 2:
            return issues

        expected_interval = timeframe.minutes * 60  # seconds

        for i in range(1, len(candles)):
            diff = (candles[i].timestamp - candles[i - 1].timestamp).total_seconds()
            if abs(diff - expected_interval) > 1:  # Allow 1 second tolerance
                gap_size = int(diff / expected_interval) - 1
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        code="MISSING_CANDLES",
                        message=(
                            f"Gap between {candles[i - 1].timestamp} and "
                            f"{candles[i].timestamp}: ~{gap_size} candles missing"
                        ),
                        timestamp=candles[i - 1].timestamp,
                    )
                )

        return issues

    def _check_stale_data(self, last_candle: Candle) -> list[ValidationIssue]:
        """Check if data is stale.

        Args:
            last_candle: Last candle in the set

        Returns:
            List of validation issues
        """
        now = datetime.utcnow()
        age_seconds = (now - last_candle.timestamp).total_seconds()

        if age_seconds > self.stale_threshold_seconds:
            return [
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="STALE_DATA",
                    message=f"Data is {int(age_seconds)} seconds old (threshold: {self.stale_threshold_seconds}s)",
                    timestamp=last_candle.timestamp,
                )
            ]
        return []


def validate_candle(candle: Candle) -> list[ValidationIssue]:
    """Validate a single candle (convenience function).

    Args:
        candle: Candle to validate

    Returns:
        List of validation issues
    """
    validator = CandleValidator(
        check_duplicates=False,
        check_missing=False,
        check_stale=False,
    )
    return validator._check_ohlc(candle, 0) + validator._check_volume(candle, 0)
