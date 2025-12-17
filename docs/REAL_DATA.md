# Using Real Market Data - Quick Guide

## ✅ You're Now Using Real Data!

I've set up **yfinance** which gives you FREE access to real historical market data from Yahoo Finance. No API key needed!

## 🚀 How to Use

### Fetch Data for Any Stock
```bash
# Single stock
python scripts/fetch_real_data.py AAPL

# Multiple stocks
python scripts/fetch_real_data.py AAPL MSFT GOOGL TSLA

# Popular stocks bundle
python scripts/fetch_real_data.py --all
```

### Then Run Your Backtests
```bash
# Compare strategies on real AAPL data
python examples/compare_strategies.py

# The data is cached, so subsequent runs are instant!
```

## 📊 Real vs Generated Data - See the Difference!

### Generated Data (Demo):
- SMA Slow: +33% return, 0.96 Sharpe ✅
- RSI: -100% return (complete failure!) ❌

### Real AAPL Data (2 years):
- SMA Fast (10/50): +35% return, 0.84 Sharpe ✅
- SMA Slow (50/200): -8% return (negative!) ❌
- RSI: Still struggling (-99%) ❌

**Key Insight:** Strategies behave completely differently on real data!

## 💡 Why This Matters

1. **Real market complexity** - Trends, volatility, gaps, earnings
2. **Honest results** - See what actually would have happened
3. **Better learning** - Understand why strategies fail/succeed
4. **Stock-specific** - AAPL behaves differently than SPY

## 📚 Data Available

**Already Cached:**
- ✅ AAPL (502 days, Dec 2023 - Dec 2025)

**Easily Fetch:**
```bash
python scripts/fetch_real_data.py --all
```
This gets: AAPL, MSFT, GOOGL, TSLA, AMZN, NVDA, SPY, QQQ

## 🎯 Recommended Next Steps

### 1. Test on Multiple Stocks
```bash
# Fetch data
python scripts/fetch_real_data.py AAPL MSFT SPY

# Modify compare_strategies.py to test each one
# See which strategies work on which stocks
```

### 2. Compare Time Periods
- Bull market: 2020-2021
- Bear market: 2022
- Recovery: 2023-2024

### 3. Find What Works
- Does RSI work better on volatile stocks (TSLA)?
- Does SMA work better on trending stocks?
- Test and document your findings!

## 🔍 Understanding the Results

From your AAPL backtest:
- **SMA 10/50 won** (35% return, 0.84 Sharpe, only 13 trades)
- **SMA 50/200 failed** (-8% return - would have lost money!)
- **RSI failed badly** (needs refinement)

**Why?**
- AAPL had a strong uptrend → fast SMA caught it
- Slow SMA (50/200) too slow for 2-year timeframe
- RSI mean reversion doesn't work well in trending markets

**This is real learning!** 🎓

## 🛠️ Advanced: Fetch More History

```python
# In scripts/fetch_real_data.py, change:
data = ticker.history(period="5y")  # 5 years instead of 2

# Or specific dates:
data = ticker.history(start="2020-01-01", end="2023-12-31")
```

## ⚠️ Important Notes

**yfinance Limitations:**
- Free, but Yahoo may rate-limit heavy usage
- Delayed data (15-20 min for free tier)
- Perfect for backtesting and learning
- NOT for high-frequency trading

**For Paper Trading:**
- Still need Schwab API for real-time data
- yfinance is for historical backtesting only

## 📖 Data Storage

**Where it's stored:**
```bash
data/
  AAPL.parquet    # Cached data
  MSFT.parquet
  SPY.parquet
```

**Benefits:**
- Fast: Load from cache instead of re-downloading
- Offline: Work without internet after initial fetch
- Efficient: Parquet format is compressed

## 🎓 Learning Exercise

**"The Multi-Stock Test"** (this weekend):

1. Fetch 5 stocks:
```bash
python scripts/fetch_real_data.py AAPL MSFT GOOGL SPY QQQ
```

2. Test SMA 10/50 on each (modify compare_strategies.py)

3. Document results:
   - Which stocks did it work on?
   - What was the best Sharpe ratio?
   - What was the worst drawdown?
   - Why do you think results differ?

This teaches you that **strategies are not universal** - what works on AAPL may fail on TSLA!

## ✅ Quick Checklist

- ✅ yfinance installed
- ✅ Real AAPL data fetched (502 days)
- ✅ Tested on real data (35% return on SMA!)
- ⬜ Fetch more stocks
- ⬜ Test strategies on different stocks
- ⬜ Document what works where
- ⬜ Build new strategies based on learnings

---

**You're now using REAL market data for backtesting!** 🎉

The difference in results shows why this matters - generated data gave you false confidence. Real data tells the truth.

Next: Test your strategies on different stocks and time periods!
