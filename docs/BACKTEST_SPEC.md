# Universal Market Analysis Engine (UMAE) - Backtest Specification

## Overview

This document defines the backtesting framework, metrics, and validation methodology for UMAE.

## Backtesting Principles

1. **Transaction costs are mandatory** - No backtest without fees
2. **No look-ahead bias** - Signals use only past data
3. **Realistic execution** - Account for spread, slippage, latency
4. **Walk-forward validation** - Prevent overfitting
5. **Baseline comparison** - Every strategy must beat simple rules
6. **Reproducible** - Same config + same data = same results

## Backtesting Architecture

### Components

```
┌─────────────────────────────────────────────────┐
│              Backtesting Engine                  │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐            │
│  │  Signal      │  │  Execution  │            │
│  │  Generator   │──│  Simulator  │            │
│  └──────────────┘  └──────────────┘            │
│          │                   │                   │
│          ▼                   ▼                   │
│  ┌──────────────┐  ┌──────────────┐            │
│  │  Portfolio   │  │  Cost       │            │
│  │  Tracker     │──│  Calculator │            │
│  └──────────────┘  └──────────────┘            │
│          │                   │                   │
│          ▼                   ▼                   │
│  ┌──────────────┐  ┌──────────────┐            │
│  │  Metrics     │  │  Walk-Forward│            │
│  │  Calculator  │──│  Validator   │            │
│  └──────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────┘
```

### Flow

```
1. Load historical candles
2. Initialize portfolio
3. For each candle:
   a. Compute features (using only past data)
   b. Generate signal
   c. If signal triggers trade:
      - Calculate execution price (with slippage)
      - Calculate fees
      - Execute trade
      - Record trade
4. Calculate metrics
5. Generate report
```

## Execution Model

### Order Types

```python
class OrderSide(Enum):
    LONG = "long"  # Buy, expect price up
    SHORT = "short"  # Sell, expect price down


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
```

### Execution Price

```python
def calculate_execution_price(
    candle: Candle, side: OrderSide, slippage_model: SlippageModel
) -> Decimal:
    if side == OrderSide.LONG:
        # Buy at ask (close + half spread + slippage)
        return candle.close + slippage_model.spread / 2 + slippage_model.slippage
    else:
        # Sell at bid (close - half spread - slippage)
        return candle.close - slippage_model.spread / 2 - slippage_model.slippage
```

### Cost Models

#### Fee Model

```python
@dataclass
class FeeModel:
    maker_fee: Decimal = Decimal("0.001")  # 0.1%
    taker_fee: Decimal = Decimal("0.001")  # 0.1%
    minimum_fee: Decimal = Decimal("0.00")  # No minimum

    def calculate_fee(self, trade_value: Decimal, is_maker: bool) -> Decimal:
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        fee = trade_value * fee_rate
        return max(fee, self.minimum_fee)
```

#### Slippage Model

```python
@dataclass
class SlippageModel:
    base_spread: Decimal = Decimal("0.001")  # 0.1%
    base_slippage: Decimal = Decimal("0.0005")  # 0.05%

    # Volume-based slippage
    volume_impact_factor: Decimal = Decimal("0.0001")

    def calculate_slippage(self, trade_value: Decimal, average_daily_volume: Decimal) -> Decimal:
        # Basic slippage
        slippage = self.base_slippage

        # Volume impact
        volume_ratio = trade_value / average_daily_volume
        volume_impact = volume_ratio * self.volume_impact_factor

        return slippage + volume_impact
```

#### Spread Model

```python
@dataclass
class SpreadModel:
    base_spread: Decimal = Decimal("0.001")  # 0.1%

    # Spread can vary by:
    # - Time of day
    # - Volatility
    # - Liquidity

    def calculate_spread(self, volatility: Decimal, average_daily_volume: Decimal) -> Decimal:
        # Higher volatility = wider spread
        volatility_factor = min(volatility / Decimal("0.02"), Decimal("2.0"))

        # Lower volume = wider spread
        volume_factor = max(
            Decimal("1.0") / (average_daily_volume / Decimal("1000000")), Decimal("1.0")
        )

        return self.base_spread * volatility_factor * volume_factor
```

