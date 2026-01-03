# SPXW Weekly Options Support - December 2025

## Issue Summary

When collecting SPXW (SPX weekly) options data with `--ticker SPXW`, the script reported "No contracts found" even though SPXW contracts exist in Massive API.

## Root Cause

**Massive API Ticker Structure:**
- SPXW weekly options have `underlying_ticker="SPX"` (not "SPXW")
- The "W" only appears in the option ticker itself: `O:SPXW251226C05900000`
- When script queried with `underlying_ticker="SPXW"`, it found nothing

**Example from database:**
```
underlying_ticker: SPX
option_ticker:     O:SPXW251226C05900000
expiration_date:   2025-12-26
```

## The Fix

Updated `get_options_contracts()` in `scripts/collect_options_1min_data.py` (lines 131-213):

### Before (Broken)
```python
def get_options_contracts(massive_client, underlying_ticker, ...):
    # Used underlying_ticker directly
    contracts_df = massive_client.list_options_contracts(
        underlying_ticker=underlying_ticker,  # SPXW -> 0 results
        ...
    )
```

### After (Fixed)
```python
def get_options_contracts(massive_client, underlying_ticker, ...):
    # Map SPXW -> SPX for API query
    api_underlying = underlying_ticker
    ticker_filter = None

    if underlying_ticker == "SPXW":
        api_underlying = "SPX"      # Query with SPX
        ticker_filter = "SPXW"      # Filter for O:SPXW... tickers
    elif underlying_ticker == "SPX":
        ticker_filter = "SPX"       # Filter out O:SPXW... tickers

    contracts_df = massive_client.list_options_contracts(
        underlying_ticker=api_underlying,
        ...
    )

    # Filter results by ticker pattern
    if ticker_filter == "SPXW":
        contracts_df = contracts_df[contracts_df['ticker'].str.contains(':SPXW', na=False)]
    elif ticker_filter == "SPX":
        contracts_df = contracts_df[~contracts_df['ticker'].str.contains(':SPXW', na=False)]
```

## Verification

### Test 1: SPXW Contract Discovery

```bash
python scripts/collect_options_1min_data.py \
    --ticker SPXW \
    --from 2025-12-26 \
    --to 2025-12-26 \
    --expiration 2025-12-26 \
    --strike-min 5900 \
    --strike-max 5900 \
    --contract-type call \
    --verbose
```

**Expected Output:**
```
Fetching options contracts for SPXW...
  Note: SPXW uses underlying_ticker='SPX', filtering for weekly contracts
  Filtered 1 -> 1 contracts (pattern: SPXW)
Found 1 contracts

[1/1] O:SPXW251226C05900000
  Strike: 5900 | Type: call | Exp: 2025-12-26
```

### Test 2: SPX Monthly (Verify Filtering)

```bash
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2026-01-16 \
    --to 2026-01-16 \
    --expiration 2026-01-16 \
    --strike-min 5900 \
    --strike-max 5900 \
    --contract-type call \
    --verbose
```

**Expected Output:**
```
Fetching options contracts for SPX...
  Filtered N -> M contracts (pattern: SPX)
Found M contracts

[1/M] O:SPX260116C05900000  # No W - monthly option
```

### Test 3: Check Database

```python
from quant_vibe.data import TimescaleStore

store = TimescaleStore()
conn = store.pool.getconn()
cursor = conn.cursor()

# Get SPXW expirations
cursor.execute('''
    SELECT DISTINCT expiration_date
    FROM options_bars
    WHERE option_ticker LIKE '%SPXW%'
    ORDER BY expiration_date
''')

expirations = [row[0] for row in cursor.fetchall()]
print(f"SPXW expirations: {expirations}")

store.pool.putconn(conn)
```

**Expected Output:**
```
SPXW expirations: [2025-12-22, 2025-12-23, 2025-12-24, 2025-12-26, ...]
```

## SPX vs SPXW Differences

### SPX (Monthly Standard Options)
- **Ticker format**: `O:SPX260116C05900000` (no W)
- **Expiration**: 3rd Friday of each month (monthly cycle)
- **Settlement**: AM settlement (based on opening prices)
- **Symbol**: SPX
- **Use case**: Long-term positions, monthly strategies

