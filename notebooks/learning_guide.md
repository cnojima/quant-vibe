# Strategy Development Learning Notebook

This notebook will help you learn to develop and backtest trading strategies.

## Setup

```python
# Import required libraries
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Import quant-vibe modules
from quant_vibe.data import MarketDataClient, DataStore
from quant_vibe.strategies import SMACrossoverStrategy, RSIStrategy
from quant_vibe.backtesting import BacktestEngine, PerformanceMetrics
from quant_vibe.indicators import calculate_sma, calculate_ema, calculate_rsi, calculate_macd

# Configure matplotlib
%matplotlib inline
plt.style.use('seaborn-v0_8-darkgrid')
```

## Part 1: Load and Explore Data

```python
# Load some test data
store = DataStore()
symbol = "AAPL"

# Load from cache or fetch new data
data = store.load(symbol)
if data is None:
    client = MarketDataClient(provider="alpha_vantage")
    data = client.fetch_daily_data(symbol)
    store.save(symbol, data)

print(f"Loaded {len(data)} days of {symbol} data")
print(f"Date range: {data.index[0]} to {data.index[-1]}")
data.head()
```

```python
# Visualize the price data
plt.figure(figsize=(14, 7))
plt.plot(data.index, data['Close'], label='Close Price')
plt.title(f'{symbol} Price History')
plt.xlabel('Date')
plt.ylabel('Price ($)')
plt.legend()
plt.grid(True)
plt.show()
```

## Part 2: Calculate Technical Indicators

```python
# Calculate various indicators
data['SMA_50'] = calculate_sma(data['Close'], 50)
data['SMA_200'] = calculate_sma(data['Close'], 200)
data['RSI'] = calculate_rsi(data['Close'], 14)
data['EMA_20'] = calculate_ema(data['Close'], 20)

# Display recent data with indicators
data[['Close', 'SMA_50', 'SMA_200', 'RSI']].tail(10)
```

```python
# Visualize indicators
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

# Price and moving averages
ax1.plot(data.index, data['Close'], label='Close', linewidth=1)
ax1.plot(data.index, data['SMA_50'], label='SMA 50', linewidth=1)
ax1.plot(data.index, data['SMA_200'], label='SMA 200', linewidth=1)
ax1.set_title(f'{symbol} - Price and Moving Averages')
ax1.set_ylabel('Price ($)')
ax1.legend()
ax1.grid(True)

# RSI
ax2.plot(data.index, data['RSI'], label='RSI', color='purple', linewidth=1)
ax2.axhline(y=70, color='r', linestyle='--', label='Overbought (70)')
ax2.axhline(y=30, color='g', linestyle='--', label='Oversold (30)')
ax2.set_title('Relative Strength Index (RSI)')
ax2.set_xlabel('Date')
ax2.set_ylabel('RSI')
ax2.legend()
ax2.grid(True)
ax2.set_ylim(0, 100)

plt.tight_layout()
plt.show()
```

## Part 3: Test Your First Strategy

```python
# Create and test SMA Crossover strategy
strategy = SMACrossoverStrategy(fast_period=50, slow_period=200)
engine = BacktestEngine(initial_capital=100000.0, commission=0.001)

# Run backtest
portfolio = engine.run(strategy, data)
metrics = PerformanceMetrics.calculate(portfolio)

# Display results
print(f"\\nStrategy: {strategy.name}")
print("=" * 50)
for key, value in metrics.items():
    print(f"{key}: {value:.2f}")
print(f"Total Trades: {engine.results['total_trades']}")
```

```python
# Plot equity curve
plt.figure(figsize=(14, 7))
plt.plot(portfolio.index, portfolio['Portfolio_Value'], label='Portfolio Value', linewidth=2)
plt.axhline(y=100000, color='r', linestyle='--', label='Initial Capital', linewidth=1)
plt.title(f'{strategy.name} - Equity Curve')
plt.xlabel('Date')
plt.ylabel('Portfolio Value ($)')
plt.legend()
plt.grid(True)
plt.show()
```

## Part 4: Build Your Own Strategy

```python
# Test the RSI strategy
rsi_strategy = RSIStrategy(rsi_period=14, oversold_threshold=30, overbought_threshold=70)
rsi_portfolio = engine.run(rsi_strategy, data)
rsi_metrics = PerformanceMetrics.calculate(rsi_portfolio)

print(f"\\nStrategy: {rsi_strategy.name}")
print("=" * 50)
for key, value in rsi_metrics.items():
    print(f"{key}: {value:.2f}")
print(f"Total Trades: {engine.results['total_trades']}")
```

## Part 5: Compare Strategies

```python
# Compare multiple strategies
strategies_to_test = [
    SMACrossoverStrategy(fast_period=10, slow_period=50),
    SMACrossoverStrategy(fast_period=50, slow_period=200),
    RSIStrategy(rsi_period=14, oversold_threshold=30, overbought_threshold=70),
    RSIStrategy(rsi_period=14, oversold_threshold=20, overbought_threshold=80),
]

results = []
for strat in strategies_to_test:
    port = engine.run(strat, data)
    met = PerformanceMetrics.calculate(port)
    results.append({
        'Strategy': strat.name,
        'Total Return': met['total_return'],
        'Sharpe Ratio': met['sharpe_ratio'],
        'Max Drawdown': met['max_drawdown'],
        'Win Rate': met['win_rate'],
        'Trades': engine.results['total_trades']
    })

comparison_df = pd.DataFrame(results)
comparison_df
```

```python
# Visualize comparison
fig, axes = plt.subplots(2, 2, figsize=(15, 10))

comparison_df.plot(x='Strategy', y='Total Return', kind='bar', ax=axes[0,0], legend=False)
axes[0,0].set_title('Total Return (%)')
axes[0,0].set_xlabel('')

comparison_df.plot(x='Strategy', y='Sharpe Ratio', kind='bar', ax=axes[0,1], legend=False, color='orange')
axes[0,1].set_title('Sharpe Ratio')
axes[0,1].set_xlabel('')

comparison_df.plot(x='Strategy', y='Max Drawdown', kind='bar', ax=axes[1,0], legend=False, color='red')
axes[1,0].set_title('Max Drawdown (%)')
axes[1,0].set_xlabel('')

comparison_df.plot(x='Strategy', y='Win Rate', kind='bar', ax=axes[1,1], legend=False, color='green')
axes[1,1].set_title('Win Rate (%)')
axes[1,1].set_xlabel('')

plt.tight_layout()
plt.show()
```

## Part 6: Experiment!

Now it's your turn. Try these exercises:

### Exercise 1: Modify Parameters
- Change the RSI thresholds (try 25/75, 20/80)
- Change SMA periods (try 20/50, 10/30)
- Which parameters work best?

### Exercise 2: Create a New Strategy
- Try a MACD crossover strategy
- Combine multiple indicators (RSI + SMA)
- Add a stop-loss rule

### Exercise 3: Test on Different Stocks
- Run the same strategy on MSFT, GOOGL, TSLA
- Does the best strategy change?
- Why might that be?

### Exercise 4: Analyze Results
- Which strategy has the best Sharpe ratio?
- Which has the fewest trades?
- Which has the lowest drawdown?
- What's the tradeoff between return and risk?

## Next Steps

1. Implement Bollinger Bands strategy
2. Add position sizing (risk % of portfolio)
3. Add stop-loss and take-profit levels
4. Test on multiple timeframes
5. Build a momentum strategy
6. Combine signals from multiple indicators

Good luck! 🚀
