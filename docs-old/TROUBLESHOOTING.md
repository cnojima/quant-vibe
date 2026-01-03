# Troubleshooting Guide

## Common Issues and Solutions

### 1. Schwab enrichment fields showing NULL in database

**Symptoms:**
- Using `--enrich-schwab` flag
- Script shows "✓ Enriched with Schwab quote data"
- Database shows NULL for: bid, ask, bid_size, ask_size, delta, gamma, theta, vega, rho, implied_volatility

**Cause:** ✅ **FIXED** - The enriched fields weren't being mapped to the database insertion dict.

**Solution:** Update to latest version of `collect_options_1min_data.py`. The script now properly includes all enrichment fields:

```python
# Quote data from Schwab (if enriched)
"bid": convert_numpy_types(bar.get("bid")),
"ask": convert_numpy_types(bar.get("ask")),
# ... etc
```

**Verify the fix:**
```bash
python scripts/test_enrichment_fields.py
# Should show: "✓ TEST PASSED: All fields mapped correctly!"
```

---

### 2. Database Error: `schema "np" does not exist`

**Error Message:**
```
✗ Database error: schema "np" does not exist
LINE 10: ...1:00'::timestamp, 'O:SPXW251226P02000000', 'SPX', np.float64...
```

**Cause:** Numpy data types (like `np.float64`, `np.int64`) from pandas DataFrames are being passed directly to PostgreSQL, which doesn't understand them.

**Solution:** ✅ **FIXED** - The data collection script now converts all numpy types to Python native types before database insertion.

The script includes a `convert_numpy_types()` helper function that converts:
- `np.float64/np.float32` → `float`
- `np.int64/np.int32` → `int`
- `np.bool_` → `bool`
- `None` → `None` (preserved)

**Verification:**
```bash
python scripts/collect_options_1min_data.py --ticker SPX
# Should now insert data without errors
```

---

### 2. ModuleNotFoundError: No module named 'schwab'

**Error Message:**
```
ModuleNotFoundError: No module named 'schwab'
```

**Cause:** The `schwab-py` library is in the optional `[schwab]` dependency group and not installed.

**Solutions:**

**Option A:** Install Schwab dependencies
```bash
pip install -e ".[schwab]"
```

**Option B:** Run without Schwab enrichment (uses only Massive data)
```bash
# Don't use the --enrich-schwab flag
python scripts/collect_options_1min_data.py --ticker SPX
```

The script will automatically skip Schwab enrichment if the library is not available.

---

### 3. Connection Error: Cannot connect to TimescaleDB

**Error Message:**
```
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Cause:** TimescaleDB container is not running.

**Solution:**
```bash
# Start TimescaleDB
docker-compose up -d

# Verify it's running
docker ps | grep timescaledb

# Check logs if issues persist
docker logs quant-vibe-timescaledb
```

**Verify connection:**
```bash
docker exec -it quant-vibe-timescaledb psql -U quantvibe -d options_data
```

---

### 4. numba/pandas-ta fails to install on Python 3.14

**Error Message:**
```
RuntimeError: Cannot install on Python version 3.14.2; only versions >=3.10,<3.14 are supported.
```

**Cause:** `pandas-ta` depends on `numba`, which doesn't support Python 3.14 yet.

**Solution:** ✅ **FIXED** - `pandas-ta` has been removed from optional dependencies.

For technical indicators, use pandas built-in functions:

```python
import pandas as pd

# Simple Moving Average
df['SMA_20'] = df['Close'].rolling(window=20).mean()

# Exponential Moving Average
df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()

# Relative Strength Index (RSI)
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

df['RSI_14'] = calculate_rsi(df['Close'])

# Bollinger Bands
df['BB_Middle'] = df['Close'].rolling(window=20).mean()
df['BB_Std'] = df['Close'].rolling(window=20).std()
df['BB_Upper'] = df['BB_Middle'] + (df['BB_Std'] * 2)
df['BB_Lower'] = df['BB_Middle'] - (df['BB_Std'] * 2)

# MACD
exp1 = df['Close'].ewm(span=12, adjust=False).mean()
exp2 = df['Close'].ewm(span=26, adjust=False).mean()
df['MACD'] = exp1 - exp2
df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
```

**Alternative:** If you need `pandas-ta`, downgrade to Python 3.13:
```bash
# Create new venv with Python 3.13
python3.13 -m venv venv313
source venv313/bin/activate
pip install -e ".[all]"
```

---

### 5. pip install -e . fails with build backend error

**Error Message:**
```
Cannot import 'setuptools.build_backend'
```

**Cause:** Python 3.14 compatibility issue with older setuptools backend name.

**Solution:** ✅ **FIXED** - `pyproject.toml` now uses `setuptools.build_meta`

If still encountering issues:
```bash
# Upgrade build tools
pip install --upgrade setuptools pip wheel

