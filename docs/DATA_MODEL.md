# Universal Market Analysis Engine (UMAE) - Data Model

## Overview

This document defines the core data structures and database schema for UMAE.

## Core Domain Models

### Candle

Represents a single OHLCV candle.

```python
@dataclass(frozen=True)
class Candle:
    timestamp: datetime  # UTC, candle open time
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None  # Not all providers supply this
    trades_count: int | None
    is_complete: bool  # False for current/incomplete candle
```

**Constraints**:
- `high >= open, close, low`
- `low <= open, close, high`
- `open, high, low, close > 0`
- `volume >= 0`
- Timestamps must be in UTC

### Timeframe

```python
class Timeframe(Enum):
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
```

**Aggregation Rules**:
```
Valid: 1m → 3m, 1m → 5m, 1m → 15m, etc.
Valid: 5m → 15m, 5m → 30m, 5m → 1h, etc.
Invalid: 3m → 5m (not a divisor)
Invalid: 1h → 45m (target must be larger)
```

### AssetType

```python
class AssetType(Enum):
    CRYPTO = "crypto"
    STOCK = "stock"
    FOREX = "forex"
    INDEX = "index"
    COMMODITY = "commodity"
    ETF = "etf"
```

### AssetMetadata

```python
@dataclass
class AssetMetadata:
    symbol: str
    asset_type: AssetType
    exchange: str
    timezone: str  # e.g., "America/New_York"
    base_currency: str  # e.g., "USD" for BTC/USD
    quote_currency: str  # e.g., "BTC" for BTC/USD
    tick_size: Decimal  # Minimum price increment
    lot_size: Decimal | None  # Minimum order size
    trading_hours: TradingHours | None
    fee_model: FeeModel
    liquidity_info: LiquidityInfo | None
    data_adapter: str  # Which adapter handles this
    metadata_version: str
    updated_at: datetime
```

### TradingHours

```python
@dataclass
class TradingHours:
    timezone: str
    sessions: list[TradingSession]
    holidays: list[date]
    early_closes: dict[date, time]


@dataclass
class TradingSession:
    day: int  # 0=Monday, 6=Sunday
    open_time: time
    close_time: time
```

### FeeModel

```python
class FeeType(Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"
    TIERED = "tiered"


@dataclass
class FeeModel:
    fee_type: FeeType
    maker_fee: Decimal | None
    taker_fee: Decimal
    minimum_fee: Decimal | None
    tier_thresholds: list[TierThreshold] | None


@dataclass
class TierThreshold:
    volume_threshold: Decimal
    fee_rate: Decimal
```

### LiquidityInfo

```python
@dataclass
class LiquidityInfo:
    average_daily_volume: Decimal
    average_spread: Decimal  # In quote currency
    average_slippage_100u: Decimal  # Slippage for 100 unit order
    market_depth: Decimal | None  # Total depth in quote currency
    last_updated: datetime
```

### CandleSet

Collection of candles for a specific symbol and timeframe.

```python
@dataclass
class CandleSet:
    symbol: str
    timeframe: Timeframe
    candles: list[Candle]
    source: str  # Adapter name
    fetched_at: datetime
    data_version: str

    @property
    def start(self) -> datetime: ...

    @property
    def end(self) -> datetime: ...

    @property
    def count(self) -> int: ...

    def is_continuous(self) -> bool: ...

    def gaps(self) -> list[tuple[datetime, datetime]]: ...
```

## Feature Models

### FeatureGroup

```python
class FeatureGroup(Enum):
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLUME = "volume"
    VOLATILITY = "volatility"
    PRICE_STRUCTURE = "price_structure"
```

### FeatureSet

Features computed for a single candle.

```python
@dataclass
class FeatureSet:
    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    features: dict[str, float]  # Feature name → value
    feature_version: str
    computed_at: datetime

    def get(self, feature_name: str) -> float | None: ...

    def get_group(self, group: FeatureGroup) -> dict[str, float]: ...
```

### FeatureDefinition

Metadata about a feature.

```python
@dataclass
class FeatureDefinition:
    name: str
    group: FeatureGroup
    description: str
    parameters: dict[str, Any]
    enabled: bool
    min_candles_required: int
    version: str
```

## Market Regime Models

### MarketRegime

```python
class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BREAKOUT = "breakout"
    UNCERTAIN = "uncertain"
```

### RegimeResult

```python
@dataclass
class RegimeResult:
    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    regime: MarketRegime
    confidence: float  # 0.0 to 1.0
    indicators: dict[str, float]  # What contributed
    computed_at: datetime
```

## Signal Models

### SignalType

```python
class SignalType(Enum):
    UP = "up"
    DOWN = "down"
    NEUTRAL = "neutral"
    NO_SIGNAL = "no_signal"
```

