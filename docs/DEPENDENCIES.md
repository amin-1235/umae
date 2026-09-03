# Universal Market Analysis Engine (UMAE) - Dependencies

## Overview

This document lists all dependencies, their purpose, and data provider options.

## Python Dependencies

### Core

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| Python | >= 3.11 | Runtime | Yes |
| pydantic | >= 2.0 | Data validation, settings | Yes |
| pydantic-settings | >= 2.0 | Configuration management | Yes |
| pyyaml | >= 6.0 | YAML config files | Yes |

### Data Processing

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| pandas | >= 2.0 | DataFrame operations | Yes |
| numpy | >= 1.24 | Numerical operations | Yes |

### Technical Indicators

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| pandas-ta | >= 0.3.14 | Technical indicators | Yes |
| ta-lib | >= 0.4.28 | Alternative indicators (optional) | No |

**Note**: pandas-ta is sufficient for initial implementation. TA-Lib can be added later for performance if needed.

### Database

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| sqlalchemy | >= 2.0 | Database ORM/abstraction | Yes |
| aiosqlite | >= 0.19 | Async SQLite support | Yes |
| alembic | >= 1.12 | Database migrations | Yes |

### HTTP/API

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| aiohttp | >= 3.9 | Async HTTP client | Yes |
| tenacity | >= 8.2 | Retry logic | Yes |

### Logging/Monitoring

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| structlog | >= 23.2 | Structured logging | Yes |
| rich | >= 13.7 | Console output (dev) | Yes |

### Testing

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| pytest | >= 8.0 | Test framework | Yes |
| pytest-asyncio | >= 0.23 | Async test support | Yes |
| pytest-cov | >= 4.1 | Coverage reporting | Yes |
| hypothesis | >= 6.92 | Property-based testing | Yes |

### Code Quality

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| ruff | >= 0.3 | Linting and formatting | Yes |
| mypy | >= 1.8 | Static type checking | Yes |

### Optional (Future)

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| scikit-learn | >= 1.4 | ML models, calibration | No |
| scipy | >= 1.12 | Statistical functions | No |
| telegram-bot | >= 20.7 | Telegram interface | No |

## Dependency Installation

### requirements.txt (Core)

```
pydantic>=2.0
pydantic-settings>=2.0
pyyaml>=6.0
pandas>=2.0
numpy>=1.24
pandas-ta>=0.3.14
sqlalchemy>=2.0
aiosqlite>=0.19
alembic>=1.12
aiohttp>=3.9
tenacity>=8.2
structlog>=23.2
rich>=13.7
```

### requirements-dev.txt (Development)

```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.1
hypothesis>=6.92
ruff>=0.3
mypy>=1.8
```

### requirements-ml.txt (Optional ML)

```
-r requirements.txt
scikit-learn>=1.4
scipy>=1.12
```

## Data Providers

### Crypto

#### Binance (Primary)

- **Type**: REST API
- **Data**: OHLCV, ticker, trades
- **Rate Limit**: 1200 requests/minute (weight-based)
- **Auth**: API key + secret (for some endpoints)
- **Free**: Yes
- **Documentation**: https://binance-docs.github.io/apidocs/

**Adapter Implementation**:
- Fetch historical candles (klines)
- Support all timeframes
- Handle pagination
- Cache locally

#### Coinbase (Secondary)

- **Type**: REST API
- **Data**: OHLCV, ticker
- **Rate Limit**: 10 requests/second
- **Auth**: API key
- **Free**: Yes
- **Documentation**: https://docs.cloud.coinbase.com/

**Use Case**: Fallback if Binance unavailable

### Stocks/ETFs

#### Yahoo Finance (Primary)

- **Type**: REST API (unofficial)
- **Data**: OHLCV, fundamentals
- **Rate Limit**: 2000 requests/hour
- **Auth**: None
- **Free**: Yes
- **Documentation**: https://github.com/ranaroussi/yfinance

**Adapter Implementation**:
- Fetch historical data
- Support daily and intraday
- Handle symbol validation
- Note: Unofficial, may break

#### Alpha Vantage (Secondary)

