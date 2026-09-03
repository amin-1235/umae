# Universal Market Analysis Engine (UMAE) - Requirements

## Functional Requirements

### FR-1: Data Ingestion

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | System SHALL accept candle data from pluggable data adapters | P0 |
| FR-1.2 | System SHALL normalize all incoming data to common Candle format | P0 |
| FR-1.3 | System SHALL support at minimum: Binance, Yahoo Finance adapters | P0 |
| FR-1.4 | System SHALL handle rate limiting per adapter | P0 |
| FR-1.5 | System SHALL validate incoming data before storage | P0 |
| FR-1.6 | System SHALL store raw candles in persistent storage | P0 |
| FR-1.7 | System SHALL support async data fetching | P1 |

### FR-2: Asset Metadata

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | System SHALL accept asset metadata: symbol, asset_type, exchange, timezone | P0 |
| FR-2.2 | System SHALL accept trading_hours, tick_size, fee_model per asset | P0 |
| FR-2.3 | System SHALL accept liquidity information per asset | P1 |
| FR-2.4 | System SHALL use metadata in backtesting cost calculations | P0 |

### FR-3: Candle Aggregation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | System SHALL aggregate candles from base timeframe to target timeframe | P0 |
| FR-3.2 | System SHALL only aggregate when source is divisor of target | P0 |
| FR-3.3 | System SHALL handle OHLCV aggregation correctly | P0 |
| FR-3.4 | System SHALL align timestamps to target candle boundaries | P0 |
| FR-3.5 | System SHALL exclude incomplete candles from aggregation | P0 |
| FR-3.6 | System SHALL handle missing candles gracefully | P0 |
| FR-3.7 | System SHALL support all timeframes: 1m,3m,5m,15m,20m,30m,1h,2h,4h,6h,12h,1D,1W | P0 |

