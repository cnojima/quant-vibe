# Schwab API Integration Guide

## ✅ Integration Status: WORKING!

Your Schwab API integration is **live and functional** using direct bearer token authentication.

### What's Working
- ✅ Real-time quotes (`get_quote()`)
- ✅ Multiple quotes (`get_quotes()`)
- ✅ Historical price data (`get_price_history()`)
- ⚠️ Account info (needs valid account number)
- ⚠️ Order placement (ready, but TEST CAREFULLY!)

---

## 🚀 Quick Start

### Test the Integration
```bash
# Run the test script
python src/quant_vibe/data/schwab_client.py
```

**Result:** Should fetch AAPL quote and price history successfully!

### Use in Your Code
```python
from quant_vibe.data.schwab_client import SchwabClient

# Initialize client (uses bearer token from .env)
client = SchwabClient()

# Get real-time quote
quote = client.get_quote("AAPL")
print(f"AAPL: ${quote['AAPL']['quote']['lastPrice']}")

# Get historical data
data = client.get_price_history("AAPL", period_type="month", period=1)
print(f"Fetched {len(data)} days of data")

# Save to cache for backtesting
from quant_vibe.data import DataStore
store = DataStore()
store.save("AAPL", data)
```

---

## 📋 Two Integration Approaches

### Approach 1: Bearer Token (Current - `schwab_client.py`)

**Best for:** Quick prototyping, learning, testing strategies

**Pros:**
- ✅ Simple setup (just paste token)
- ✅ No OAuth flow needed
- ✅ Works with any Python version
- ✅ Good for development/testing

**Cons:**
- ❌ Token expires (must refresh manually)
- ❌ Less secure (token in .env)
- ❌ No automatic token management

**Setup:**
```bash
# Already configured! Bearer token in .env:
# SCHWAB_BEARER_TOKEN=I0.b2F1dGgyLmJkYy5zY2h3YWIuY29t...
```

**Usage:**
```python
from quant_vibe.data.schwab_client import SchwabClient
client = SchwabClient()
quote = client.get_quote("AAPL")
```

---

### Approach 2: OAuth2 Library (New - `schwab_py_client.py`)

**Best for:** Production, automated trading, long-term projects

**Pros:**
- ✅ Automatic token refresh (no interruptions!)
- ✅ Official library (better support)
- ✅ More secure token storage
- ✅ Production-ready
- ✅ Supports websockets/streaming

**Cons:**
- ❌ Requires Python 3.10+ (you have 3.14 ✅)
- ❌ More complex setup (OAuth flow)
- ❌ Needs API credentials from Schwab

**Setup:**

1. **Get API Credentials** (one-time)
   - Go to https://developer.schwab.com/
   - Create a new app
   - Note these values:
     * API Key (Consumer Key)
     * App Secret (Consumer Secret)
     * Callback URL (e.g., `https://127.0.0.1:8182/`)

2. **Add to .env:**
   ```bash
   # schwab-py OAuth2 credentials
   SCHWAB_API_KEY=your_api_key_here
   SCHWAB_API_SECRET=your_app_secret_here
   SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
   SCHWAB_TOKEN_PATH=./tokens/schwab_token.json
   SCHWAB_ACCOUNT_NUMBER=your_account_number  # optional
   ```

3. **First-time authentication:**
   ```bash
   # Run the client - browser will open for OAuth
   python src/quant_vibe/data/schwab_py_client.py
   
   # Steps:
   # 1. Browser opens automatically
   # 2. Log in to Schwab
   # 3. Authorize the app
   # 4. Redirected to callback URL
   # 5. Copy the FULL URL and paste when prompted
   # 6. Token saved to ./tokens/schwab_token.json
   ```

4. **Future runs** - no browser needed!
   ```python
   from quant_vibe.data.schwab_py_client import SchwabPyClient
   from schwab.client import Client
   
   # Initialize (uses cached token)
   client = SchwabPyClient()
   
   # Get quote
   quote = client.get_quote("AAPL")
   
   # Get price history
   history = client.get_price_history(
       "AAPL",
       period_type=Client.PriceHistory.PeriodType.YEAR,
       period=Client.PriceHistory.Period.ONE_YEAR,
       frequency_type=Client.PriceHistory.FrequencyType.DAILY,
       frequency=Client.PriceHistory.Frequency.DAILY
   )
   ```

