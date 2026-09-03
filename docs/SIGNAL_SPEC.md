# Universal Market Analysis Engine (UMAE) - Signal Specification

## Overview

This document defines how signals are generated, scored, and interpreted in UMAE.

## Signal Philosophy

1. **NO_SIGNAL is a valid output** - Better to say nothing than say something wrong
2. **Score ≠ Probability** - Raw score is not a probability claim
3. **Evidence-based** - Signals require minimum evidence
4. **Multi-timeframe confluence** - Single timeframe signals are weak
5. **Auditability** - Every signal must be explainable

## Signal Types

### UP

Bullish evidence is sufficient.

**When to emit**:
- Multiple timeframes show bullish alignment
- Volume confirms the move
- Regime supports continuation
- No strong contradictory evidence

### DOWN

Bearish evidence is sufficient.

**When to emit**:
- Multiple timeframes show bearish alignment
- Volume confirms the move
- Regime supports continuation
- No strong contradictory evidence

### NEUTRAL

Evidence is balanced, no clear direction.

**When to emit**:
- Equal bullish and bearish evidence
- Market is in ranging regime
- No decisive pattern

### NO_SIGNAL

Insufficient evidence to form a signal.

**When to emit**:
- Conflicting timeframes
- Uncertain regime
- Weak features
- Low volume
- Insufficient data
- Too close to call

**This is the preferred default when unsure.**

## Signal Score

### Raw Score

A numeric value representing signal strength.

```
Range: -1.0 to 1.0
-1.0 = Strong bearish
 0.0 = Neutral
+1.0 = Strong bullish
```

**Properties**:
- NOT a probability
- NOT calibrated to accuracy
- Subjective scale based on feature weights
- Used for ranking, not decision-making

### Calibrated Confidence

A probability-like value after calibration.

```
Range: 0.0 to 1.0
0.0 = No confidence
1.0 = Maximum confidence
```

**Properties**:
- Calibrated using historical data
- Per-asset and per-regime specific
- Subject to overfitting risk
- Must be validated on out-of-sample data

**NEVER claim this is "accuracy" without statistical validation.**

## Multi-Timeframe Analysis

### Timeframe Classification

| Category | Timeframes | Role |
|----------|-----------|------|
| Higher (HTF) | 4h, 6h, 12h, 1D, 1W | Context, trend direction |
| Middle (MTF) | 15m, 20m, 30m, 1h, 2h | Bias, setup quality |
| Lower (LTF) | 1m, 3m, 5m | Timing, entry |

### Confluence Requirements

#### Minimum Confluence

```yaml
min_htf_alignment: 2      # At least 2 HTF must agree
min_mtf_alignment: 2      # At least 2 MTF must agree
min_ltf_confirmation: 1   # At least 1 LTF must confirm
```

#### Timeframe Weights

```yaml
timeframe_weights:
  1W: 0.15
  1D: 0.20
  12h: 0.15
  6h: 0.10
  4h: 0.10
  2h: 0.08
  1h: 0.07
  30m: 0.05
  20m: 0.04
  15m: 0.03
  5m: 0.02
  3m: 0.01
  1m: 0.00  # 1m only for timing, not direction
```

### Conflict Resolution

| Scenario | Resolution |
|----------|------------|
| HTF bullish, LTF bearish | Follow HTF, reduce confidence |
| HTF bearish, LTF bullish | Follow HTF, reduce confidence |
| HTF neutral, LTF strong | Weak signal, consider NO_SIGNAL |
| All timeframes aligned | Strong signal, higher confidence |
| Mixed signals across MTF | NO_SIGNAL |

## Feature Groups

### Trend Features