- **Type**: REST API
- **Data**: OHLCV, fundamentals, technicals
- **Rate Limit**: 5 requests/minute (free tier)
- **Auth**: API key (free)
- **Free**: Yes (limited)
- **Documentation**: https://www.alphavantage.co/documentation/

**Use Case**: More reliable than Yahoo, but rate limited

### Forex

#### OANDA (Future)

- **Type**: REST API + Streaming
- **Data**: OHLCV, ticks, order book
- **Rate Limit**: 120 requests/minute
- **Auth**: API token
- **Free**: Practice account available
- **Documentation**: https://developer.oanda.com/

**Use Case**: Primary forex provider when implemented

### Indices

#### Yahoo Finance

- Same as stocks
- Index symbols: ^GSPC (S&P 500), ^DJI (Dow), ^IXIC (Nasdaq)

#### Investing.com (Future)

- **Type**: Web scraping (not recommended for production)
- **Use Case**: Additional index data

## Provider Selection Matrix

| Asset Type | Primary | Secondary | Fallback |
|-----------|---------|-----------|----------|
| Crypto | Binance | Coinbase | Yahoo |
| US Stocks | Yahoo Finance | Alpha Vantage | - |
| Forex | OANDA | Yahoo | - |
| Indices | Yahoo Finance | - | - |
| ETFs | Yahoo Finance | Alpha Vantage | - |

## API Key Management

### Storage

- Environment variables only
- Never in config files
- Never in code
- Never in git

### Environment Variables

```bash
# Binance
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here

# Alpha Vantage
ALPHA_VANTAGE_API_KEY=your_key_here

# OANDA
OANDA_API_TOKEN=your_token_here
OANDA_ACCOUNT_ID=your_account_id
```

### Loading

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    binance_api_key: str | None = None
    binance_api_secret: str | None = None
    alpha_vantage_api_key: str | None = None
    oanda_api_token: str | None = None
    oanda_account_id: str | None = None

    class Config:
        env_file = ".env"
```

## System Dependencies

| Dependency | Version | Purpose | Required |
|------------|---------|---------|----------|
| SQLite | >= 3.35 | Local database | Yes |
| PostgreSQL | >= 14 | Production database (optional) | No |
| Redis | >= 7.0 | Caching (optional) | No |

## Development Tools

| Tool | Purpose | Required |
|------|---------|----------|
| Git | Version control | Yes |
| Make | Task runner | Optional |
| Docker | Containerization (optional) | No |

## Version Constraints

### Minimum Python Version

Python 3.11+ required for:
- `match` statements
- Improved type hints
- Performance improvements

### Why Not Older Python?

- Type hint syntax
- Async improvements
- Security patches
- Library compatibility

### Why Not Newer Python?

- Stability
- Library support
- Deployment compatibility

## Dependency Security

### Audit

```bash
# Check for vulnerabilities
pip-audit

# Or
safety check
```

### Lock Dependencies

```bash
# Generate lock file
pip-compile requirements.in

# Install from lock
pip install -r requirements.txt
```

### Regular Updates

- Monthly security updates
- Quarterly minor updates
- Annual major updates (with testing)

## Future Dependencies

### ML Stack (Optional)

```
scikit-learn>=1.4    # ML models
scipy>=1.12          # Statistics
xgboost>=2.0         # Gradient boosting (optional)
lightgbm>=4.2        # LightGBM (optional)
```

### Real-time Data

```
websocket-client>=1.7    # WebSocket client
websockets>=12.0         # Async WebSocket
```

### Telegram Interface

```
python-telegram-bot>=20.7  # Telegram Bot API
```

## Dependency Management Workflow

1. Add dependency to `requirements.in`
2. Run `pip-compile requirements.in`
3. Test thoroughly
4. Commit `requirements.txt`
5. Update documentation if needed

## Notes

- **No TA-Lib initially**: pandas-ta is sufficient and easier to install
- **No ML initially**: Baseline deterministic rules first
- **No Telegram initially**: Engine is standalone
- **SQLite first**: PostgreSQL migration later if needed
