# Universal Market Analysis Engine (UMAE) - Architecture

## Overview

UMAE is a research and analysis engine for multi-asset market analysis. It is NOT a prediction system or live trading platform. It provides deterministic and statistical analysis across multiple timeframes, with auditable signals and reproducible backtesting.

## Core Principles

1. **Analysis first, execution never (in v1)** - No live order execution
2. **Evidence-based signals** - NO_SIGNAL is a valid output
3. **Data leakage prevention** - Future data never touches past features
4. **Baseline before ML** - Deterministic rules first, ML only if validated
5. **Modularity** - All components are replaceable via interfaces

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TELEGRAM INTERFACE                           │
│                    (optional, decoupled)                             │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        ANALYSIS ORCHESTRATOR                        │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Multi-TF     │  │ Signal       │  │ Confidence   │              │
│  │ Aggregator   │──│ Composer     │──│ Calibrator   │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
          │                   │                    │
          ▼                   ▼                    ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   FEATURE    │  │   MARKET     │  │   SIGNAL     │
│   ENGINE     │  │   REGIME     │  │   AUDIT      │
│              │  │   DETECTOR   │  │   LOGGER     │
└──────────────┘  └──────────────┘  └──────────────┘
          │                   │                    │
          ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        CANDLE ENGINE                                │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Aggregation  │  │ Validation   │  │ Alignment    │              │
│  │              │  │              │  │              │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
          │                   │                    │
          ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     DATA ADAPTER LAYER                              │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Binance    │  │   Yahoo      │  │   IBKR       │              │
│  │   Adapter    │  │   Adapter    │  │   Adapter    │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
          │                   │                    │
          ▼                   ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        STORAGE LAYER                                │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   SQLite     │  │   Metadata   │  │   Audit      │              │
│  │   (candles)  │  │   Store      │  │   Store      │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

## Module Responsibilities

### 1. Data Adapter Layer

**Purpose**: Normalize data from any provider to a common format.

```python
class DataAdapter(Protocol):
    async def fetch_candles(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Candle]: ...

    async def get_asset_metadata(self, symbol: str) -> AssetMetadata: ...

    async def validate_symbol(self, symbol: str) -> bool: ...
```

**Providers** (initial):
- Binance (crypto)
- Yahoo Finance (stocks, ETFs, indices)
- OANDA (forex) - future

**Rules**:
- Each adapter implements `DataAdapter` protocol
- Adapter configuration via YAML/config files
- API keys via environment variables only
- Rate limiting handled per adapter
- Adapter never exposes raw API errors to engine

### 2. Candle Engine

**Purpose**: Store, validate, aggregate, and serve candles.

**Responsibilities**:
- Store raw candles from providers
- Validate candle integrity (OHLC consistency, missing data)
- Aggregate candles (1m → 3m, 5m, 15m, etc.)
- Handle timezone alignment
- Detect and flag incomplete candles
- Handle missing/stale data

**Timeframes Supported**:
1m, 3m, 5m, 15m, 20m, 30m, 1h, 2h, 4h, 6h, 12h, 1D, 1W

**Aggregation Rules**:
- Source candle must be a divisor of target (e.g., 1m → 3m valid, 1m → 7m invalid)
- Incomplete candles excluded from aggregation
- OHLCV properly aggregated (open from first, close from last, high/low from range)
- Timestamp aligned to target candle boundaries

### 3. Feature Engine

**Purpose**: Compute technical features from candles.

**Feature Groups**:

| Group | Features | Default |
|-------|----------|---------|
| Trend | EMA, SMA, MA slope, market structure (HH/HL/LH/LL) | Enabled |
| Momentum | RSI, MACD, ROC, momentum change | Enabled |
| Volume | Relative volume, volume expansion, volume confirmation | Enabled |
| Volatility | ATR, volatility expansion/contraction, candle range | Enabled |
| Price Structure | Breakout, consolidation, S/R levels, rejection, structure shift | Enabled |

**Rules**:
- Features are configurable (enable/disable per group)
- Features computed incrementally (not recomputed from scratch)
- All features use only data available at timestamp (no future leak)
- Features are versioned for reproducibility
- Feature output is a flat dict per candle

### 4. Market Regime Detector

**Purpose**: Classify market conditions.

**Regimes**:
- `trending_up` - Strong upward trend
- `trending_down` - Strong downward trend
- `ranging` - No clear direction
- `high_volatility` - Volatile, unpredictable
- `low_volatility` - Quiet, compressed
- `breakout` - Breaking from range
- `uncertain` - Cannot classify

**Classification Logic**:
- Based on ADX, ATR percentile, price structure
- Regime is timeframe-specific
- Higher timeframe regime provides context
- Regime affects signal confidence