| Feature | Description | Parameters |
|---------|-------------|------------|
| `ema_fast` | Fast EMA value | period: 9 |
| `ema_slow` | Slow EMA value | period: 21 |
| `ema_trend` | Trend EMA value | period: 50 |
| `sma_200` | 200 SMA | period: 200 |
| `ma_slope` | MA slope (normalized) | period: 20 |
| `ma_crossover` | Fast/slow MA crossover signal | - |
| `market_structure` | HH/HL/LH/LL pattern | lookback: 20 |
| `structure_break` | Structure break detected | lookback: 20 |

**Interpretation**:
- `ema_fast > ema_slow` → Bullish
- `ma_slope > 0` → Bullish momentum
- `market_structure == "HH_HL"` → Uptrend
- `structure_break == "bullish"` → Potential reversal

### Momentum Features

| Feature | Description | Parameters |
|---------|-------------|------------|
| `rsi` | RSI value | period: 14 |
| `rsi_signal` | RSI signal (overbought/oversold) | ob: 70, os: 30 |
| `macd` | MACD line | fast: 12, slow: 26 |
| `macd_signal` | MACD signal line | period: 9 |
| `macd_histogram` | MACD histogram | - |
| `roc` | Rate of change | period: 10 |
| `momentum_change` | Momentum acceleration/deceleration | - |

**Interpretation**:
- `rsi < 30` → Oversold, potential bullish
- `rsi > 70` → Overbought, potential bearish
- `macd > macd_signal` → Bullish momentum
- `roc > 0` → Positive momentum

### Volume Features

| Feature | Description | Parameters |
|---------|-------------|------------|
| `relative_volume` | Volume vs average | period: 20 |
| `volume_expansion` | Volume increasing | period: 5 |
| `volume_confirmation` | Volume confirms price move | - |
| `obv` | On-Balance Volume | - |
| `vwap` | Volume Weighted Average Price | - |

**Interpretation**:
- `relative_volume > 1.5` → High volume, confirms move
- `volume_confirmation == True` → Move is genuine
- `obv_trending_up` → Accumulation

### Volatility Features

| Feature | Description | Parameters |
|---------|-------------|------------|
| `atr` | Average True Range | period: 14 |
| `atr_percent` | ATR as % of price | - |
| `volatility_percentile` | Volatility vs history | period: 100 |
| `volatility_expansion` | Volatility increasing | period: 5 |
| `candle_range` | Current candle range | - |

**Interpretation**:
- `volatility_percentile > 80` → High volatility regime
- `volatility_expansion == True` → Move may be accelerating
- `candle_range > atr * 2` → Significant candle

### Price Structure Features

| Feature | Description | Parameters |
|---------|-------------|------------|
| `breakout` | Breakout from range | lookback: 20 |
| `consolidation` | Price in consolidation | lookback: 20 |
| `support_level` | Nearest support | lookback: 50 |
| `resistance_level` | Nearest resistance | lookback: 50 |
| `rejection` | Rejection at level | lookback: 5 |
| `structure_shift` | Market structure change | lookback: 20 |

**Interpretation**:
- `breakout == "bullish"` → Price broke resistance
- `consolidation == True` → Range-bound market
- `rejection == "bearish"` → Rejected at resistance

## Signal Generation Algorithm

### Step 1: Compute Features

For each timeframe, compute all enabled features.

```
For each timeframe in [1m, 3m, 5m, ..., 1W]:
    features[timeframe] = compute_features(candles[timeframe])
```

### Step 2: Detect Regime

For each timeframe, detect market regime.

```
For each timeframe in [1m, 3m, 5m, ..., 1W]:
    regime[timeframe] = detect_regime(features[timeframe])
```

### Step 3: Generate Timeframe Signals

For each timeframe, generate a local signal.

```
For each timeframe in [1m, 3m, 5m, ..., 1W]:
    signal[timeframe] = generate_timeframe_signal(
        features[timeframe],
        regime[timeframe]
    )
```

### Step 4: Multi-Timeframe Aggregation

Combine timeframe signals into composite signal.

