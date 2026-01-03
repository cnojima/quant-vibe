# Trading Strategies Guide

This guide provides an overview of all trading strategies implemented in the quant-vibe backtester.

## Table of Contents
- [Trend-Following Strategies](#trend-following-strategies)
- [Mean Reversion Strategies](#mean-reversion-strategies)
- [Momentum Strategies](#momentum-strategies)
- [Confirmation Strategies](#confirmation-strategies)
- [Usage Examples](#usage-examples)

---

## Trend-Following Strategies

### 1. SMA Crossover Strategy (`SMACrossoverStrategy`)
**File:** `src/quant_vibe/strategies/sma_crossover.py`

Classic moving average crossover strategy using Simple Moving Averages.

**Signals:**
- **BUY:** Fast SMA crosses above Slow SMA
- **SELL:** Fast SMA crosses below Slow SMA

**Parameters:**
- `fast_period`: Period for fast SMA (default: 50)
- `slow_period`: Period for slow SMA (default: 200)

**Best For:** Strong trending markets, longer timeframes

---

### 2. SMA Crossover with Delay (`SMACrossoverDelayedStrategy`)
**File:** `src/quant_vibe/strategies/sma_crossover_delayed.py`

Enhanced version of SMA crossover that waits for confirmation before signaling.

**Signals:**
- **BUY:** Fast SMA crosses above Slow SMA and remains above for `delay_periods`
- **SELL:** Fast SMA crosses below Slow SMA and remains below for `delay_periods`

**Parameters:**
- `fast_period`: Period for fast SMA (default: 50)
- `slow_period`: Period for slow SMA (default: 200)
- `delay_periods`: Confirmation periods (default: 5)

**Best For:** Reducing whipsaws and false signals in choppy markets

---

### 3. EMA Crossover Strategy (`EMACrossoverStrategy`)
**File:** `src/quant_vibe/strategies/ema_crossover.py`

Similar to SMA crossover but uses Exponential Moving Averages for faster response.

**Signals:**
- **BUY:** Fast EMA crosses above Slow EMA
- **SELL:** Fast EMA crosses below Slow EMA

**Parameters:**
- `fast_period`: Period for fast EMA (default: 12)
- `slow_period`: Period for slow EMA (default: 26)

**Best For:** More responsive to recent price changes, shorter timeframes

---

### 4. Triple Moving Average Strategy (`TripleMAStrategy`)
**File:** `src/quant_vibe/strategies/triple_ma.py`

Uses three moving averages to identify strong, aligned trends.

**Signals:**
- **BUY:** Short MA > Medium MA > Long MA (all bullish aligned)
- **SELL:** Short MA < Medium MA < Long MA (all bearish aligned)

**Parameters:**
- `short_period`: Short MA period (default: 5)
- `medium_period`: Medium MA period (default: 20)
- `long_period`: Long MA period (default: 50)

**Best For:** Strong trending markets, avoids choppy sideways action

---

### 5. MACD Crossover Strategy (`MACDCrossoverStrategy`)
**File:** `src/quant_vibe/strategies/macd_crossover.py`

Trend-following strategy based on MACD indicator.

**Signals:**
- **BUY:** MACD line crosses above Signal line
- **SELL:** MACD line crosses below Signal line

**Parameters:**
- `fast_period`: Fast EMA period (default: 12)
- `slow_period`: Slow EMA period (default: 26)
- `signal_period`: Signal line period (default: 9)

**Best For:** Identifying trend changes and momentum shifts

---

## Mean Reversion Strategies

### 6. RSI Strategy (`RSIStrategy`)
**File:** `src/quant_vibe/strategies/rsi_strategy.py`

Mean reversion strategy based on RSI overbought/oversold levels.

**Signals:**
- **BUY:** RSI < oversold threshold
- **SELL:** RSI > overbought threshold

**Parameters:**
- `rsi_period`: RSI calculation period (default: 14)
- `oversold_threshold`: Buy trigger level (default: 30)
- `overbought_threshold`: Sell trigger level (default: 70)

**Best For:** Range-bound markets, catching price extremes

---

### 7. Bollinger Bands Strategy (`BollingerBandsStrategy`)
**File:** `src/quant_vibe/strategies/bollinger_bands.py`

Mean reversion using Bollinger Bands for adaptive volatility.

**Signals:**
- **BUY:** Price touches/crosses below lower band
- **SELL:** Price touches/crosses above upper band

**Parameters:**
- `period`: Moving average period (default: 20)
- `num_std`: Number of standard deviations (default: 2.0)

**Best For:** Adapts to volatility, works in various market conditions

---

### 8. RSI with MA Filter (`RSIMAFilterStrategy`)
**File:** `src/quant_vibe/strategies/rsi_ma_filter.py`

RSI mean reversion with trend filter to trade only with the trend.

**Signals:**
- **BUY:** RSI < oversold AND price above MA (uptrend)
- **SELL:** RSI > overbought AND price below MA (downtrend)

**Parameters:**
- `rsi_period`: RSI calculation period (default: 14)
- `oversold_threshold`: Buy trigger level (default: 30)
- `overbought_threshold`: Sell trigger level (default: 70)
- `ma_period`: Trend filter MA period (default: 200)

**Best For:** Reducing false signals by combining mean reversion with trend

---

## Momentum Strategies

### 9. MACD Histogram Strategy (`MACDHistogramStrategy`)
**File:** `src/quant_vibe/strategies/macd_histogram.py`

Captures momentum shifts earlier than MACD crossover.

**Signals:**
- **BUY:** Histogram crosses above zero (turns positive)
- **SELL:** Histogram crosses below zero (turns negative)

**Parameters:**
- `fast_period`: Fast EMA period (default: 12)
- `slow_period`: Slow EMA period (default: 26)
- `signal_period`: Signal line period (default: 9)
- `threshold`: Minimum histogram value (default: 0.0)

**Best For:** Early momentum detection, faster entries/exits

---

### 10. Multi-Timeframe RSI Strategy (`MultiRSIStrategy`)
**File:** `src/quant_vibe/strategies/multi_rsi.py`

Uses multiple RSI periods for stronger confirmation.

**Signals:**
- **BUY:** ALL RSI values < oversold threshold
- **SELL:** ALL RSI values > overbought threshold

**Parameters:**
- `rsi_periods`: Tuple of RSI periods (default: (7, 14, 21))
- `oversold_threshold`: Buy trigger level (default: 30)
- `overbought_threshold`: Sell trigger level (default: 70)

**Best For:** High-conviction signals, reducing false positives

---

## Confirmation Strategies

### 11. RSI + MACD Confirmation Strategy (`RSIMACDConfirmationStrategy`)
**File:** `src/quant_vibe/strategies/rsi_macd_confirmation.py`

Requires both RSI and MACD to agree before signaling.

**Signals:**
- **BUY:** RSI < oversold AND MACD bullish crossover
- **SELL:** RSI > overbought AND MACD bearish crossover

**Parameters:**
- `rsi_period`: RSI calculation period (default: 14)
- `oversold_threshold`: RSI buy trigger (default: 30)
- `overbought_threshold`: RSI sell trigger (default: 70)
- `macd_fast`: MACD fast period (default: 12)
- `macd_slow`: MACD slow period (default: 26)
- `macd_signal`: MACD signal period (default: 9)

**Best For:** High-quality signals, lower trade frequency

---

## Usage Examples

### Basic Strategy Usage

```python
from quant_vibe.strategies import EMACrossoverStrategy
from quant_vibe.backtesting import BacktestEngine
from quant_vibe.data import DataStore

# Load data
data_store = DataStore("data/backtest_db/spx_1min.db")
data = data_store.load_data("SPY")

# Create strategy
strategy = EMACrossoverStrategy(fast_period=12, slow_period=26)

# Run backtest
engine = BacktestEngine(
    data=data,
    strategy=strategy,
    initial_capital=10000,
    commission=0.001
)

result = engine.run()
metrics = result.calculate_metrics()
print(f"Total Return: {metrics['total_return']:.2%}")
```

### Comparing Multiple Strategies

```python
from quant_vibe.strategies import (
    MACDCrossoverStrategy,
    RSIMAFilterStrategy,
    BollingerBandsStrategy
)

strategies = [
    MACDCrossoverStrategy(),
    RSIMAFilterStrategy(),
    BollingerBandsStrategy(period=20, num_std=2.0)
]

for strategy in strategies:
    engine = BacktestEngine(data, strategy, 10000)
    result = engine.run()
    print(f"{strategy.name}: {result.calculate_metrics()['total_return']:.2%}")
```

### Running the Demo

```bash
# Test all strategies at once
python examples/new_strategies_demo.py
```

---

## Strategy Selection Guide

| Market Condition | Recommended Strategies |
|-----------------|------------------------|
| **Strong Uptrend** | EMA Crossover, MACD Crossover, Triple MA |
| **Strong Downtrend** | EMA Crossover, MACD Crossover, Triple MA |
| **Range-Bound** | RSI Strategy, Bollinger Bands, Multi-RSI |
| **Choppy/Sideways** | SMA Delayed, RSI + MA Filter, RSI + MACD Confirmation |
| **High Volatility** | Bollinger Bands, MACD Histogram |
| **Low Volatility** | Triple MA, Multi-RSI |

---

## Parameter Optimization Tips

1. **Moving Average Periods:**
   - Shorter periods (5-20): More signals, faster response, more whipsaws
   - Medium periods (20-50): Balanced approach
   - Longer periods (50-200): Fewer signals, more reliable, slower response

2. **RSI Thresholds:**
   - More aggressive: 35/65 (more trades)
   - Standard: 30/70 (balanced)
   - Conservative: 25/75 (fewer trades, stronger signals)

3. **Bollinger Bands:**
   - Narrow bands (1.5 std): More sensitive, more signals
   - Standard bands (2.0 std): Balanced
   - Wide bands (2.5+ std): Only extreme moves

4. **Commission Impact:**
   - Higher frequency strategies are more sensitive to commissions
   - Consider slippage in your commission parameter

---

## Creating Custom Strategies

To create your own strategy, inherit from the `Strategy` base class:

```python
from quant_vibe.strategies import Strategy, Signal
import pandas as pd

class MyCustomStrategy(Strategy):
    def __init__(self, param1: int = 10):
        super().__init__(name=f"MyStrategy_{param1}")
        self.param1 = param1
    
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        self.validate_data(data)
        signals = pd.Series(Signal.HOLD.value, index=data.index)
        
        # Your signal logic here
        # signals[condition] = Signal.BUY.value
        # signals[condition] = Signal.SELL.value
        
        return signals
```

---

## Next Steps

1. **Backtest:** Run `examples/new_strategies_demo.py` to see all strategies in action
2. **Optimize:** Adjust parameters for your specific market/timeframe
3. **Combine:** Create hybrid strategies by combining multiple indicators
4. **Validate:** Test on out-of-sample data before live trading

For more information, see:
- `README.md` - Project overview
- `QUICKSTART.md` - Getting started guide
- `examples/` - More example scripts