---

## 🔀 Compare Both Approaches

Run the comparison script:
```bash
python scripts/compare_schwab_apis.py
```

This will test both approaches and show you:
- Which one is configured
- Performance comparison
- Recommendations based on your use case

### Quick Comparison Table

| Feature | Bearer Token | OAuth2 Library |
|---------|-------------|----------------|
| **Python Version** | Any | 3.10+ ✅ |
| **Setup Complexity** | Simple ⭐ | Moderate |
| **Token Refresh** | Manual | Automatic ⭐ |
| **Security** | Good | Better ⭐ |
| **Streaming Support** | No | Yes ⭐ |
| **Production Ready** | Good | Better ⭐ |
| **Best For** | Learning/Testing | Production |

### Migration Path

**Current State:** You have both options available! Python 3.14.2 ✅

**Recommended approach:**

1. **Start with Bearer Token** (already working!)
   - Fast prototyping
   - Test your strategies
   - Learn the API

2. **Switch to OAuth2** when ready
   - Get API credentials from developer.schwab.com
   - Run first-time OAuth flow
   - Enjoy automatic token refresh!

3. **Keep both** for flexibility
   - Bearer token for quick testing
   - OAuth2 for production backtesting

---

## 📝 Usage Examples

---

## 🔑 Authentication Setup

### Current Setup (Bearer Token)

Your `.env` file has:
```bash
SCHWAB_BEARER_TOKEN=I0.b2F1dGgyLmJkYy5zY2h3YWIuY29t.o8QDMlRwgfWMeeZ72huUd83hJaA0dorJ_HbRsPuXraQ@
SCHWAB_ACCOUNT_NUMBER=your_account_number_here  # Update this!
```

### Where to Get Credentials

1. **Schwab Developer Portal**: https://developer.schwab.com/
2. **Create an App**
3. **Generate Bearer Token** (what you have)
4. **Get Account Number** from Schwab/ThinkorSwim

### Token Expiration

⚠️ **Bearer tokens expire!** You'll need to regenerate periodically.

**Signs your token expired:**
- 401 Unauthorized errors
- Quote fetching fails

**Solution:** Generate new token from Schwab portal and update `.env`

---

## 📊 Available Methods

### Market Data

```python
# Single quote
quote = client.get_quote("AAPL")
last_price = quote['AAPL']['quote']['lastPrice']

# Multiple quotes
quotes = client.get_quotes(["AAPL", "MSFT", "GOOGL"])

# Historical data - various periods
data = client.get_price_history("AAPL", period_type="year", period=1)
data = client.get_price_history("AAPL", period_type="month", period=3)
data = client.get_price_history("AAPL", period_type="day", period=5)

# Historical data - specific dates
from datetime import datetime
data = client.get_price_history(
    "AAPL",
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31)
)

# Intraday data (minute bars)
data = client.get_price_history(
    "AAPL",
    period_type="day",
    period=1,
    frequency_type="minute",
    frequency=5  # 5-minute bars
)
```

### Account Information

```python
# Get account info (requires valid SCHWAB_ACCOUNT_NUMBER)
account = client.get_account_info()

# Get current positions
positions = client.get_positions()
for pos in positions:
    symbol = pos['instrument']['symbol']
    quantity = pos['longQuantity']
    print(f"{symbol}: {quantity} shares")

# Get account balance
balance = client.get_account_balance()
print(f"Account Value: ${balance['liquidationValue']:,.2f}")
print(f"Buying Power: ${balance['buyingPower']:,.2f}")
```

### Trading (USE WITH CAUTION!)

```python
# Market buy order
order = client.place_order(
    symbol="AAPL",
    quantity=10,
    instruction="BUY",
    order_type="MARKET"
)

# Limit sell order
order = client.place_order(
    symbol="AAPL",
    quantity=10,
    instruction="SELL",
    order_type="LIMIT",
    price=150.00
)

# Get recent orders
orders = client.get_orders(max_results=10)
```

---

## 🎯 Integration with Backtesting

### Replace yfinance with Live Schwab Data

