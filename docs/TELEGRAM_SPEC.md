# Universal Market Analysis Engine (UMAE) - Telegram Bot Specification

## Overview

This document defines the Telegram bot interface for UMAE.

## Architecture Principle

**Telegram is a thin interface layer. Analysis logic lives in the core engine.**

```
Telegram Handler
    ↓
Bot Service (Telegram-specific)
    ↓
Application/Analysis Service (interface layer)
    ↓
UMAE Core Engine
```

- Telegram Bot NEVER imports analysis logic directly
- Telegram Bot NEVER computes features or signals
- Telegram Bot receives typed `AnalysisResult` objects
- Telegram Bot formats results for display only

## Implementation Order

Telegram is implemented AFTER core engine is stable:

```
Phase 1: Core domain, data model, adapters
Phase 2: Candle engine, feature engine
Phase 3: Regime engine, baseline analysis
Phase 4: Backtesting, validation
Phase 5: Paper analysis
Phase 6: Application service/API ← Telegram depends on this
Phase 7: Telegram adapter ← LAST
```

## Bot Commands

### V1 Commands (First MVP)

| Command | Description | Status |
|---------|-------------|--------|
| `/start` | Welcome message | V1 |
| `/help` | Help text | V1 |
| `/analyze <symbol>` | Full analysis | V1 |
| `/status` | System health | V1 |

### V2 Commands

| Command | Description | Status |
|---------|-------------|--------|
| `/watchlist` | List watchlist | V2 |
| `/add <symbol>` | Add to watchlist | V2 |
| `/remove <symbol>` | Remove from watchlist | V2 |

### Future Commands (V3+)

| Command | Description | Status |
|---------|-------------|--------|
| `/alert <symbol>` | Set alert | Future |
| `/backtest <symbol>` | Run backtest | Future |
| `/paper <symbol>` | Paper trading status | Future |

## Command Specifications

### /start

**Input**: `/start`
**Response**: Welcome message with bot capabilities

```
Welcome to UMAE - Universal Market Analysis Engine

This bot provides multi-timeframe market analysis.
It is NOT a trading signal service.

Commands:
/analyze <symbol> - Analyze an asset
/status - System status
/help - Show help

Example:
/analyze BTCUSDT
/analyze AAPL
/analyze EURUSD

Disclaimer: This is for research and analysis only.
```

### /help

**Input**: `/help`
**Response**: Detailed help text

```
UMAE Commands:

/analyze <symbol>
  Full multi-timeframe analysis
  Example: /analyze BTCUSDT

/status
  Show system health and data status

/watchlist
  Show your watchlist

/add <symbol>
  Add symbol to watchlist

/remove <symbol>
  Remove from watchlist

Supported Assets:
  Crypto: BTC, ETH, SOL, BNB, etc.
  Stocks: AAPL, GOOGL, MSFT, etc.
  Forex: EURUSD, GBPUSD, etc.
  Indices: ^GSPC, ^DJI, etc.

Timeframes Analyzed:
  1m, 3m, 5m, 15m, 20m, 30m,
  1h, 2h, 4h, 6h, 12h, 1D, 1W

Disclaimer: Analysis only, not trading advice.
```

### /analyze

**Input**: `/analyze <symbol>`
**Examples**: `/analyze BTCUSDT`, `/analyze AAPL`, `/analyze EUR/USD`

**Response Structure**:

