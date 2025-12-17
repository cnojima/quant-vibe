# Quick Start Guide - First Day

## 🚀 Get Started in 5 Minutes

### Step 1: Activate Environment
```bash
source activate.sh
```

### Step 2: Run Your First Comparison
```bash
# Compare different strategies (uses cached data if available)
python examples/compare_strategies.py
```

### Step 3: Open the Interactive Jupyter Notebook
```bash
# Launch Jupyter (already installed ✅)
jupyter notebook notebooks/getting_started.ipynb
```

This opens an **interactive** notebook where you can run code, see results, and learn by doing!

## 📖 What You Have Now

### Working Examples
1. **Simple Backtest** (`examples/simple_backtest.py`)
   - Fetch data
   - Run strategy
   - See performance metrics

2. **Strategy Comparison** (`examples/compare_strategies.py`)
   - Test multiple strategies at once
   - Compare performance side-by-side
   - Find the best performer

3. **Calculate Indicators** (`examples/calculate_indicators.py`)
   - Learn technical indicators
   - See how they're calculated

### Ready-to-Use Strategies
1. **SMA Crossover** - Trend following with moving averages
2. **RSI Mean Reversion** - Buy oversold, sell overbought

### Available Indicators
- SMA (Simple Moving Average)
- EMA (Exponential Moving Average)  
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)

## 🎯 Your Learning Path

### Today (15 minutes)
```bash
# 1. Test the comparison tool
python examples/compare_strategies.py

# 2. Read the results - which strategy performed best?

# 3. Open NEXT_STEPS.md and read Phase 1
```

### This Weekend (2-3 hours)
1. **Modify RSI Strategy**
   - Edit `src/quant_vibe/strategies/rsi_strategy.py`
   - Try different thresholds (20/80 instead of 30/70)
   - Run comparison again - did it improve?

2. **Create Your First Strategy**
   - Copy `rsi_strategy.py` to `my_strategy.py`
   - Combine RSI + SMA signals
   - Test it!

3. **Read Strategy Development Resources**
   - Check out the recommended books in NEXT_STEPS.md
   - Watch some YouTube videos on RSI/MACD strategies

### Next Week (5-10 hours)
1. **Schwab API Setup**
   - Register at developer.schwab.com
   - Get API credentials
   - Test authentication

2. **Build 3 More Strategies**
   - Bollinger Bands
   - MACD crossover
   - Momentum strategy

3. **Start Paper Trading Prep**
   - Read `src/quant_vibe/data/schwab_client.py`
   - Plan your paper trading workflow

## 🛠️ Common Commands

```bash
# Run all tests
pytest

# Run specific test
pytest tests/unit/test_strategies.py -v

# Format code
black src/ tests/

# Check code style
ruff check src/

# Run a strategy backtest
python examples/simple_backtest.py

# Compare strategies
python examples/compare_strategies.py
```

## 📚 Key Concepts to Learn

### Week 1: Backtesting Basics
- What is a backtest?
- How to interpret metrics (Sharpe ratio, drawdown, etc.)
- Why commissions matter
- Overfitting vs. robust strategies

### Week 2: Technical Indicators
- How RSI works (momentum oscillator)
- How moving averages work (trend following)
- When to use each indicator
- Combining multiple indicators

### Week 3: Strategy Development
- Entry signals vs. exit signals
- Position sizing
- Risk management (stop-loss, take-profit)
- Testing vs. live trading

### Week 4: Paper Trading
- Schwab API basics
- Order types (market, limit, stop)
- Managing positions
- Real-time monitoring

## ❓ FAQ

**Q: Can I start paper trading today?**
A: Not yet! You need to:
1. Learn how strategies work (Week 1-2)
2. Set up Schwab API (Week 3)
3. Build confidence with backtesting first

**Q: Which strategy should I use for real trading?**
A: None yet! These are learning examples. Real trading requires:
- Months of paper trading
- Consistent profitable results
- Proper risk management
- Emotional discipline

**Q: How do I know if a strategy is good?**
A: Look at these metrics:
- Sharpe Ratio > 1.0 (risk-adjusted return)
- Max Drawdown < 20% (risk management)
- Win Rate > 50% (consistency)
- Tested on multiple stocks/timeframes

**Q: Why did my strategy lose money in backtest?**
A: Common reasons:
- Market conditions changed
- Commissions eat profits on frequent trading
- Parameters not optimized for that stock
- Normal! Not every strategy works on every stock

**Q: How long until I can trade for real?**
A: Minimum 3-6 months of paper trading with real money discipline.

## 🎓 Recommended First Project

**"The RSI Explorer"** - A weekend project to learn the basics:

1. Test RSI strategy on 5 different stocks (AAPL, MSFT, GOOGL, TSLA, SPY)
2. Try 3 different threshold combinations (30/70, 25/75, 20/80)
3. Document which works best for each stock
4. Write a short report: "What I learned about RSI strategies"

This teaches you:
- How to run backtests
- How to interpret results
- Why one size doesn't fit all
- How to think like a quant trader

## 🚨 Important Warnings

⚠️ **Never trade real money until:**
- You have 3+ months of profitable paper trading
- You understand why your strategy works
- You have proper risk management
- You can afford to lose that money

⚠️ **Beware of overfitting:**
- Testing many parameters until one "works"
- Using the same data for testing and validation
- Assuming past performance = future results

⚠️ **Start small:**
- Paper trade first
- Then micro-lots ($100-$500)
- Scale up slowly as you gain confidence

## 📞 Getting Help

- Read the code comments - they explain everything
- Check NEXT_STEPS.md for detailed guidance
- Google error messages
- Read Schwab API documentation
- Join quant trading communities (Reddit: r/algotrading)

---

**Ready to start?**

```bash
# Let's go!
python examples/compare_strategies.py
```

Good luck! 🚀📈
