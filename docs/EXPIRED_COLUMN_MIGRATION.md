# Expired Column Migration

## Summary

Replaces the `-9.0` sentinel value approach with a proper `expired` boolean column to mark expired contracts.

## Problem

Previously, expired contracts were marked by setting all Greeks (`delta`, `gamma`, `theta`, `vega`, `rho`, `implied_volatility`) to `-9.0`. This caused:

1. **Pydantic validation errors** - IV must be >= 0
2. **Data pollution** - Invalid values stored in database
3. **Query complexity** - Had to filter out -9.0 values
4. **Broken backtests** - Filtering excluded all contracts, not just expired ones

## Solution

Add a dedicated `expired` BOOLEAN column to properly flag expired contracts without corrupting the Greeks data.

## Changes Made

### 1. Database Schema (`scripts/migrations/007_add_expired_column.sql`)
- Added `expired` BOOLEAN column to `options_bars_1min`
- Added `expired` column to aggregated views (5min, 15min, 1hour, daily)
- Migrated existing `-9.0` values to `expired=true` and set greeks to `NULL`
- Created index on `expired` column for query performance

### 2. Pydantic Model (`src/quant_vibe/models/market_data.py`)
- Added `expired: bool = Field(default=False)` to `OptionsBar` model

### 3. Data Loading (`src/quant_vibe/data/timescale_store.py`)
- Updated `get_options_for_backtest()` to:
  - SELECT the `expired` column
  - Filter with `WHERE COALESCE(expired, false) = false`

### 4. Backfill Script (`scripts/backfill/backfill_stream_greeks.py`)
- Updated `mark_expired_contracts()` to:
  - Set `expired=true` instead of setting greeks to `-9.0`
  - Updated statistics query to check `expired=true` instead of `delta=-9`

### 5. Docker Configuration (`docker-compose.yml`)
- Changed optimization worker `LOG_LEVEL` from `INFO` to `WARNING` to reduce noise

## Migration Steps

### Step 1: Run the Migration

```bash
# Apply schema changes and migrate data
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data \
  -f scripts/migrations/007_add_expired_column.sql
```

This will:
- Add `expired` column to all options_bars tables
- Find all records where `implied_volatility = -9.0`
- Set `expired = true` for those records
- Set all Greeks to `NULL` (removing the -9.0 pollution)

### Step 2: Restart Services

```bash
# Restart optimization worker with new code
docker-compose restart optimization_worker

# Check logs
docker-compose logs -f optimization_worker
```

### Step 3: Verify Migration

```bash
# Check migration results
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -c "
SELECT
    'options_bars_1min' as table_name,
    COUNT(*) FILTER (WHERE expired = true) as expired_count,
    COUNT(*) FILTER (WHERE expired = false) as active_count,
    COUNT(*) FILTER (WHERE implied_volatility = -9.0) as still_has_negative_nine
FROM options_bars_1min;
"
```

Expected output:
- `expired_count`: ~100k+ (varies by dataset)
- `active_count`: Millions
- `still_has_negative_nine`: **0** (should be zero!)

### Step 4: Future Backfills

Going forward, use the updated script:

```bash
# Mark new expired contracts (uses expired column now)
python scripts/backfill/backfill_stream_greeks.py --mark-expired
```

## Benefits

✅ **Clean data** - No more invalid -9.0 values in Greeks columns
✅ **Valid Pydantic models** - All records pass validation
✅ **Better performance** - Indexed boolean lookups faster than numeric comparisons
✅ **Clearer intent** - `expired=true` is self-documenting
✅ **Proper backtests** - Can access all historical data, filtering only expired contracts

## Backwards Compatibility

- The migration automatically handles existing -9.0 values
- `COALESCE(expired, false)` handles NULL values in case column doesn't exist yet
- Old `sentinel_value` parameter kept in `mark_expired_contracts()` for compatibility (but ignored)

## Rollback

If needed, rollback with:

```sql
BEGIN;
ALTER TABLE options_bars_1min DROP COLUMN IF EXISTS expired;
ALTER TABLE options_bars_5min DROP COLUMN IF EXISTS expired;
ALTER TABLE options_bars_15min DROP COLUMN IF EXISTS expired;
ALTER TABLE options_bars_1hour DROP COLUMN IF EXISTS expired;
ALTER TABLE options_bars_daily DROP COLUMN IF EXISTS expired;
COMMIT;
```

**Note**: This will remove the `expired` flag but won't restore the -9.0 sentinel values.