### 5. Multi-Timeframe Analysis

**Purpose**: Combine signals across timeframes.

**Framework**:
- **Higher Timeframes (HTF)**: 4h, 6h, 12h, 1D, 1W → Context/trend
- **Middle Timeframes (MTF)**: 15m, 20m, 30m, 1h, 2h → Bias
- **Lower Timeframes (LTF)**: 1m, 3m, 5m → Timing/entry

**Rules**:
- Signal requires alignment across multiple timeframes
- HTF context overrides LTF signals when conflicting
- Missing timeframes handled gracefully (not treated as neutral)
- Timeframe weights configurable

### 6. Signal Composer

**Purpose**: Produce final signal from multi-TF analysis.

**Signal Types**:
- `UP` - Bullish evidence sufficient
- `DOWN` - Bearish evidence sufficient
- `NEUTRAL` - Balanced evidence
- `NO_SIGNAL` - Insufficient evidence

**Score**:
- Raw signal score (not probability)
- Separate from calibrated confidence
- Range: configurable (e.g., -1.0 to 1.0)

**Rules**:
- NO_SIGNAL is valid and preferred over weak signals
- Signal requires minimum confluence
- Conflicting timeframes → NO_SIGNAL
- Uncertain regime → reduced confidence

### 7. Confidence Calibrator

**Purpose**: Map raw scores to calibrated probabilities.

**Approach**:
- Use isotonic regression or Platt scaling
- Calibrated on historical data
- Per-asset and per-regime calibration
- Regular recalibration as new data arrives

**Rules**:
- Never claim accuracy without validation
- Calibrated probability ≠ actual probability without validation
- Output includes calibration confidence

### 8. Signal Audit Logger

**Purpose**: Record every signal with full context.

**Recorded Data**:
```python
@dataclass
class SignalAudit:
    timestamp: datetime
    asset: str
    asset_type: str
    exchange: str
    timeframe: str
    price: Decimal
    features: dict
    market_regime: str
    signal: SignalType
    raw_score: float
    calibrated_confidence: float | None
    model_version: str
    data_version: str
    reason_codes: list[str]
    contributing_factors: dict
```

**Reason Codes**:
- `HTF_BEARISH` / `HTF_BULLISH`
- `LTF_BEARISH` / `LTF_BULLISH`
- `VOLUME_WEAK` / `VOLUME_STRONG`
- `REGIME_UNCERTAIN`
- `INSUFFICIENT_CONFLUENCE`
- `CONFLICTING_SIGNALS`
- etc.

### 9. Backtesting Engine

**Purpose**: Validate signals against historical data.

**Components**:
- `Backtester` - Runs simulation
- `MetricsCalculator` - Computes performance metrics
- `WalkForwardValidator` - Time-series cross-validation

**Metrics Required**:
- Accuracy, Precision, Recall, F1
- Expected Return
- Profit Factor
- Maximum Drawdown
- Average Win / Average Loss
- Longest Losing Streak
- Trade Frequency
- Performance per timeframe, asset, regime

**Cost Model**:
- Configurable fee per trade
- Spread simulation
- Slippage estimation
- Latency simulation (optional)

### 10. Walk-Forward Validation

**Purpose**: Prevent overfitting via time-series CV.

**Process**:
```
Window 1: [Train: 2020-01 → 2021-01] [Test: 2021-01 → 2021-06]
Window 2: [Train: 2020-06 → 2021-06] [Test: 2021-06 → 2021-12]
Window 3: [Train: 2021-01 → 2022-01] [Test: 2022-01 → 2022-06]
...
```

**Rules**:
- No random shuffle
- Train/Test split by time only
- Each window saved independently
- Aggregate metrics across windows
- Result must be reproducible

### 11. Paper Trading

**Purpose**: Simulate live trading without real execution.

**Features**:
- Real-time signal generation
- Simulated order execution
- Portfolio tracking
- P&L calculation
- Performance comparison vs backtest

### 12. Storage Layer

**Purpose**: Persistent storage with abstraction.

**Storage Backend**: SQLite (default), PostgreSQL (future)

**Tables**:
- `candles` - OHLCV data
- `features` - Computed features
- `signals` - Signal audit records
- `backtest_runs` - Backtest session metadata
- `backtest_metrics` - Backtest results
- `model_versions` - Model/version tracking
- `asset_metadata` - Asset information
- `watchlists` - User watchlists

**Rules**:
- Storage never coupled to business logic
- All queries go through repository pattern
- Migrations managed via Alembic or similar

### 13. Configuration Management

**Purpose**: Centralized, versioned configuration.

**Config File**: `configs/default.yaml`

**Configurable Items**:
- Data providers and API keys
- Feature groups and parameters
- Timeframe weights
- Signal thresholds
- Backtest parameters
- Storage settings
- Logging settings

