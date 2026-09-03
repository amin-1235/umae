"""Core enums for UMAE domain models."""

from enum import Enum


class Timeframe(Enum):
    """Supported timeframes for candle data."""

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M20 = "20m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H12 = "12h"
    D1 = "1D"
    W1 = "1W"

    @property
    def minutes(self) -> int:
        """Convert timeframe to minutes."""
        mapping = {
            "1m": 1,
            "3m": 3,
            "5m": 5,
            "15m": 15,
            "20m": 20,
            "30m": 30,
            "1h": 60,
            "2h": 120,
            "4h": 240,
            "6h": 360,
            "12h": 720,
            "1D": 1440,
            "1W": 10080,
        }
        return mapping[self.value]

    def can_aggregate_from(self, source: "Timeframe") -> bool:
        """Check if this timeframe can be aggregated from source."""
        return self.minutes % source.minutes == 0 and self.minutes > source.minutes


class AssetType(Enum):
    """Types of financial assets."""

    CRYPTO = "crypto"
    STOCK = "stock"
    FOREX = "forex"
    INDEX = "index"
    COMMODITY = "commodity"
    ETF = "etf"


class SignalType(Enum):
    """Signal types for analysis output."""

    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"
    NO_SIGNAL = "no_signal"


class MarketRegime(Enum):
    """Market regime classifications."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BREAKOUT = "breakout"
    UNCERTAIN = "uncertain"


class FeatureGroup(Enum):
    """Feature group categories."""

    TREND = "trend"
    MOMENTUM = "momentum"
    VOLUME = "volume"
    VOLATILITY = "volatility"
    PRICE_STRUCTURE = "price_structure"


class OrderSide(Enum):
    """Order sides for trading."""

    LONG = "long"
    SHORT = "short"


class PositionSizing(Enum):
    """Position sizing methods."""

    FIXED = "fixed"
    PERCENTAGE = "percentage"