```
composite = aggregate_signals(
    signal[1m], signal[3m], ..., signal[1W],
    weights,
    regime_context
)
```

### Step 5: Apply Confidence Rules

Apply minimum confluence rules.

```
if insufficient_confluence(composite):
    composite.signal = NO_SIGNAL
    composite.reason_codes.append("INSUFFICIENT_CONFLUENCE")
```

### Step 6: Calibrate (Optional)

If calibration model available, calibrate confidence.

```
if calibration_model_exists:
    composite.calibrated_confidence = calibrate(
        composite.raw_score,
        composite.regime,
        composite.symbol
    )
```

### Step 7: Generate Reason Codes

Explain why signal appeared (or didn't).

```
composite.reason_codes = generate_reason_codes(
    composite,
    timeframe_signals,
    regime
)
```

### Step 8: Audit

Log full audit record.

```
audit_log.record(composite)
```

## Reason Codes

### Direction Codes

| Code | Description |
|------|-------------|
| `HTF_BULLISH` | Higher timeframe(s) show bullish alignment |
| `HTF_BEARISH` | Higher timeframe(s) show bearish alignment |
| `HTF_NEUTRAL` | Higher timeframes are neutral |
| `MTF_BULLISH` | Middle timeframe(s) show bullish alignment |
| `MTF_BEARISH` | Middle timeframe(s) show bearish alignment |
| `LTF_BULLISH` | Lower timeframe(s) show bullish alignment |
| `LTF_BEARISH` | Lower timeframe(s) show bearish alignment |

### Volume Codes

| Code | Description |
|------|-------------|
| `VOLUME_STRONG` | Volume confirms price move |
| `VOLUME_WEAK` | Volume does not confirm |
| `VOLUME_DECLINING` | Volume is declining |

### Regime Codes

| Code | Description |
|------|-------------|
| `REGIME_TRENDING_UP` | Market in uptrend |
| `REGIME_TRENDING_DOWN` | Market in downtrend |
| `REGIME_RANGING` | Market range-bound |
| `REGIME_HIGH_VOLATILITY` | High volatility environment |
| `REGIME_LOW_VOLATILITY` | Low volatility environment |
| `REGIME_BREAKOUT` | Potential breakout |
| `REGIME_UNCERTAIN` | Cannot determine regime |

### Conflict Codes

| Code | Description |
|------|-------------|
| `CONFLICTING_SIGNALS` | Timeframes show conflicting signals |
| `INSUFFICIENT_CONFLUENCE` | Not enough timeframes agree |
| `WEAK_EVIDENCE` | Features are weak |
| `NO_DATA` | Insufficient data for analysis |

### Entry Codes

| Code | Description |
|------|-------------|
| `FRESH_SIGNAL` | New signal just generated |
| `CONTINUATION` | Signal continues from previous |
| `REVERSAL` | Signal reversed from previous |

## Feature Scoring

### Individual Feature Score

Each feature contributes to the raw score.

```
feature_score = feature_value * feature_weight * direction_multiplier
```

### Direction Multiplier

| Feature | Bullish | Bearish |
|---------|---------|---------|
| `ema_fast > ema_slow` | +1.0 | -1.0 |
| `rsi < 30` | +0.8 | 0.0 |
| `rsi > 70` | 0.0 | -0.8 |
| `macd > signal` | +0.7 | -0.7 |
| `volume > 1.5 avg` | ±0.5 | ±0.5 |
| `regime == trending_up` | +0.6 | -0.6 |

### Score Aggregation

```
raw_score = sum(feature_scores) / count(features)
```

Normalized to [-1.0, 1.0] range.

## Signal Thresholds

```yaml
signal_thresholds:
  # Minimum raw score to emit UP/DOWN
  min_score: 0.3
  
  # Minimum confluence
  min_htf_alignment: 2
  min_mtf_alignment: 2
  min_ltf_confirmation: 1
  
  # Volume requirement
  min_relative_volume: 0.8
  
  # Regime impact
  regime_penalty:
    uncertain: 0.5
    ranging: 0.7
    high_volatility: 0.8
  
  # Confidence thresholds
  high_confidence: 0.7
  medium_confidence: 0.5
  low_confidence: 0.3
```

## Signal Output Format

```python
@dataclass
class SignalOutput:
    # Core
    signal: SignalType  # UP, DOWN, NEUTRAL, NO_SIGNAL
    raw_score: float  # -1.0 to 1.0
    calibrated_confidence: float | None

    # Context
    symbol: str
    price: Decimal
    timestamp: datetime

    # Timeframe breakdown
    timeframe_signals: dict[Timeframe, TimeframeSignal]

    # Regime
    regime: MarketRegime
    regime_confidence: float

    # Explanation
    reason_codes: list[str]
    summary: str  # Human-readable summary

    # Metadata
    model_version: str
    data_version: str
```

## Example Outputs

### Strong UP Signal

```json
{
  "signal": "UP",
  "raw_score": 0.72,
  "calibrated_confidence": 0.68,
  "symbol": "BTC/USDT",
  "price": 65432.10,
  "timestamp": "2026-01-15T10:30:00Z",
  "timeframe_signals": {
    "1D": {"signal": "UP", "score": 0.8},
    "4h": {"signal": "UP", "score": 0.7},
    "1h": {"signal": "UP", "score": 0.6},
    "15m": {"signal": "UP", "score": 0.5}
  },
  "regime": "trending_up",
  "regime_confidence": 0.75,
  "reason_codes": [
    "HTF_BULLISH",
    "MTF_BULLISH",
    "VOLUME_STRONG",
    "REGIME_TRENDING_UP"
  ],
  "summary": "Strong bullish alignment across timeframes with volume confirmation in uptrend regime",
  "model_version": "1.0.0",
  "data_version": "binance_20260115_50000"
}
```

### NO_SIGNAL Output

```json
{
  "signal": "NO_SIGNAL",
  "raw_score": 0.12,
  "calibrated_confidence": null,
  "symbol": "ETH/USDT",
  "price": 3456.78,
  "timestamp": "2026-01-15T10:30:00Z",
  "timeframe_signals": {
    "1D": {"signal": "NEUTRAL", "score": 0.1},
    "4h": {"signal": "UP", "score": 0.3},
    "1h": {"signal": "DOWN", "score": -0.2},
    "15m": {"signal": "NEUTRAL", "score": 0.05}
  },
  "regime": "uncertain",
  "regime_confidence": 0.4,
  "reason_codes": [
    "CONFLICTING_SIGNALS",
    "INSUFFICIENT_CONFLUENCE",
    "REGIME_UNCERTAIN",
    "VOLUME_WEAK"
  ],
  "summary": "Conflicting signals across timeframes with uncertain regime. Insufficient evidence for directional signal.",
  "model_version": "1.0.0",
  "data_version": "binance_20260115_50000"
}
```

## Calibration

### Method

Use isotonic regression or Platt scaling for calibration.

```python
# Platt scaling
from sklearn.linear_model import LogisticRegression

model = LogisticRegression()
model.fit(train_scores, train_labels)
calibrated = model.predict_proba(new_score)[:, 1]
```

### Per-Segment Calibration

Calibrate separately for:
- Each asset type (crypto, stock, forex)
- Each regime (trending, ranging, etc.)
- Each major timeframe

### Calibration Validation

- Use time-series split (not random)
- Report calibration error (Brier score)
- Validate on out-of-sample data
- Recalibrate periodically

## Constraints

1. **No forward-looking signals** - All features must use only past data
2. **No overconfidence** - Default to NO_SIGNAL when unsure
3. **No guaranteed returns** - Signal is analysis, not prediction
4. **Audit everything** - Every signal must be explainable
5. **Reproducible** - Same data + same config = same signal