### Position Sizing

```python
class PositionSizing(Enum):
    FIXED = "fixed"  # Fixed amount per trade
    PERCENTAGE = "percentage"  # Percentage of portfolio
    KELLY = "kelly"  # Kelly criterion (future)
    RISK_PARITY = "risk_parity"  # Risk parity (future)


@dataclass
class PositionSizer:
    method: PositionSizing = PositionSizing.PERCENTAGE
    fixed_size: Decimal = Decimal("1000")
    percentage: Decimal = Decimal("0.02")  # 2% of portfolio
    max_position: Decimal = Decimal("0.10")  # 10% max

    def calculate_size(
        self, portfolio_value: Decimal, signal_confidence: float, volatility: Decimal
    ) -> Decimal:
        if self.method == PositionSizing.FIXED:
            return self.fixed_size

        elif self.method == PositionSizing.PERCENTAGE:
            size = portfolio_value * self.percentage
            return min(size, portfolio_value * self.max_position)

        # Other methods for future
        raise NotImplementedError
```

## Trade Management

### Entry Rules

```python
@dataclass
class EntryRules:
    # Minimum signal strength
    min_signal_score: float = 0.3

    # Minimum confluence
    min_htf_alignment: int = 2
    min_mtf_alignment: int = 2

    # Volume filter
    min_relative_volume: float = 0.8

    # Regime filter
    allowed_regimes: list[MarketRegime] = field(
        default_factory=lambda: [
            MarketRegime.TRENDING_UP,
            MarketRegime.TRENDING_DOWN,
            MarketRegime.RANGING,
            MarketRegime.BREAKOUT,
        ]
    )

    # Time filter
    trading_hours_only: bool = False
    avoid_first_minutes: int = 5  # Avoid first 5 minutes
    avoid_last_minutes: int = 5  # Avoid last 5 minutes
```

### Exit Rules

```python
@dataclass
class ExitRules:
    # Signal-based exit
    exit_on_signal_reversal: bool = True
    exit_on_neutral: bool = False
    
    # Stop loss
    use_stop_loss: bool = True
    stop_loss_percent: Decimal = Decimal("0.02")  # 2%
    trailing_stop: bool = False
    trailing_stop_percent: Decimal = Decimal("0.01")  # 1%
    
    # Take profit
    use_take_profit: bool = True
    take_profit_percent: Decimal = Decimal("0.04")  # 4%
    
    # Time-based exit
    max_holding_periods: int | None = None  # Max candles to hold
    
    # Regime-based exit
    exit_on_regime_change: bool = False
    exit_on_uncertain_regime: bool = True
```

### Risk Management

```python
@dataclass
class RiskManagement:
    # Portfolio limits
    max_portfolio_risk: Decimal = Decimal("0.06")  # 6% max risk
    max_correlated_positions: int = 3
    max_positions: int = 10
    
    # Per-trade limits
    max_loss_per_trade: Decimal = Decimal("0.02")  # 2%
    
    # Drawdown limits
    max_drawdown_halt: Decimal = Decimal("0.10")  # Halt at 10% DD
    drawdown_cooldown_periods: int = 10
    
    # Daily limits
    max_daily_loss: Decimal = Decimal("0.03")  # 3%
    max_daily_trades: int = 10
```

## Walk-Forward Validation

### Window Structure

```python
@dataclass
class WalkForwardWindow:
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    # Step sizes
    train_size_days: int = 365  # 1 year training
    test_size_days: int = 180  # 6 months testing
    step_size_days: int = 90  # Step 3 months
```

### Walk-Forward Process

```
Window 1:
  Train: 2020-01-01 to 2020-12-31
  Test:  2021-01-01 to 2021-06-30

Window 2:
  Train: 2020-04-01 to 2021-03-31
  Test:  2021-04-01 to 2021-09-30

Window 3:
  Train: 2020-07-01 to 2021-06-30
  Test:  2021-07-01 to 2021-12-31

...

Window N:
  Train: YYYY-MM-DD to YYYY-MM-DD
  Test:  YYYY-MM-DD to YYYY-MM-DD
```