### SignalScore

```python
@dataclass
class SignalScore:
    raw_score: float  # e.g., -1.0 to 1.0
    calibrated_confidence: float | None  # 0.0 to 1.0 if calibrated
    calibration_method: str | None
    calibration_version: str | None
```

### TimeframeSignal

Signal from a single timeframe analysis.

```python
@dataclass
class TimeframeSignal:
    timestamp: datetime
    symbol: str
    timeframe: Timeframe
    signal: SignalType
    score: SignalScore
    features_used: dict[str, float]
    regime: RegimeResult
    reason_codes: list[str]
```

### CompositeSignal

Final signal combining multiple timeframes.

```python
@dataclass
class CompositeSignal:
    timestamp: datetime
    symbol: str
    asset_type: AssetType
    exchange: str
    price: Decimal
    signal: SignalType
    score: SignalScore
    timeframe_signals: dict[Timeframe, TimeframeSignal]
    htf_context: dict[Timeframe, TimeframeSignal]  # Higher TF signals
    ltf_timing: dict[Timeframe, TimeframeSignal]  # Lower TF signals
    regime: MarketRegime
    reason_codes: list[str]
    contributing_factors: dict[str, Any]
    model_version: str
    data_version: str
```

### SignalAudit

Full audit record for a signal.

```python
@dataclass
class SignalAudit:
    id: str  # UUID
    timestamp: datetime
    symbol: str
    asset_type: AssetType
    exchange: str
    timeframe: Timeframe
    price: Decimal
    signal: SignalType
    raw_score: float
    calibrated_confidence: float | None
    features: dict[str, float]
    market_regime: MarketRegime
    regime_confidence: float
    timeframe_signals: dict[str, str]  # timeframe → signal type
    reason_codes: list[str]
    contributing_factors: dict[str, Any]
    model_version: str
    data_version: str
    created_at: datetime
```

## Backtest Models

### BacktestRun

```python
@dataclass
class BacktestRun:
    id: str  # UUID
    name: str
    strategy_config: dict
    start_date: datetime
    end_date: datetime
    symbol: str
    timeframe: Timeframe
    initial_capital: Decimal
    created_at: datetime
    status: str  # running, completed, failed
    error: str | None
```

### BacktestTrade

```python
@dataclass
class BacktestTrade:
    id: str
    backtest_run_id: str
    entry_timestamp: datetime
    entry_price: Decimal
    entry_signal: SignalType
    exit_timestamp: datetime | None
    exit_price: Decimal | None
    exit_signal: SignalType | None
    side: str  # "long" or "short"
    size: Decimal
    fee_entry: Decimal
    fee_exit: Decimal | None
    slippage_entry: Decimal
    slippage_exit: Decimal | None
    pnl: Decimal | None
    pnl_percent: Decimal | None
    holding_periods: int  # Number of candles held
    regime_at_entry: MarketRegime
    regime_at_exit: MarketRegime | None
```

### BacktestMetrics

```python
@dataclass
class BacktestMetrics:
    backtest_run_id: str

    # Basic metrics
    total_trades: int
    winning_trades: int
    losing_trades: int

    # Accuracy metrics
    accuracy: float
    precision: float
    recall: float
    f1_score: float

    # Financial metrics
    total_return: Decimal
    total_return_percent: float
    expected_return: float
    profit_factor: float

    # Risk metrics
    maximum_drawdown: Decimal
    maximum_drawdown_percent: float
    sharpe_ratio: float | None

    # Trade statistics
    average_win: Decimal
    average_loss: Decimal
    average_trade_pnl: Decimal
    average_holding_period: float
    longest_losing_streak: int
    trade_frequency: float  # Trades per time period

    # Segment analysis
    performance_by_timeframe: dict[str, float]
    performance_by_asset: dict[str, float]
    performance_by_regime: dict[str, float]

    # Cost analysis
    total_fees: Decimal
    total_slippage: Decimal
```

### WalkForwardWindow

```python
@dataclass
class WalkForwardWindow:
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    metrics: BacktestMetrics
    trades: list[BacktestTrade]
    calibration_version: str | None
```

### WalkForwardResult

```python
@dataclass
class WalkForwardResult:
    id: str
    backtest_run_id: str
    windows: list[WalkForwardWindow]
    aggregate_metrics: BacktestMetrics
    overfitting_score: float | None  # Comparison train vs test
    created_at: datetime
```

## Storage Models

### ModelVersion

```python
@dataclass
class ModelVersion:
    version: str
    name: str
    description: str
    config: dict
    created_at: datetime
    is_active: bool
    parent_version: str | None
```

### DataVersion

