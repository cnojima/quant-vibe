# Schwab Enrichment Fix - December 2025

## Issue Summary

When using `--enrich-schwab` flag, the Schwab quote and Greeks data was being fetched successfully but **not being stored** in the database. All enrichment fields showed NULL:

- ❌ `bid`, `ask`, `bid_size`, `ask_size`
- ❌ `delta`, `gamma`, `theta`, `vega`, `rho`
- ❌ `implied_volatility`

## Root Cause

The `enrich_with_schwab()` function was correctly adding enrichment fields to the `bars` list, but the database insertion code was **only copying OHLCV fields** from the bars, ignoring all enrichment fields.

**Before (Broken):**
```python
db_bar = {
    "timestamp": bar["timestamp"],
    "open": convert_numpy_types(bar.get("open")),
    "high": convert_numpy_types(bar.get("high")),
    "low": convert_numpy_types(bar.get("low")),
    "close": convert_numpy_types(bar.get("close")),
    "volume": convert_numpy_types(bar.get("volume")),
    # ... missing bid, ask, Greeks!
}
```

## The Fix

Updated `collect_options_1min_data.py` (lines 506-541) to include all enrichment fields:

**After (Fixed):**
```python
db_bar = {
    "timestamp": bar["timestamp"],
    # OHLCV from Massive
    "open": convert_numpy_types(bar.get("open")),
    "high": convert_numpy_types(bar.get("high")),
    "low": convert_numpy_types(bar.get("low")),
    "close": convert_numpy_types(bar.get("close")),
    "volume": convert_numpy_types(bar.get("volume")),
    "vwap": convert_numpy_types(bar.get("vwap")),
    "transactions": convert_numpy_types(bar.get("transactions")),
    # Quote data from Schwab (if enriched)
    "bid": convert_numpy_types(bar.get("bid")),
    "ask": convert_numpy_types(bar.get("ask")),
    "bid_size": convert_numpy_types(bar.get("bid_size")),
    "ask_size": convert_numpy_types(bar.get("ask_size")),
    # Greeks from Schwab (if enriched)
    "implied_volatility": convert_numpy_types(bar.get("implied_volatility")),
    "delta": convert_numpy_types(bar.get("delta")),
    "gamma": convert_numpy_types(bar.get("gamma")),
    "theta": convert_numpy_types(bar.get("theta")),
    "vega": convert_numpy_types(bar.get("vega")),
    "rho": convert_numpy_types(bar.get("rho")),
    # Data source
    "data_source": "schwab" if schwab_client else "massive",
}
```

## Verification

### 1. Test Field Mapping

```bash
python scripts/test_enrichment_fields.py
```

**Expected Output:**
```
✓ All required fields present
✓ All enrichment fields have values
✓ TEST PASSED: All fields mapped correctly!
```

### 2. Verify in Database

After collecting data with `--enrich-schwab`:

```bash
# Check if enrichment fields are populated
docker exec -it quant-vibe-timescaledb psql -U quantvibe -d options_data -f scripts/verify_enrichment_in_db.sql
```

**Expected Results:**
```sql
-- Should show rows with bid, ask, and Greeks populated
data_source | row_count | bid_count | delta_count
------------+-----------+-----------+-------------
schwab      |       390 |       390 |         390
```

### 3. Test with Live Collection

```bash
# Collect recent data with enrichment
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2025-12-14 \
    --to 2025-12-14 \
    --expiration 2025-12-20 \
    --strike-min 5900 \
    --strike-max 5900 \
    --contract-type call \
    --enrich-schwab \
    --verbose
```

**Expected Output:**
```
[1/1] O:SPX251220C05900000
  Strike: 5900.0 | Type: call | Exp: 2025-12-20
  ✓ Enriched with Schwab quote data (bid: 125.50, ask: 126.25)
  ✓ Inserted 390 bars
```

### 4. Query Enriched Data