### Walk-Forward Metrics

```python
@dataclass
class WalkForwardMetrics:
    windows: list[WalkForwardWindow]
    
    # Aggregate metrics
    mean_return: float
    std_return: float
    sharpe_ratio: float
    
    # Consistency
    profitable_windows: int
    total_windows: int
    win_rate_windows: float
    
    # Overfitting detection
    train_test_correlation: float
    overfitting_score: float  # Low = less overfitting
    
    # Stability
    return_stability: float  # Lower = more stable
    max_window_drawdown: float
```

## Baseline Strategies

### Baseline 1: Buy and Hold

```python
class BuyAndHoldBaseline:
    """
    Simple buy and hold.
    Entry: First candle
    Exit: Last candle
    """

    def generate_signals(self, candles: list[Candle]) -> list[Signal]:
        signals = []
        for i, candle in enumerate(candles):
            if i == 0:
                signals.append(Signal(type=SignalType.UP, score=1.0))
            else:
                signals.append(Signal(type=SignalType.NEUTRAL, score=0.0))
        return signals
```

### Baseline 2: Simple MA Crossover

```python
class MACrossoverBaseline:
    """
    Simple moving average crossover.
    Buy when fast MA > slow MA
    Sell when fast MA < slow MA
    """

    def __init__(self, fast_period: int = 20, slow_period: int = 50):
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signals(self, candles: list[Candle]) -> list[Signal]:
        signals = []
        for i in range(len(candles)):
            if i < self.slow_period:
                signals.append(Signal(type=SignalType.NO_SIGNAL, score=0.0))
                continue

            fast_ma = calculate_sma(candles[i - self.fast_period : i], self.fast_period)
            slow_ma = calculate_sma(candles[i - self.slow_period : i], self.slow_period)

            if fast_ma > slow_ma:
                signals.append(Signal(type=SignalType.UP, score=0.5))
            elif fast_ma < slow_ma:
                signals.append(Signal(type=SignalType.DOWN, score=-0.5))
            else:
                signals.append(Signal(type=SignalType.NEUTRAL, score=0.0))

        return signals
```

### Baseline 3: RSI Mean Reversion

```python
class RSIMeanReversionBaseline:
    """
    Buy when RSI oversold, sell when RSI overbought.
    """

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, candles: list[Candle]) -> list[Signal]:
        signals = []
        for i in range(len(candles)):
            if i < self.period:
                signals.append(Signal(type=SignalType.NO_SIGNAL, score=0.0))
                continue

            rsi = calculate_rsi(candles[i - self.period : i + 1], self.period)

            if rsi < self.oversold:
                signals.append(Signal(type=SignalType.UP, score=0.5))
            elif rsi > self.overbought:
                signals.append(Signal(type=SignalType.DOWN, score=-0.5))
            else:
                signals.append(Signal(type=SignalType.NEUTRAL, score=0.0))

        return signals
```

## Metrics Calculation

### Classification Metrics

```python
def calculate_classification_metrics(
    predictions: list[SignalType], actuals: list[SignalType]
) -> ClassificationMetrics:
    """
    Calculate precision, recall, F1 for UP/DOWN signals.
    NO_SIGNAL and NEUTRAL excluded from calculation.
    """
    # Filter to only UP/DOWN signals
    pred_updown = [
        (p, a) for p, a in zip(predictions, actuals) if p in [SignalType.UP, SignalType.DOWN]
    ]

    if not pred_updown:
        return ClassificationMetrics.empty()

    # True Positives, False Positives, etc.
    tp = sum(1 for p, a in pred_updown if p == a and p == SignalType.UP)
    fp = sum(1 for p, a in pred_updown if p != a and p == SignalType.UP)
    fn = sum(1 for p, a in pred_updown if p != a and a == SignalType.UP)
    tn = sum(1 for p, a in pred_updown if p == a and p == SignalType.DOWN)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / len(pred_updown) if pred_updown else 0.0

    return ClassificationMetrics(
        accuracy=accuracy, precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn, tn=tn
    )
```

### Financial Metrics