```
═══════════════════════════════
📊 ANALYSIS: BTC/USDT
═══════════════════════════════

⏰ 2026-01-15 10:30:00 UTC
💰 Price: $65,432.10
📦 Data: Fresh (2m ago)

───────────────────────────────
📈 MARKET REGIME
───────────────────────────────
Regime: TRENDING_UP
Confidence: 75%

───────────────────────────────
⏱ TIMEFRAME ANALYSIS
───────────────────────────────
TF    | Signal | Score | Regime
------+--------+-------+--------
1W    |   UP   |  0.82 | TREND
1D    |   UP   |  0.75 | TREND
12h   |   UP   |  0.68 | TREND
4h    |   UP   |  0.61 | TREND
1h    |   UP   |  0.54 | RANGE
15m   |   UP   |  0.45 | RANGE
5m    |  NEUT  |  0.12 | RANGE

───────────────────────────────
🎯 SIGNAL
───────────────────────────────
Signal: UP
Score: 0.72
Confidence: 68%

───────────────────────────────
📝 REASONS
───────────────────────────────
• HTF_BULLISH (4h, 6h, 12h, 1D, 1W)
• VOLUME_STRONG
• REGIME_TRENDING_UP

───────────────────────────────
📊 FEATURE SUMMARY
───────────────────────────────
Trend:     Bullish ✓
Momentum:  Bullish ✓
Volume:    Strong ✓
Volatility: Normal
Structure: HH_HL ✓

───────────────────────────────
⚠ WARNINGS
───────────────────────────────
• 5m timeframe neutral
• Near resistance at $66,000

───────────────────────────────
ℹ META
───────────────────────────────
Model: v1.0.0
Data: binance_20260115

═══════════════════════════════
⚠ This is analysis, not advice.
═══════════════════════════════
```

### /status

**Input**: `/status`
**Response**: System health status

```
═══════════════════════════════
🔧 SYSTEM STATUS
═══════════════════════════════

Providers:
  Binance:      ✅ OK
  Yahoo:        ✅ OK
  OANDA:        ⏸ Not configured

Database:       ✅ Connected
Analysis Engine: ✅ Running
Last Update:    2m ago

Data Quality:
  Binance: 99.8%
  Yahoo:   98.5%

Warnings:
  None

Uptime: 5d 12h 30m
Version: 0.1.0
═══════════════════════════════
```

### /watchlist

**Input**: `/watchlist`
**Response**: User's watchlist

```
Your Watchlist:

1. BTC/USDT (Binance) - UP 0.72
2. AAPL (Yahoo) - NEUTRAL 0.05
3. EUR/USD (OANDA) - DOWN -0.34

Use /add <symbol> to add
Use /remove <symbol> to remove
```

### /add

**Input**: `/add <symbol>`
**Example**: `/add SOLUSDT`

**Response (success)**:
```
Added SOL/USDT to your watchlist.

Current: UP 0.65
```

**Response (duplicate)**:
```
SOL/USDT is already in your watchlist.
```

**Response (invalid)**:
```
Invalid symbol: SOLUSDT

Please check the symbol and try again.
```

### /remove

**Input**: `/remove <symbol>`
**Example**: `/remove SOLUSDT`

**Response (success)**:
```
Removed SOL/USDT from your watchlist.
```

**Response (not found)**:
```
SOL/USDT is not in your watchlist.
```

## Response Contract

See `TELEGRAM_RESPONSE_CONTRACT.md` for typed response objects.

## Security

### Token Management

```python
# NEVER hardcode
# NEVER log
# Use environment variables


class TelegramConfig(BaseSettings):
    bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    enabled: bool = Field(True, env="TELEGRAM_ENABLED")
    rate_limit: int = Field(10, env="TELEGRAM_RATE_LIMIT")  # commands per minute
```

### Input Validation

- Validate symbol format before processing
- Reject unknown commands gracefully
- Sanitize user input
- Limit message length (4096 chars)

### Rate Limiting

```python
class UserRateLimiter:
    def __init__(self, max_commands: int = 10, window: int = 60):
        self.max_commands = max_commands
        self.window = window
        self.user_commands: dict[int, list[float]] = {}
    
    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        commands = self.user_commands.get(user_id, [])
        commands = [t for t in commands if now - t < self.window]
        
        if len(commands) >= self.max_commands:
            return False
        
        commands.append(now)
        self.user_commands[user_id] = commands
        return True
```

### Error Handling

```python
# Handle Telegram API errors
async def safe_send(chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except TimedOut:
        logger.warning(f"Telegram timeout for {chat_id}")
    except BotBlocked:
        logger.info(f"Bot blocked by {chat_id}")
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after)
    except Exception:
        logger.exception(f"Telegram error for {chat_id}")
```

### Duplicate Updates