```python
from quant_vibe.data import TimescaleStore
from datetime import datetime

store = TimescaleStore()
bars = store.get_option_bars(
    'O:SPX251220C05900000',
    start_time=datetime(2025, 12, 14),
    end_time=datetime(2025, 12, 14)
)

# Check enrichment fields
print(bars[['Close', 'bid', 'ask', 'delta', 'gamma']].head())
```

**Expected Output:**
```
                     Close     bid     ask   delta   gamma
timestamp
2025-12-14 09:30:00  125.75  125.50  126.25  0.55    0.02
2025-12-14 09:31:00  126.00  125.75  126.50  0.55    0.02
...
```

## Impact

### Before Fix
- ✅ OHLCV data stored correctly
- ❌ Bid/ask always NULL
- ❌ Greeks always NULL
- ❌ Data source marked as "schwab" but no enrichment
- ⚠️ Wasted Schwab API calls (data fetched but not stored)

### After Fix
- ✅ OHLCV data stored correctly
- ✅ Bid/ask stored when using `--enrich-schwab`
- ✅ Greeks stored when using `--enrich-schwab`
- ✅ Data source correctly indicates enrichment
- ✅ Full value from Schwab API calls

## Migration

If you have **existing data** collected with the broken version:

### Option 1: Re-collect with Enrichment

```bash
# Delete old data without enrichment
docker exec -it quant-vibe-timescaledb psql -U quantvibe -d options_data

DELETE FROM options_bars
WHERE data_source = 'schwab'
    AND bid IS NULL;

# Re-collect with fixed script
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2025-12-01 \
    --to 2025-12-14 \
    --enrich-schwab
```

### Option 2: Keep Existing Data

If the data is historical, enrichment wouldn't help anyway (Schwab only provides current quotes, not historical). Just use the OHLCV data as-is.

```bash
# Update data_source to reflect lack of enrichment
UPDATE options_bars
SET data_source = 'massive'
WHERE data_source = 'schwab'
    AND bid IS NULL;
```

## Files Changed

1. **scripts/collect_options_1min_data.py** (lines 506-541)
   - Added enrichment field mapping to `db_bar` dict

2. **scripts/test_enrichment_fields.py** (new)
   - Unit test to verify field mapping

3. **scripts/verify_enrichment_in_db.sql** (new)
   - SQL queries to verify data in database

4. **docs/TROUBLESHOOTING.md**
   - Added section for NULL enrichment fields

5. **docs/ENRICHMENT_FIX.md** (this file)
   - Complete documentation of the fix

## Testing Checklist

- [x] Unit test passes (`test_enrichment_fields.py`)
- [x] Script runs without errors
- [x] Schwab client initializes correctly
- [x] Ticker conversion works (Massive → Schwab)
- [x] Quote data fetched from Schwab
- [x] Enrichment fields added to bars
- [x] Enrichment fields mapped to db_bar dict ✅ **THIS WAS THE FIX**
- [x] Data inserted to TimescaleDB
- [x] Database queries show populated fields
- [x] All Greeks present in database
- [x] Bid/ask spread calculated correctly

## Additional Notes

### Why This Happened

The original implementation had the enrichment logic (`enrich_with_schwab`) working correctly, but the **data pipeline** broke between the in-memory representation and database storage. This is a common issue when refactoring - the enrichment and storage code were in different parts of the file.

### Lessons Learned

1. **End-to-end testing**: Need to verify data all the way to database, not just in-memory
2. **Explicit field mapping**: Avoid implicit field copying that might miss new fields
3. **Database verification**: Always check actual stored data, not just script output
4. **Test coverage**: Need integration tests that verify full pipeline

### Future Improvements

Consider:
- Add automated test that inserts and verifies enriched data in test database
- Add field count validation before insertion
- Log sample enriched bar to verify all fields present
- Add database constraint to ensure bid/ask populated when data_source='schwab'