```python
def calculate_financial_metrics(
    trades: list[BacktestTrade], initial_capital: Decimal
) -> FinancialMetrics:
    """Calculate all financial metrics."""

    # Basic
    total_trades = len(trades)
    winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
    losing_trades = [t for t in trades if t.pnl and t.pnl < 0]

    # Returns
    total_pnl = sum(t.pnl for t in trades if t.pnl)
    total_return = total_pnl / initial_capital

    # Win/Loss
    avg_win = (
        sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else Decimal("0")
    )
    avg_loss = (
        sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else Decimal("0")
    )

    # Profit Factor
    gross_profit = sum(t.pnl for t in winning_trades) if winning_trades else Decimal("0")
    gross_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else Decimal("0")
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Expected Return
    win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0.0
    avg_pnl = total_pnl / total_trades if total_trades > 0 else Decimal("0")
    expected_return = float(avg_pnl / initial_capital) if initial_capital > 0 else 0.0

    # Drawdown
    drawdowns = calculate_drawdowns(trades, initial_capital)
    max_drawdown = max(drawdowns) if drawdowns else Decimal("0")

    # Holding Period
    avg_holding = sum(t.holding_periods for t in trades) / total_trades if total_trades > 0 else 0

    # Losing Streak
    losing_streak = calculate_losing_streak(trades)

    # Trade Frequency
    if trades:
        first_trade = min(t.entry_timestamp for t in trades)
        last_trade = max(t.entry_timestamp for t in trades)
        total_days = (last_trade - first_trade).days or 1
        trade_frequency = total_trades / total_days
    else:
        trade_frequency = 0.0

    # Costs
    total_fees = sum(t.fee_entry + (t.fee_exit or 0) for t in trades)
    total_slippage = sum(t.slippage_entry + (t.slippage_exit or 0) for t in trades)

    return FinancialMetrics(
        total_trades=total_trades,
        winning_trades=len(winning_trades),
        losing_trades=len(losing_trades),
        win_rate=win_rate,
        total_pnl=total_pnl,
        total_return=float(total_return),
        expected_return=expected_return,
        profit_factor=profit_factor,
        average_win=avg_win,
        average_loss=avg_loss,
        max_drawdown=max_drawdown,
        max_drawdown_percent=float(max_drawdown / initial_capital) if initial_capital else 0.0,
        average_holding_period=avg_holding,
        longest_losing_streak=losing_streak,
        trade_frequency=trade_frequency,
        total_fees=total_fees,
        total_slippage=total_slippage,
    )
```

### Segment Analysis

```python
def calculate_segment_analysis(
    trades: list[BacktestTrade], metrics: FinancialMetrics
) -> SegmentAnalysis:
    """Calculate performance by segment."""

    # By Timeframe
    by_timeframe = {}
    for tf in Timeframe:
        tf_trades = [t for t in trades if hasattr(t, "timeframe") and t.timeframe == tf]
        if tf_trades:
            by_timeframe[tf.value] = calculate_financial_metrics(tf_trades, Decimal("10000"))

    # By Asset
    by_asset = {}
    for trade in trades:
        asset = trade.symbol.split("/")[0]  # Simple extraction
        if asset not in by_asset:
            by_asset[asset] = []
        by_asset[asset].append(trade)

    by_asset_metrics = {}
    for asset, asset_trades in by_asset.items():
        by_asset_metrics[asset] = calculate_financial_metrics(asset_trades, Decimal("10000"))

    # By Regime
    by_regime = {}
    for regime in MarketRegime:
        regime_trades = [t for t in trades if t.regime_at_entry == regime]
        if regime_trades:
            by_regime[regime.value] = calculate_financial_metrics(regime_trades, Decimal("10000"))

    return SegmentAnalysis(
        by_timeframe=by_timeframe, by_asset=by_asset_metrics, by_regime=by_regime
    )
```

## Reporting

### Backtest Report

