"""Core domain models for UMAE."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from umae.domain.enums import (
    AssetType,
    FeatureGroup,
    MarketRegime,
    SignalType,
    Timeframe,
)


@dataclass(frozen=True)
class Candle:
    """Single OHLCV candle."""

    timestamp: datetime  # UTC, candle open time
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None = None
    trades_count: int | None = None
    is_complete: bool = True

    def __post_init__(self) -> None:
        """Validate candle data."""
        if self.high < self.low:
            msg = f"High ({self.high}) must be >= low ({self.low})"
            raise ValueError(msg)
        if self.open > self.high or self.open < self.low:
            msg = f"Open ({self.open}) must be between low ({self.low}) and high ({self.high})"
            raise ValueError(msg)
        if self.close > self.high or self.close < self.low:
            msg = f"Close ({self.close}) must be between low ({self.low}) and high ({self.high})"
            raise ValueError(msg)
        if self.volume < 0:
            msg = f"Volume ({self.volume}) must be >= 0"
            raise ValueError(msg)


@dataclass(frozen=True)
class TradingSession:
    """Trading session for a specific day."""

    day: int  # 0=Monday, 6=Sunday
    open_time: time
    close_time: time


@dataclass
class TradingHours:
    """Trading hours for an asset."""

    timezone: str
    sessions: list[TradingSession] = field(default_factory=list)
    holidays: list[date] = field(default_factory=list)
    early_closes: dict[date, time] = field(default_factory=dict)


@dataclass
class FeeModel:
    """Fee model for an asset/exchange."""

    taker_fee: Decimal = Decimal("0.001")  # 0.1%
    maker_fee: Decimal | None = None
    minimum_fee: Decimal | None = None

    def calculate_fee(self, trade_value: Decimal, is_maker: bool = False) -> Decimal:
        """Calculate fee for a trade."""
        fee_rate = self.maker_fee if is_maker and self.maker_fee is not None else self.taker_fee
        fee = trade_value * fee_rate
        if self.minimum_fee is not None:
            fee = max(fee, self.minimum_fee)
        return fee


@dataclass
class LiquidityInfo:
    """Liquidity information for an asset."""

    average_daily_volume: Decimal
    average_spread: Decimal
    average_slippage_100u: Decimal
    market_depth: Decimal | None = None
    last_updated: datetime | None = None


@dataclass
class AssetMetadata:
    """Metadata for a financial asset."""

    symbol: str
    asset_type: AssetType
    exchange: str
    timezone: str
    base_currency: str
    quote_currency: str
    tick_size: Decimal
    lot_size: Decimal | None = None
    trading_hours: TradingHours | None = None
    fee_model: FeeModel = field(default_factory=FeeModel)
    liquidity_info: LiquidityInfo | None = None
    data_adapter: str = ""
    metadata_version: str = "1.0.0"
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CandleSet:
    """Collection of candles for a specific symbol and timeframe."""

    symbol: str
    timeframe: Timeframe
    candles: list[Candle] = field(default_factory=list)
    source: str = ""
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    data_version: str = ""

    @property
    def start(self) -> datetime | None:
        """Get start timestamp."""
        if not self.candles:
            return None
        return self.candles[0].timestamp

    @property
    def end(self) -> datetime | None:
        """Get end timestamp."""
        if not self.candles:
            return None
        return self.candles[-1].timestamp

    @property
    def count(self) -> int:
        """Get number of candles."""
        return len(self.candles)

    def is_continuous(self) -> bool:
        """Check if candles are continuous (no gaps)."""
        if len(self.candles) < 2:
            return True
        expected_interval = self.timeframe.minutes * 60  # seconds
        for i in range(1, len(self.candles)):
            diff = (self.candles[i].timestamp - self.candles[i - 1].timestamp).total_seconds()
            if abs(diff - expected_interval) > 1:  # Allow 1 second tolerance
                return False
        return True

    def gaps(self) -> list[tuple[datetime, datetime]]:
        """Find gaps in candle data."""
        if len(self.candles) < 2:
            return []
        expected_interval = self.timeframe.minutes * 60
        result: list[tuple[datetime, datetime]] = []
        for i in range(1, len(self.candles)):
            diff = (self.candles[i].timestamp - self.candles[i - 1].timestamp).total_seconds()
            if abs(diff - expected_interval) > 1:
                result.append((self.candles[i - 1].timestamp, self.candles[i].timestamp))
        return result


@dataclass
class FeatureDefinition:
    """Definition of a computed feature."""

    name: str
    group: FeatureGroup
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    min_candles_required: int = 20
    version: str = "1.0.0"


@dataclass
class FeatureSet:
    """Computed features for a single candle."""

    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    features: dict[str, float] = field(default_factory=dict)
    feature_version: str = "1.0.0"
    computed_at: datetime = field(default_factory=datetime.utcnow)

    def get(self, feature_name: str) -> float | None:
        """Get a feature value by name."""
        return self.features.get(feature_name)

    def get_group(self, group: FeatureGroup) -> dict[str, float]:
        """Get all features for a group."""
        prefix = f"{group.value}_"
        return {k: v for k, v in self.features.items() if k.startswith(prefix)}


@dataclass
class RegimeResult:
    """Market regime detection result."""

    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    regime: MarketRegime
    confidence: float = 0.0
    indicators: dict[str, float] = field(default_factory=dict)
    computed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SignalScore:
    """Signal score with optional calibration."""

    raw_score: float = 0.0
    calibrated_confidence: float | None = None
    calibration_method: str | None = None
    calibration_version: str | None = None


@dataclass
class TimeframeSignal:
    """Signal from a single timeframe analysis."""

    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    signal: SignalType
    score: SignalScore = field(default_factory=SignalScore)
    features_used: dict[str, float] = field(default_factory=dict)
    regime: RegimeResult | None = None
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class CompositeSignal:
    """Final signal combining multiple timeframes."""

    timestamp: datetime
    symbol: str
    asset_type: AssetType
    exchange: str
    price: Decimal
    signal: SignalType
    score: SignalScore = field(default_factory=SignalScore)
    timeframe_signals: dict[Timeframe, TimeframeSignal] = field(default_factory=dict)
    regime: MarketRegime = MarketRegime.UNCERTAIN
    reason_codes: list[str] = field(default_factory=list)
    contributing_factors: dict[str, Any] = field(default_factory=dict)
    model_version: str = "1.0.0"
    data_version: str = ""


@dataclass
class SignalAudit:
    """Full audit record for a signal."""

    id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    symbol: str = ""
    asset_type: AssetType = AssetType.CRYPTO
    exchange: str = ""
    timeframe: Timeframe = Timeframe.D1
    price: Decimal = Decimal("0")
    signal: SignalType = SignalType.NO_SIGNAL
    raw_score: float = 0.0
    calibrated_confidence: float | None = None
    features: dict[str, float] = field(default_factory=dict)
    market_regime: MarketRegime = MarketRegime.UNCERTAIN
    regime_confidence: float = 0.0
    timeframe_signals: dict[str, str] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    contributing_factors: dict[str, Any] = field(default_factory=dict)
    model_version: str = "1.0.0"
    data_version: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