```python
from quant_vibe.data import DataStore
from quant_vibe.data.schwab_client import SchwabClient

# Fetch from Schwab instead of yfinance
client = SchwabClient()
store = DataStore()

# Get 2 years of data
data = client.get_price_history("AAPL", period_type="year", period=2)

# Cache it
store.save("AAPL", data)

# Now use in backtesting (same as before!)
from quant_vibe.strategies import SMACrossoverStrategy
from quant_vibe.backtesting import BacktestEngine

strategy = SMACrossoverStrategy(fast_period=50, slow_period=200)
engine = BacktestEngine(initial_capital=100000.0)
portfolio = engine.run(strategy, data)
```

### Script to Fetch All Schwab Data

Create `scripts/fetch_schwab_data.py`:
```python
from quant_vibe.data import DataStore
from quant_vibe.data.schwab_client import SchwabClient

client = SchwabClient()
store = DataStore()

symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "SPY"]

for symbol in symbols:
    print(f"Fetching {symbol}...")
    data = client.get_price_history(symbol, period_type="year", period=2)
    store.save(symbol, data)
    print(f"  ✓ Saved {len(data)} days")
```

---

## ⚠️ Important Warnings

### Paper Trading NOT Supported

**Critical:** Schwab's API does **NOT support paper trading**!
- schwab-py documentation explicitly states this
- Your orders will be REAL
- This uses your REAL account

**Solutions:**
1. **Start with TINY positions** ($50-100 max)
2. **Use limit orders** to control prices  
3. **Test thoroughly with backtesting first**
4. **Consider Interactive Brokers** (has paper trading API)

### Rate Limits

Schwab has API rate limits:
- ~120 requests/minute for market data
- ~60 requests/minute for trading

**Best practices:**
- Cache data locally
- Don't fetch same quote repeatedly
- Use `get_quotes()` for multiple symbols

### Token Security

⚠️ **Never commit .env file to git!**

Your `.gitignore` already excludes it, but double-check:
```bash
# Verify .env is git-ignored
git status  # Should NOT show .env
```

---

## 📈 Next Steps

### Today (15 minutes)
1. ✅ API integration working
2. Update `SCHWAB_ACCOUNT_NUMBER` in `.env` (if you have it)
3. Fetch data for your favorite stocks:
```bash
python -c "
from quant_vibe.data.schwab_client import SchwabClient
from quant_vibe.data import DataStore
client = SchwabClient()
store = DataStore()
data = client.get_price_history('SPY', period_type='year', period=2)
store.save('SPY', data)
print(f'Fetched {len(data)} days of SPY data!')
"
```

### This Weekend (2-3 hours)
1. Create `scripts/fetch_schwab_data.py` to fetch multiple stocks
2. Replace yfinance with Schwab in your workflows
3. Test backtesting with Schwab data
4. Compare Schwab vs yfinance data quality

### Next Week
1. Build real-time quote monitor
2. Create price alert system
3. Develop paper trading simulator (custom, since Schwab doesn't have one)
4. Start building towards live trading (very carefully!)

---

## 🔧 Troubleshooting

### "401 Unauthorized"
- Bearer token expired - regenerate from Schwab portal
- Wrong token format - check `.env` format
- Account number incorrect

### "No data returned"
- Check symbol is valid (use uppercase: "AAPL" not "aapl")
- Verify market hours (extended hours may not have data)
- Check date ranges are valid

### Import errors
```python
# Make sure PYTHONPATH is set
export PYTHONPATH="${PYTHONPATH}:${PWD}/src"

# Or use activate.sh
source activate.sh
```

---

## 📚 Resources

- **Schwab API Docs**: https://developer.schwab.com/products/trader-api--individual/details/documentation
- **schwab-py GitHub**: https://github.com/alexgolec/schwab-py
- **schwab-py Docs**: https://schwab-py.readthedocs.io/
- **Discord Community**: https://discord.gg/BEr6y6Xqyv

---

## ✅ Success!

Your Schwab integration is **live and working**! You can now:
- ✅ Fetch real-time quotes
- ✅ Get historical data from Schwab
- ✅ Use Schwab data for backtesting
- ✅ Access account info (once account number is set)
- ⚠️ Place orders (BE CAREFUL - these are REAL!)

**Recommendation:** Use this for data fetching and backtesting now. For live trading, practice extensively with backtesting first, then start with TINY positions.

Good luck! 🚀📈
