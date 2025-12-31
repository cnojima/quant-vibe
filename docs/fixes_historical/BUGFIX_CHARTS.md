# Bugfix: Charts Not Displaying (Empty Equity Curve)

## Issue

Admin UI charts (Equity Curve, P&L Distribution, Drawdown) were showing empty despite successful backtest execution.

## Root Cause

Two separate issues prevented equity curve data from reaching the charts:

### 1. Pandas Timestamp Not JSON Serializable

**Error**: `Object of type Timestamp is not JSON serializable`

When saving trades to the database, the `legs` JSON field contained pandas Timestamp objects that couldn't be serialized. This caused the entire `save_backtest_to_db()` function to fail before reaching the equity curve save step.

**Impact**: No data was saved to the database at all (trades, equity curve, or metadata).

### 2. Timestamp Serialization in API Response

Even after fixing the database save, the API endpoint `GET /backtests/{id}/results` was converting DataFrames to dictionaries without converting pandas Timestamp objects to ISO strings, causing JSON serialization errors when returning the response.

**Impact**: Data was in the database but couldn't be retrieved by the frontend.

## Fixes Applied

### Fix 1: Database Save - Convert Pandas Types Before Serialization

**File**: `src/quant_vibe/data/timescale_store.py`

**Method**: `save_backtest_trades()`

Added a recursive converter function to handle all pandas and NumPy types:

```python
def convert_to_serializable(obj):
    """Convert pandas/numpy types to JSON-serializable types."""
    if obj is None:
        return None
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if hasattr(obj, 'item'):  # NumPy scalar
        return obj.item()
    if isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item) for item in obj]
    return obj

# Convert all pandas/numpy types before JSON serialization
legs_json = convert_to_serializable(legs_json)
```

This ensures that when the `legs` field is serialized with `json.dumps()`, all nested pandas Timestamps are already converted to ISO strings.

### Fix 2: Equity Curve DataFrame - Handle Index vs Column

**File**: `src/quant_vibe/data/timescale_store.py`

**Method**: `save_backtest_equity_curve()`

Added logic to handle `timestamp` being either an index or a column:

```python
# Reset index to get timestamp as a column if it's the index
df = equity_df.copy()
if df.index.name == 'timestamp' or 'timestamp' not in df.columns:
    df = df.reset_index()
```

This ensures the timestamp is always available as a column for the database insert.

### Fix 3: API Response - Convert Timestamps and Handle NaN/Inf

**File**: `src/admin_ui/backend/api/backtests.py`

**Method**: `get_backtest_results()`

Added explicit conversion of timestamp fields and NaN/Inf values before returning JSON:

```python
# Convert timestamps to ISO strings for JSON serialization
import math

for trade in trades_data:
    # Parse legs JSON
    if 'legs' in trade and isinstance(trade['legs'], str):
        trade['legs'] = json.loads(trade['legs'])
    # Convert timestamp fields
    for field in ['entry_time', 'exit_time']:
        if field in trade and trade[field] is not None:
            if hasattr(trade[field], 'isoformat'):
                trade[field] = trade[field].isoformat()
    # Convert NaN/Inf to None for JSON serialization
    for key, value in list(trade.items()):
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                trade[key] = None

for point in equity_data:
    # Convert timestamp to ISO string
    if 'timestamp' in point and point['timestamp'] is not None:
        if hasattr(point['timestamp'], 'isoformat'):
            point['timestamp'] = point['timestamp'].isoformat()
    # Convert NaN/Inf to None for JSON serialization
    for key, value in list(point.items()):
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                point[key] = None
```

This ensures:
1. API returns properly formatted ISO timestamp strings
2. NaN values (common in first row of `returns` column) are converted to `null`
3. Infinity values are converted to `null`
4. All data is JSON-compliant

## Verification

### Before Fix

1. Backtest execution would show error:
   ```
   ❌ Error saving to database: Object of type Timestamp is not JSON serializable
   ```

2. Database would have 0 rows in equity curve table:
   ```sql
   SELECT COUNT(*) FROM backtest_equity_curve WHERE backtest_id = '...';
   -- Result: 0
   ```

3. Charts would be empty in Admin UI

4. If data was somehow in the database, API would return:
   ```json
   {
     "detail": "Out of range float values are not JSON compliant",
     "type": "ValueError"
   }
   ```

### After Fix

1. Backtest execution shows success:
   ```
   ✅ 796 equity curve points saved
   ```

2. Database has complete data:
   ```sql
   SELECT COUNT(*) FROM backtest_equity_curve WHERE backtest_id = 'bullish_vertical_put_20251230_173902';
   -- Result: 796
   ```

3. API returns properly formatted data:
   ```json
   {
     "equity_curve": [
       {
         "timestamp": "2025-12-01T14:30:00+00:00",
         "cash": 100000.0,
         "portfolio_value": 100000.0,
         ...
       }
     ]
   }
   ```

4. Charts display correctly in Admin UI

## Test Backtest

```bash
# Run test backtest
python scripts/run_backtest.py --strategy bullish_vertical_put --start-date 2025-12-01 --end-date 2025-12-02

# Verify database save
docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data -c \
  "SELECT COUNT(*) FROM backtest_equity_curve WHERE backtest_id = 'bullish_vertical_put_20251230_173902';"

# Result: 796 rows
```

## Related Issues Fixed

- Win rate displaying as 10000% → Fixed in previous commit (divide by 100)
- TypeError in history endpoint → Fixed in previous commit (safe sorting)
- 404 errors on backtest results → Fixed in previous commit (check database)

## Files Modified

1. `src/quant_vibe/data/timescale_store.py`
   - Added `convert_to_serializable()` function in `save_backtest_trades()`
   - Added index reset logic in `save_backtest_equity_curve()`

2. `src/admin_ui/backend/api/backtests.py`
   - Added timestamp conversion in `get_backtest_results()`

## Status

✅ **Fixed** - Charts now display properly:
- Equity Curve chart shows portfolio value over time
- P&L Distribution chart shows trade profit/loss distribution
- Drawdown chart shows drawdown over time
- Win Rate displays correctly as 100% instead of 10000%
- All backtest data persists to database successfully
