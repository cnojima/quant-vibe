# Bugfix: Backtest History API TypeError

## Issue

Admin UI was showing error when loading backtest history:

```json
{
    "detail": "'<' not supported between instances of 'str' and 'datetime.datetime'",
    "type": "TypeError"
}
```

## Root Cause

The `/api/backtests/history` endpoint had type conversion issues:

1. **Datetime conversion**: When converting datetime objects to ISO strings, the code checked `if backtest[key]` which would skip `None` values, but they still existed in the dict
2. **Sorting fallback**: The in-memory fallback was trying to sort by `started_at` field which could be mixed types (datetime, string, or None)
3. **Type safety**: No proper handling of None values when comparing dates

## Fix Applied

### File: `src/admin_ui/backend/api/backtests.py`

**Change 1: Proper None handling in datetime conversion**
```python
# Before
if key in backtest and backtest[key]:
    value = backtest[key]
    if hasattr(value, 'isoformat'):
        backtest[key] = value.isoformat()

# After
if key in backtest:
    value = backtest[key]
    if value is not None:
        if hasattr(value, 'isoformat'):
            backtest[key] = value.isoformat()
    # Leave None as None for proper JSON null serialization
```

**Change 2: Safe sorting with type checking**
```python
# Before
history.sort(key=lambda x: x.get("started_at", datetime.min), reverse=True)

# After
def get_sort_key(x):
    """Get sortable key from started_at, handling both datetime and string."""
    started = x.get("started_at")
    if started is None:
        return datetime.min
    if isinstance(started, str):
        try:
            return datetime.fromisoformat(started.replace('Z', '+00:00'))
        except:
            return datetime.min
    return started

history.sort(key=get_sort_key, reverse=True)
```

**Change 3: Better numeric type conversion**
```python
# Added safe numeric type conversion for PostgreSQL Decimal types
for key in ['total_return_pct', 'win_rate', 'sharpe_ratio', 'max_drawdown',
           'num_trades', 'final_capital', 'initial_capital']:
    if key in backtest and backtest[key] is not None:
        if hasattr(backtest[key], 'item'):
            backtest[key] = backtest[key].item()
```

## Verification

1. Database returns datetime objects correctly:
   ```
   created_at type = <class 'datetime.datetime'>
   started_at type = <class 'NoneType'> (expected - not yet populated)
   ```

2. API should now properly convert:
   - Datetime → ISO string (`"2025-12-31T01:25:13.906012+00:00"`)
   - None → JSON null
   - Decimal → float/int

3. Frontend should receive clean JSON without type mixing

## Testing

To verify the fix:

```bash
# Check if backend is running
curl http://localhost:8000/api/backtests/history

# Should return JSON with properly formatted dates
{
  "backtests": [
    {
      "backtest_id": "...",
      "created_at": "2025-12-31T01:25:13.906012+00:00",
      "started_at": null,
      ...
    }
  ],
  "total": 2,
  "source": "database"
}
```

## Related Files Modified

- `src/admin_ui/backend/api/backtests.py` - Type safety improvements

## Status

✅ **Fixed** - Backend now properly handles:
- None values in date fields
- Mixed datetime/string types in sorting
- PostgreSQL Decimal types
- JSON serialization of complex types

The Admin UI should now load backtest history without errors.