```python
@dataclass
class DataVersion:
    version: str
    adapter: str
    symbol: str
    start_date: datetime
    end_date: datetime
    candle_count: int
    created_at: datetime
    checksum: str  # For data integrity
```

## Database Schema

### candles

```sql
CREATE TABLE candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    quote_volume REAL,
    trades_count INTEGER,
    is_complete BOOLEAN NOT NULL DEFAULT TRUE,
    source TEXT NOT NULL,
    data_version TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, timeframe, timestamp)
);

CREATE INDEX idx_candles_symbol_timeframe ON candles(symbol, timeframe);
CREATE INDEX idx_candles_timestamp ON candles(timestamp);
```

### features

```sql
CREATE TABLE features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    features JSON NOT NULL,
    feature_version TEXT NOT NULL,
    computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(symbol, timeframe, timestamp, feature_version)
);

CREATE INDEX idx_features_symbol_timeframe ON features(symbol, timeframe);
```

### signals

```sql
CREATE TABLE signals (
    id TEXT PRIMARY KEY,             -- UUID
    timestamp DATETIME NOT NULL,
    symbol TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    exchange TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    price REAL NOT NULL,
    signal TEXT NOT NULL,
    raw_score REAL NOT NULL,
    calibrated_confidence REAL,
    features JSON NOT NULL,
    market_regime TEXT NOT NULL,
    regime_confidence REAL NOT NULL,
    timeframe_signals JSON NOT NULL,
    reason_codes JSON NOT NULL,
    contributing_factors JSON,
    model_version TEXT NOT NULL,
    data_version TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_signals_symbol ON signals(symbol);
CREATE INDEX idx_signals_timestamp ON signals(timestamp);
CREATE INDEX idx_signals_signal ON signals(signal);
```

### backtest_runs

```sql
CREATE TABLE backtest_runs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    strategy_config JSON NOT NULL,
    start_date DATETIME NOT NULL,
    end_date DATETIME NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    initial_capital REAL NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT
);
```

### backtest_trades

```sql
CREATE TABLE backtest_trades (
    id TEXT PRIMARY KEY,
    backtest_run_id TEXT NOT NULL,
    entry_timestamp DATETIME NOT NULL,
    entry_price REAL NOT NULL,
    entry_signal TEXT NOT NULL,
    exit_timestamp DATETIME,
    exit_price REAL,
    exit_signal TEXT,
    side TEXT NOT NULL,
    size REAL NOT NULL,
    fee_entry REAL NOT NULL,
    fee_exit REAL,
    slippage_entry REAL NOT NULL,
    slippage_exit REAL,
    pnl REAL,
    pnl_percent REAL,
    holding_periods INTEGER,
    regime_at_entry TEXT NOT NULL,
    regime_at_exit TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(id)
);
```

### backtest_metrics

```sql
CREATE TABLE backtest_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backtest_run_id TEXT NOT NULL,
    metrics JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(id)
);
```

### model_versions

```sql
CREATE TABLE model_versions (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    config JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    parent_version TEXT
);
```

### asset_metadata

```sql
CREATE TABLE asset_metadata (
    symbol TEXT PRIMARY KEY,
    asset_type TEXT NOT NULL,
    exchange TEXT NOT NULL,
    timezone TEXT NOT NULL,
    base_currency TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    tick_size REAL NOT NULL,
    lot_size REAL,
    trading_hours JSON,
    fee_model JSON NOT NULL,
    liquidity_info JSON,
    data_adapter TEXT NOT NULL,
    metadata_version TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### watchlists

```sql
CREATE TABLE watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    symbols JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## Data Relationships

```
AssetMetadata (1) ──── (*) Candle
AssetMetadata (1) ──── (*) Signal
AssetMetadata (1) ──── (*) FeatureSet

Candle (1) ──── (*) FeatureSet
Candle (1) ──── (*) RegimeResult

TimeframeSignal (*) ──── (1) CompositeSignal
CompositeSignal (1) ──── (1) SignalAudit

BacktestRun (1) ──── (*) BacktestTrade
BacktestRun (1) ──── (*) BacktestMetrics
BacktestRun (1) ──── (*) WalkForwardWindow

WalkForwardWindow (1) ──── (*) BacktestTrade
WalkForwardWindow (1) ──── (1) BacktestMetrics
```

## Versioning

### Data Version

Format: `{adapter}_{YYYYMMDD}_{candle_count}`

Example: `binance_20260101_1500000`

### Feature Version

Format: `{major}.{minor}.{patch}`

Bumped when:
- Major: Feature definition changes (breaks compatibility)
- Minor: New features added
- Patch: Bug fixes in computation

### Model Version

Format: `{major}.{minor}.{patch}`

Bumped when:
- Major: Strategy logic changes
- Minor: Parameter tuning
- Patch: Bug fixes