# Then reinstall
pip install -e .
```

---

### 5. SPXW (weekly options) showing "No contracts found"

**Error Message:**
```
Fetching options contracts for SPXW...
Found 0 contracts
No contracts found. Exiting.
```

**Cause:** ✅ **FIXED** - SPXW contracts have `underlying_ticker="SPX"` in Massive API, but the script was querying with `underlying_ticker="SPXW"`.

**Solution:** Update to latest version of `collect_options_1min_data.py`. The script now:
- Maps `--ticker SPXW` → `underlying_ticker="SPX"` for API query
- Filters results to only include tickers matching `O:SPXW...` pattern
- Separates SPX monthly options from SPXW weekly options

**Example:**
```bash
# Collect SPXW weekly options (PM settlement)
python scripts/collect_options_1min_data.py \
    --ticker SPXW \
    --from 2025-12-26 \
    --to 2025-12-26 \
    --expiration 2025-12-26 \
    --contract-type call
```

**Output should show:**
```
Fetching options contracts for SPXW...
  Note: SPXW uses underlying_ticker='SPX', filtering for weekly contracts
  Filtered 1 -> 1 contracts (pattern: SPXW)
Found 1 contracts
[1/1] O:SPXW251226C05900000
```

**See also:** [docs/SPXW_FIX.md](SPXW_FIX.md) for complete details on SPX vs SPXW.

---

### 6. No data collected / Empty results

**Possible Causes:**

**A) API rate limiting**
```bash
# Add delays between requests
python scripts/collect_options_1min_data.py --ticker SPX --verbose
# Check for rate limit errors in output
```

**B) No contracts match filters**
```bash
# Check what contracts are available
python -c "
from quant_vibe.data import MassiveClient
from datetime import datetime, timedelta

client = MassiveClient()
today = datetime.now().strftime('%Y-%m-%d')
future = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

contracts = client.list_options_contracts(
    underlying_ticker='SPX',
    expiration_date_gte=today,
    expiration_date_lte=future,
    limit=5
)
print(f'Found {len(contracts)} contracts')
print(contracts.head() if not contracts.empty else 'No contracts')
"
```

**C) Date range has no data**
```bash
# Check if data exists for the date range
# Massive may not have historical 1-minute data for all dates
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2025-12-01 \
    --to 2025-12-14 \
    --verbose
```

---

### 6. Database fills up quickly

**Cause:** 1-minute data for thousands of options contracts accumulates rapidly.

**Solutions:**

**A) Enable compression** (automatic after 7 days)
```sql
-- Check compression status
SELECT
    hypertable_name,
    total_chunks,
    number_compressed_chunks
FROM timescaledb_information.compression_settings;
```

**B) Add retention policy**
```sql
-- Keep only 90 days of raw 1-minute data
SELECT add_retention_policy('options_bars', INTERVAL '90 days');
```

**C) Use higher timeframes**
```python
# Query 5-minute bars instead of 1-minute (uses continuous aggregates)
from quant_vibe.data import TimescaleStore

store = TimescaleStore()
bars = store.get_option_bars(
    'O:SPX251220C04500000',
    timeframe='5min'  # or '15min', '1hour', 'daily'
)
```

---

### 7. Slow queries

**Cause:** Missing indexes or querying without proper filters.

**Solutions:**

**Use proper filtering:**
```python
# SLOW - no underlying ticker filter
bars = store.get_option_bars('O:SPX251220C04500000')

# FAST - uses indexes
from datetime import datetime, timedelta
bars = store.get_option_bars(
    'O:SPX251220C04500000',
    start_time=datetime.now() - timedelta(days=30),
    end_time=datetime.now()
)
```

**Use continuous aggregates for higher timeframes:**
```python
# Instead of querying 1-minute and aggregating in Python
bars = store.get_option_bars(ticker, timeframe='5min')
# This uses pre-computed aggregates
```

**Check query plan:**
```sql
EXPLAIN ANALYZE
SELECT * FROM options_bars
WHERE option_ticker = 'O:SPX251220C04500000'
  AND timestamp >= '2025-01-01'
  AND timestamp <= '2025-12-31';
```

---

### 8. Import errors with optional dependencies

**Error Message:**
```
ImportError: cannot import name 'X' from 'quant_vibe'
```

**Cause:** Trying to use features that require optional dependencies.

**Solutions:**

**Check what's installed:**
```bash
pip list | grep -E "backtrader|pandas-ta|schwab|yfinance"
```

**Install needed dependencies:**
```bash
# For backtesting
pip install -e ".[backtest]"

# For indicators
pip install -e ".[indicators]"

# For everything
pip install -e ".[all]"
```

---

## Getting Help

If you encounter an issue not listed here:

1. **Check logs:**
   ```bash
   # TimescaleDB logs
   docker logs quant-vibe-timescaledb

   # Run script with verbose mode
   python scripts/collect_options_1min_data.py --ticker SPX --verbose
   ```

2. **Verify setup:**
   ```bash
   # Check Python version
   python --version  # Should be 3.9+

   # Check package installation
   pip show quant-vibe

   # Test core imports
   python -c "from quant_vibe.data import MassiveClient, TimescaleStore; print('OK')"
   ```

3. **Database diagnostics:**
   ```python
   from quant_vibe.data import TimescaleStore

   store = TimescaleStore()
   stats = store.get_database_stats()
   for key, value in stats.items():
       print(f"{key}: {value}")
   ```

4. **Check documentation:**
   - [TimescaleDB Setup](TIMESCALE_SETUP.md)
   - [Installation Guide](../INSTALLATION.md)
   - [README](../README.md)