```python
class UpdateDeduplicator:
    def __init__(self):
        self.seen_updates: set[int] = set()
        self.max_size = 10000
    
    def is_duplicate(self, update_id: int) -> bool:
        if update_id in self.seen_updates:
            return True
        self.seen_updates.add(update_id)
        if len(self.seen_updates) > self.max_size:
            self.seen_updates = set(list(self.seen_updates)[-1000:])
        return False
```

## User Data

### Storage

Per-user data stored in database:

```sql
CREATE TABLE telegram_users (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    username TEXT,
    watchlist JSON DEFAULT '[]',
    alert_config JSON DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Minimum Data

- `user_id`: Telegram user ID
- `chat_id`: Chat ID for sending messages
- `watchlist`: List of symbols
- `alert_config`: Alert settings (future)

### No Unnecessary Data

- Do NOT store message history
- Do NOT store personal information
- Do NOT track user behavior beyond commands

## Trading Restrictions

### V1 Prohibited

| Command | Status |
|---------|--------|
| `/buy` | PROHIBITED |
| `/sell` | PROHIBITED |
| `/order` | PROHIBITED |
| `/trade` | PROHIBITED |
| Any live execution | PROHIBITED |

### Future Consideration

- Paper trading commands (analysis only, no execution)
- Backtest results display
- Strategy performance tracking

## Reconnection

```python
class TelegramReconnector:
    def __init__(self, bot: Bot, max_retries: int = 5):
        self.bot = bot
        self.max_retries = max_retries

    async def run_with_reconnect(self) -> None:
        retries = 0
        while retries < self.max_retries:
            try:
                await self.bot.run_polling()
                break
            except Exception:
                retries += 1
                wait_time = min(2**retries, 60)
                logger.warning(f"Reconnecting in {wait_time}s...")
                await asyncio.sleep(wait_time)

        if retries >= self.max_retries:
            logger.critical("Max retries reached. Bot shutting down.")
```

## Testing Requirements

### Unit Tests

| Test | Description |
|------|-------------|
| `test_parse_analyze_command` | Parse `/analyze BTCUSDT` |
| `test_parse_analyze_with_slash` | Parse `/analyze BTC/USDT` |
| `test_parse_invalid_command` | Unknown command handling |
| `test_parse_missing_symbol` | `/analyze` without symbol |
| `test_format_analysis_result` | Format AnalysisResult to text |
| `test_format_status` | Format status response |
| `test_rate_limiter` | Rate limit enforcement |
| `test_update_deduplicator` | Duplicate update handling |

### Integration Tests

| Test | Description |
|------|-------------|
| `test_analyze_flow` | Full /analyze flow |
| `test_watchlist_add_remove` | Watchlist CRUD |
| `test_error_handling` | API error responses |
| `test_reconnection` | Bot reconnection |

### Mocking

- Mock Telegram API calls
- Mock analysis engine responses
- Use deterministic fixtures

## Configuration

```yaml
telegram:
  enabled: true
  bot_token: ${TELEGRAM_BOT_TOKEN}  # From env
  rate_limit: 10  # Commands per minute
  max_message_length: 4096
  default_timeframes:
    - "1h"
    - "4h"
    - "1D"
  timezone: "UTC"
```

## Dependencies

```toml
# In pyproject.toml [project.optional-dependencies]
telegram = [
    "python-telegram-bot>=20.7",
]
```

## File Structure

```
src/umae/
├── telegram/
│   ├── __init__.py
│   ├── bot.py              # Bot setup and main loop
│   ├── handlers.py         # Command handlers
│   ├── formatters.py       # Response formatting
│   ├── models.py           # Telegram-specific models
│   ├── services.py         # Bot services (watchlist, etc.)
│   ├── security.py         # Rate limiting, validation
│   └── config.py           # Telegram configuration
```

## Notes

1. Telegram is LAST in implementation order
2. Core engine must be stable first
3. Telegram only formats, never computes
4. All responses typed (AnalysisResult)
5. No trading commands in V1
6. Graceful error handling required
7. Tests mandatory before deploy