```python
@dataclass
class BacktestReport:
    # Metadata
    run_id: str
    name: str
    config: dict
    timestamp: datetime
    
    # Data
    symbol: str
    timeframe: Timeframe
    start_date: datetime
    end_date: datetime
    total_candles: int
    
    # Portfolio
    initial_capital: Decimal
    final_capital: Decimal
    
    # Metrics
    classification_metrics: ClassificationMetrics
    financial_metrics: FinancialMetrics
    segment_analysis: SegmentAnalysis
    
    # Walk-Forward (if applicable)
    walk_forward_result: WalkForwardResult | None
    
    # Baseline Comparison
    baseline_comparison: dict[str, FinancialMetrics]
    
    # Trades
    trades: list[BacktestTrade]
    
    # Signal Distribution
    signal_distribution: dict[SignalType, int]
    
    # Summary
    summary: str
    warnings: list[str]
```

### Report Generation

```python
def generate_report(
    backtest_run: BacktestRun,
    trades: list[BacktestTrade],
    metrics: FinancialMetrics,
    baseline_metrics: dict[str, FinancialMetrics],
) -> BacktestReport:
    """Generate comprehensive backtest report."""

    # Classification metrics
    predictions = [t.entry_signal for t in trades]
    actuals = [determine_actual(t) for t in trades]
    classification = calculate_classification_metrics(predictions, actuals)

    # Segment analysis
    segments = calculate_segment_analysis(trades, metrics)

    # Summary
    summary = generate_summary(metrics, classification, baseline_metrics)

    # Warnings
    warnings = generate_warnings(metrics, trades)

    return BacktestReport(
        run_id=backtest_run.id,
        name=backtest_run.name,
        config=backtest_run.strategy_config,
        timestamp=datetime.now(),
        symbol=backtest_run.symbol,
        timeframe=backtest_run.timeframe,
        start_date=backtest_run.start_date,
        end_date=backtest_run.end_date,
        total_candles=0,  # Calculate
        initial_capital=backtest_run.initial_capital,
        final_capital=calculate_final_capital(trades, backtest_run.initial_capital),
        classification_metrics=classification,
        financial_metrics=metrics,
        segment_analysis=segments,
        walk_forward_result=None,
        baseline_comparison=baseline_metrics,
        trades=trades,
        signal_distribution=calculate_signal_distribution(trades),
        summary=summary,
        warnings=warnings,
    )
```

## Quality Gates

### Minimum Requirements for Valid Backtest

| Metric | Minimum | Description |
|--------|---------|-------------|
| Total Trades | >= 30 | Statistical significance |
| Win Rate | > 40% | Better than random |
| Profit Factor | > 1.0 | Positive expectancy |
| Sharpe Ratio | > 0.5 | Risk-adjusted return |
| Max Drawdown | < 30% | Acceptable risk |
| Walk-Forward Win Rate | > 50% | Consistent performance |
| vs Baseline | > 0 | Beats buy-and-hold |

### Red Flags

| Issue | Description |
|-------|-------------|
| Overfitting | Train performance >> Test performance |
| Curve Fitting | Too many parameters |
| Look-ahead Bias | Future data in features |
| Survivorship Bias | Only winning assets |
| Transaction Cost Ignorance | No fees in backtest |
| Short Sample | Too few trades |
| Regime Dependency | Only works in one regime |

## Configuration Example

```yaml
backtest:
  initial_capital: 10000
  
  fees:
    maker_fee: 0.001
    taker_fee: 0.001
  
  slippage:
    base_spread: 0.001
    base_slippage: 0.0005
  
  position_sizing:
    method: percentage
    percentage: 0.02
    max_position: 0.10
  
  entry_rules:
    min_signal_score: 0.3
    min_htf_alignment: 2
    min_relative_volume: 0.8
  
  exit_rules:
    exit_on_signal_reversal: true
    use_stop_loss: true
    stop_loss_percent: 0.02
    use_take_profit: true
    take_profit_percent: 0.04
  
  walk_forward:
    train_days: 365
    test_days: 180
    step_days: 90
  
  baselines:
    - buy_and_hold
    - ma_crossover
    - rsi_mean_reversion
```

## Limitations

1. **Past performance ≠ future results** - Backtest is historical analysis
2. **Market conditions change** - What worked may stop working
3. **Execution assumptions** - Real execution may differ
4. **Data quality** - Bad data → bad backtest
5. **Overfitting risk** - Always validate out-of-sample