### SPXW (Weekly Options)
- **Ticker format**: `O:SPXW251226C05900000` (with W)
- **Expiration**: Multiple weekly expirations (Mon, Wed, Fri)
- **Settlement**: PM settlement (at market close)
- **Symbol**: SPXW
- **Use case**: Short-term trades, 0DTE strategies

### Massive API Representation

Both have `underlying_ticker="SPX"` in the database, differentiated only by ticker:
```
SPX Monthly:  underlying=SPX, ticker=O:SPX260116C05900000
SPXW Weekly:  underlying=SPX, ticker=O:SPXW251226C05900000
```

## Known Limitations

### 1. API Plan Restrictions

You may see this error even after the fix:
```
Error: Your plan doesn't include this data timeframe.
Please upgrade your plan at https://polygon.io/pricing
```

This means:
- ✅ Contract discovery works
- ❌ Your Massive/Polygon plan doesn't allow access to 1-minute historical data for that timeframe
- **Solution**: Check your plan at https://polygon.io/pricing or use different date ranges

### 2. Available Expirations

Not all dates have SPXW contracts. SPXW typically has:
- Weekly expirations (Fridays)
- Some mid-week expirations (Mon/Wed)
- No expirations on holidays

Check available expirations:
```sql
SELECT DISTINCT expiration_date
FROM options_bars
WHERE option_ticker LIKE '%SPXW%'
ORDER BY expiration_date;
```

## Impact

### Before Fix
- ❌ `--ticker SPXW` → "No contracts found"
- ✅ `--ticker SPX` → Found both monthly and weekly contracts (mixed)
- ⚠️ No way to filter for weekly contracts specifically

### After Fix
- ✅ `--ticker SPXW` → Finds weekly contracts only
- ✅ `--ticker SPX` → Finds monthly contracts only (filters out SPXW)
- ✅ Proper separation of monthly vs weekly options
- ✅ Clear logging shows filtering in action

## Files Changed

1. **scripts/collect_options_1min_data.py** (lines 131-213)
   - Added SPXW -> SPX mapping for API queries
   - Added ticker pattern filtering (`:SPXW` vs `:SPX`)
   - Enhanced logging to show filtering steps

2. **docs/SPXW_FIX.md** (this file)
   - Complete documentation of the fix
   - SPX vs SPXW comparison
   - Known limitations

## Usage Examples

### Collect SPXW 0DTE Data
```bash
# Collect today's SPXW 0DTE options
python scripts/collect_options_1min_data.py \
    --ticker SPXW \
    --from 2025-12-26 \
    --to 2025-12-26 \
    --expiration 2025-12-26 \
    --contract-type put \
    --strike-min 5800 \
    --strike-max 6000 \
    --enrich-schwab
```

### Collect SPX Monthly Data
```bash
# Collect monthly SPX options (no SPXW)
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2026-01-16 \
    --to 2026-01-16 \
    --expiration 2026-01-16 \
    --contract-type call \
    --strike-min 5900 \
    --strike-max 6100
```

### Query SPXW Data
```python
from quant_vibe.data import TimescaleStore
from datetime import datetime

store = TimescaleStore()

# Get SPXW 0DTE bars
bars = store.get_option_bars(
    'O:SPXW251226C05900000',
    start_time=datetime(2025, 12, 26, 9, 30),
    end_time=datetime(2025, 12, 26, 16, 0),
    timeframe='1min'
)

print(bars[['Open', 'High', 'Low', 'Close', 'Volume']].head())
```

## Additional Notes

### Why This Happened

The Massive/Polygon API uses a hierarchical ticker structure:
1. `underlying_ticker`: Base symbol (e.g., "SPX", "AAPL")
2. `ticker`: Full OCC option ticker (e.g., "O:SPXW251226C05900000")

For SPX index options, both monthly (SPX) and weekly (SPXW) share the same `underlying_ticker="SPX"`. The "W" suffix only appears in the option ticker itself, not in the underlying ticker field.

This design makes sense from the API's perspective (both are SPX derivatives), but requires client-side filtering to separate weekly from monthly options.

### Future Improvements

Consider:
- Add `--weekly` flag as an alternative to `--ticker SPXW`
- Support other weekly option symbols (e.g., RUT weekly = RUTW)
- Add expiration date lookup to show available SPXW expirations
- Cache contract lists to speed up repeated queries

### Related Issues

- [ENRICHMENT_FIX.md](ENRICHMENT_FIX.md) - Schwab enrichment fields fix
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and solutions
