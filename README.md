# UMAE - Universal Market Analysis Engine

A research and analysis engine for multi-asset market analysis.

## Features

- Multi-timeframe analysis (1m to 1W)
- Multi-asset support (crypto, stocks, forex, indices)
- Pluggable data adapters (Binance, Yahoo Finance)
- Market regime detection
- Signal generation with audit trail
- Backtesting with walk-forward validation
- Telegram bot interface

## Installation

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```python
from umae.domain.enums import Timeframe
from umae.data.binance_adapter import BinanceAdapter

adapter = BinanceAdapter()
candles = await adapter.fetch_candles(
    symbol="BTC/USDT",
    timeframe=Timeframe.H1,
    start="2024-01-01",
    end="2024-01-31",
)
```

## Testing

```bash
pytest tests/
```

## License

MIT