### FR-4: Data Validation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-4.1 | System SHALL detect duplicate candles | P0 |
| FR-4.2 | System SHALL detect missing candles | P0 |
| FR-4.3 | System SHALL validate OHLC consistency (high >= open,close,low) | P0 |
| FR-4.4 | System SHALL validate timestamp ordering | P0 |
| FR-4.5 | System SHALL detect stale data | P0 |
| FR-4.6 | System SHALL detect impossible volume (negative, zero when shouldn't be) | P0 |
| FR-4.7 | System SHALL flag incomplete current candle | P0 |
| FR-4.8 | System SHALL NOT generate signals from invalid data | P0 |

### FR-5: Feature Computation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-5.1 | System SHALL compute trend features (EMA, SMA, MA slope, market structure) | P0 |
| FR-5.2 | System SHALL compute momentum features (RSI, MACD, ROC) | P0 |
| FR-5.3 | System SHALL compute volume features (relative volume, expansion) | P0 |
| FR-5.4 | System SHALL compute volatility features (ATR, expansion/contraction) | P0 |
| FR-5.5 | System SHALL compute price structure features (breakout, S/R, rejection) | P0 |
| FR-5.6 | System SHALL allow enabling/disabling feature groups via config | P0 |
| FR-5.7 | System SHALL compute features incrementally | P1 |
| FR-5.8 | System SHALL ensure no future data leakage in feature computation | P0 |
| FR-5.9 | System SHALL version feature definitions for reproducibility | P1 |

### FR-6: Market Regime Detection

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-6.1 | System SHALL classify market regime per timeframe | P0 |
| FR-6.2 | System SHALL support regimes: trending_up, trending_down, ranging, high_volatility, low_volatility, breakout, uncertain | P0 |
| FR-6.3 | System SHALL use regime in signal confidence calculation | P0 |
| FR-6.4 | System SHALL allow regime detection to be configured | P1 |

### FR-7: Multi-Timeframe Analysis

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-7.1 | System SHALL analyze signals across multiple timeframes | P0 |
| FR-7.2 | System SHALL treat HTF as context, LTF as timing | P0 |
| FR-7.3 | System SHALL handle missing timeframes gracefully | P0 |
| FR-7.4 | System SHALL allow timeframe weights to be configured | P0 |
| FR-7.5 | System SHALL require minimum confluence for signal | P0 |

### FR-8: Signal Generation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-8.1 | System SHALL produce signals: UP, DOWN, NEUTRAL, NO_SIGNAL | P0 |
| FR-8.2 | NO_SIGNAL SHALL be a valid output when evidence insufficient | P0 |
| FR-8.3 | System SHALL produce raw signal score (not probability) | P0 |
| FR-8.4 | System SHALL separate raw score from calibrated confidence | P0 |
| FR-8.5 | System SHALL NOT use terms "probability" or "accuracy" for raw score | P0 |

### FR-9: Confidence Calibration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-9.1 | System SHALL calibrate raw scores to confidence values | P1 |
| FR-9.2 | System SHALL use isotonic regression or Platt scaling | P1 |
| FR-9.3 | System SHALL calibrate per-asset and per-regime | P1 |
| FR-9.4 | System SHALL NOT claim accuracy without validation | P0 |

### FR-10: Signal Audit

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-10.1 | System SHALL log every signal with full context | P0 |
| FR-10.2 | Audit record SHALL include: timestamp, asset, exchange, timeframe, price | P0 |
| FR-10.3 | Audit record SHALL include: features, market_regime, signal, score | P0 |
| FR-10.4 | Audit record SHALL include: model_version, data_version | P0 |
| FR-10.5 | Audit record SHALL include: reason codes | P0 |
| FR-10.6 | System SHALL explain why signal appeared (or didn't) | P0 |

### FR-11: Backtesting

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-11.1 | System SHALL simulate trades with configurable fees | P0 |
| FR-11.2 | System SHALL simulate spread | P0 |
| FR-11.3 | System SHALL simulate slippage | P0 |
| FR-11.4 | System SHALL respect trading hours | P0 |
| FR-11.5 | System SHALL compute: accuracy, precision, recall, F1 | P0 |
| FR-11.6 | System SHALL compute: expected return, profit factor | P0 |
| FR-11.7 | System SHALL compute: max drawdown, avg win/loss | P0 |
| FR-11.8 | System SHALL compute: longest losing streak, trade frequency | P0 |
| FR-11.9 | System SHALL compute: performance per timeframe, asset, regime | P0 |
| FR-11.10 | Results SHALL be reproducible | P0 |

### FR-12: Walk-Forward Validation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-12.1 | System SHALL implement time-series walk-forward evaluation | P0 |
| FR-12.2 | Train/Test split SHALL be by time only (no random shuffle) | P0 |
| FR-12.3 | Each window SHALL be saved independently | P0 |
| FR-12.4 | Aggregate metrics across windows SHALL be computed | P0 |
| FR-12.5 | Results SHALL be reproducible | P0 |

### FR-13: Baseline

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-13.1 | System SHALL implement deterministic/statistical baseline | P0 |
| FR-13.2 | Baseline SHALL be simple, interpretable | P0 |
| FR-13.3 | All ML models SHALL be compared against baseline | P0 |
| FR-13.4 | ML SHALL only be used if out-of-sample improvement shown | P0 |

### FR-14: Configuration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-14.1 | System SHALL use YAML configuration files | P0 |
| FR-14.2 | Environment variables SHALL override config file | P0 |
| FR-14.3 | Secrets SHALL NOT be in config files | P0 |
| FR-14.4 | Config SHALL be validated on startup | P0 |
| FR-14.5 | Config changes SHALL be logged | P0 |

### FR-15: Storage

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-15.1 | System SHALL use database abstraction (repository pattern) | P0 |
| FR-15.2 | System SHALL store: candles, features, signals, backtest runs | P0 |
| FR-15.3 | System SHALL store: model versions, audit records | P0 |
| FR-15.4 | Default storage SHALL be SQLite | P0 |
| FR-15.5 | System SHALL support migration from SQLite to PostgreSQL | P2 |

### FR-16: Reliability

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-16.1 | System SHALL use structured logging | P0 |
| FR-16.2 | System SHALL implement retry with exponential backoff | P0 |
| FR-16.3 | System SHALL handle rate limits per provider | P0 |
| FR-16.4 | System SHALL handle graceful shutdown | P0 |
| FR-16.5 | System SHALL isolate component failures | P0 |
| FR-16.6 | System SHALL provide health check capability | P1 |

### FR-17: Telegram Interface

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-17.1 | Telegram interface SHALL be decoupled from engine | P0 |
| FR-17.2 | Engine SHALL run without Telegram | P0 |
| FR-17.3 | Telegram SHALL support: /start, /help, /analyze, /status | P1 |
| FR-17.4 | Telegram SHALL support: /watchlist, /add, /remove | P2 |
| FR-17.5 | Telegram SHALL receive typed AnalysisResult objects | P0 |
| FR-17.6 | Telegram SHALL NEVER import analysis logic directly | P0 |
| FR-17.7 | Telegram SHALL NEVER compute features or signals | P0 |
| FR-17.8 | Telegram SHALL format results only | P0 |
| FR-17.9 | Bot token SHALL come from environment variable only | P0 |
| FR-17.10 | Bot token SHALL never be logged | P0 |
| FR-17.11 | Telegram SHALL implement rate limiting per user | P0 |
| FR-17.12 | Telegram SHALL handle API errors gracefully | P0 |
| FR-17.13 | Telegram SHALL handle duplicate updates | P0 |
| FR-17.14 | Telegram SHALL reconnect on disconnection | P0 |
| FR-17.15 | Telegram V1 SHALL NOT have /buy, /sell, /order commands | P0 |
| FR-17.16 | Telegram SHALL validate all user input | P0 |
| FR-17.17 | Telegram SHALL store minimum user data (user_id, watchlist) | P0 |
| FR-17.18 | Telegram SHALL be implemented LAST (Phase 7) | P0 |

### FR-18: Telegram Response Contract

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-18.1 | System SHALL define typed AnalysisResult for Telegram | P0 |
| FR-18.2 | System SHALL define typed SystemStatus for /status | P0 |
| FR-18.3 | System SHALL define typed WatchlistResult for /watchlist | P0 |
| FR-18.4 | Telegram formatter SHALL only use typed response objects | P0 |
| FR-18.5 | Telegram formatter SHALL NOT access internal engine state | P0 |
| FR-18.6 | AnalysisResult SHALL include: symbol, price, timestamp, data_quality | P0 |
| FR-18.7 | AnalysisResult SHALL include: timeframe_results, regime, signal | P0 |
| FR-18.8 | AnalysisResult SHALL include: score, confidence, reason_codes | P0 |
| FR-18.9 | AnalysisResult SHALL include: warnings, model_version, data_version | P0 |
| FR-18.10 | Messages exceeding 4096 chars SHALL be split | P0 |

### FR-18: Live Execution

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-18.1 | System SHALL NOT implement live order execution in v1 | P0 |
| FR-18.2 | System MAY provide abstract broker/exchange interface for future | P2 |
| FR-18.3 | Default execution mode SHALL be paper trading | P0 |

## Non-Functional Requirements

### NFR-1: Code Quality

| ID | Requirement |
|----|-------------|
| NFR-1.1 | All code SHALL have type hints |
| NFR-1.2 | Code SHALL pass mypy strict mode |
| NFR-1.3 | Code SHALL pass ruff linting |
| NFR-1.4 | Code SHALL be formatted with ruff format |
| NFR-1.5 | Public APIs SHALL have docstrings |

### NFR-2: Testing

| ID | Requirement |
|----|-------------|
| NFR-2.1 | System SHALL have unit tests for all modules |
| NFR-2.2 | System SHALL have integration tests for data flow |
| NFR-2.3 | System SHALL have data validation tests |
| NFR-2.4 | System SHALL have timeframe aggregation tests |
| NFR-2.5 | System SHALL have indicator computation tests |
| NFR-2.6 | System SHALL have backtest tests |
| NFR-2.7 | System SHALL have data leakage tests |
| NFR-2.8 | Tests SHALL use deterministic fixtures |
| NFR-2.9 | Test coverage SHALL be > 80% for core modules |

### NFR-3: Performance

| ID | Requirement |
|----|-------------|
| NFR-3.1 | Feature computation for 1000 candles SHALL complete in < 1s |
| NFR-3.2 | Signal generation SHALL complete in < 500ms |
| NFR-3.3 | Backtest for 1 year daily data SHALL complete in < 30s |

### NFR-4: Maintainability

| ID | Requirement |
|----|-------------|
| NFR-4.1 | All modules SHALL have clear interfaces |
| NFR-4.2 | Dependencies SHALL be injected, not imported directly |
| NFR-4.3 | Business logic SHALL NOT depend on storage implementation |
| NFR-4.4 | Configuration SHALL be external to code |

## Quality Gates

Before any model/strategy is considered valid:

1. No data leakage detected
2. Out-of-sample test available
3. Walk-forward test available
4. Transaction costs included
5. Results reproducible
6. Baseline comparison available

## Prohibited Terms

The following terms SHALL NOT be used in signal output or user-facing messages:
- "accurate" / "accuracy" (without statistical validation)
- "pasti naik" / "pasti turun"
- "guaranteed"
- "prediction" (use "analysis" or "signal" instead)

## Development Phases

### Phase 1: Foundation
- Project structure
- Core domain models
- Data adapters (Binance, Yahoo)
- Candle engine
- Data validation
- Storage layer

### Phase 2: Analysis
- Feature engine (all groups)
- Market regime detector
- Multi-timeframe analysis
- Signal composer
- Signal audit

### Phase 3: Validation
- Backtesting engine
- Walk-forward validation
- Baseline implementation
- Confidence calibration

### Phase 4: Application Service
- Analysis service (API layer)
- Application orchestration
- Response contracts (AnalysisResult, etc.)

### Phase 5: Paper Trading
- Paper trading engine
- Simulated execution
- Portfolio tracking

### Phase 6: Hardening
- Performance optimization
- Error handling
- Monitoring
- Documentation

### Phase 7: Telegram Interface (LAST)
- Telegram bot setup
- Command handlers (/start, /help, /analyze, /status)
- Response formatting
- Watchlist management
- Rate limiting and security
- Testing

**Note**: Telegram is implemented AFTER core engine is stable. Telegram is a thin interface that formats typed response objects.