**Rules**:
- Environment variables override config file
- Secrets never in config file (use env vars)
- Config validated on startup
- Config changes logged

### 14. Reliability Layer

**Purpose**: Production-grade reliability.

**Features**:
- Structured logging (structlog)
- Retry with exponential backoff
- Rate limiting per provider
- WebSocket reconnect logic
- Graceful shutdown handling
- Health check endpoints
- Error isolation (one component failure doesn't crash others)

## Data Flow

### Analysis Flow

```
1. User requests analysis for symbol
2. Fetch candles from provider (or cache)
3. Validate candle data
4. Aggregate to required timeframes
5. Compute features per timeframe
6. Detect market regime per timeframe
7. Run multi-timeframe analysis
8. Compose signal
9. Calibrate confidence
10. Log audit record
11. Return signal to interface
```

### Backtest Flow

```
1. Load historical candles
2. Split into walk-forward windows
3. For each window:
   a. Train calibrator on train period
   b. Generate signals on test period
   c. Simulate execution with costs
   d. Calculate metrics
4. Aggregate window metrics
5. Generate report
6. Compare with baseline
```

## Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.14 | Rich ecosystem, typing, async |
| Data Processing | pandas, numpy | Industry standard for time series |
| Technical Indicators | pandas-ta, ta-lib (optional) | Proven libraries |
| Database | SQLite (default) | Zero config, portable |
| ORM/Query | SQLAlchemy | Database abstraction |
| Migrations | Alembic | Schema versioning |
| Testing | pytest | Modern, flexible |
| Type Checking | mypy | Static analysis |
| Linting | ruff | Fast, comprehensive |
| Formatting | ruff format | Consistent style |
| Config | pydantic-settings | Validated config |
| Logging | structlog | Structured logs |
| Async | asyncio, aiohttp | Non-blocking I/O |
| Telegram Bot | python-telegram-bot | Telegram Bot API wrapper |

## Security

- API keys via environment variables only
- No secrets in code or config files
- Input validation on all external data
- Rate limiting on all API calls
- No eval/exec on untrusted input

## Telegram Interface (Phase 7 - LAST)

**Telegram is a thin interface layer. Analysis logic lives in the core engine.**

### Architecture

```
Telegram Handler
    ↓
Bot Service (Telegram-specific)
    ↓
Application/Analysis Service (interface layer)
    ↓
UMAE Core Engine
```

### Key Principles

1. **Telegram NEVER imports analysis logic directly**
2. **Telegram NEVER computes features or signals**
3. **Telegram receives typed `AnalysisResult` objects**
4. **Telegram ONLY formats results for display**
5. **All responses typed (AnalysisResult, SystemStatus, etc.)**

### Implementation Order

```
Phase 1: Core domain, data model, adapters
Phase 2: Candle engine, feature engine
Phase 3: Regime engine, baseline analysis
Phase 4: Backtesting, validation
Phase 5: Paper analysis
Phase 6: Application service/API ← Telegram depends on this
Phase 7: Telegram adapter ← LAST
```

### Bot Commands (V1)

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Help text |
| `/analyze <symbol>` | Full analysis |
| `/status` | System health |
| `/watchlist` | List watchlist |
| `/add <symbol>` | Add to watchlist |
| `/remove <symbol>` | Remove from watchlist |

### Response Contract

```python
@dataclass
class AnalysisResult:
    symbol: str
    asset_type: str
    exchange: str
    timestamp: str
    price: Decimal
    data_quality: DataQuality
    timeframe_results: list[TimeframeResult]
    regime: str
    regime_confidence: float
    signal: str
    signal_score: float
    calibrated_confidence: float | None
    feature_summary: FeatureSummary
    reason_codes: list[str]
    warnings: list[str]
    model_version: str
    data_version: str
```

### Security

- `TELEGRAM_BOT_TOKEN` from environment variable only
- Never log bot token
- Rate limit user commands
- Validate all input
- Handle Telegram API errors
- Graceful reconnect

### Prohibited (V1)

- No `/buy`, `/sell`, `/order` commands
- No live execution
- No trading interface

### File Structure

```
src/umae/telegram/
├── __init__.py
├── bot.py              # Bot setup and main loop
├── handlers.py         # Command handlers
├── formatters.py       # Response formatting
├── models.py           # Telegram-specific models
├── services.py         # Bot services (watchlist, etc.)
├── security.py         # Rate limiting, validation
└── config.py           # Telegram configuration
```

## Future Considerations (NOT in v1)

- Live order execution (interface only)
- WebSocket real-time data
- ML model training pipeline
- Dashboard UI
- Multi-user support
- Plugin system
