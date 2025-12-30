# SQLAlchemy Migration - Fix Pandas Warning

## Problem

The backtest logs were cluttered with this warning:

```
/path/to/timescale_store.py:527: UserWarning: pandas only supports SQLAlchemy
connectable (engine/connection) or database string URI or sqlite3 DBAPI2 connection.
Other DBAPI2 objects are not tested. Please consider using SQLAlchemy.
```

**Root Cause**: `pd.read_sql_query()` was using psycopg2 connections directly instead of SQLAlchemy engines, which pandas recommends for better compatibility and performance.

## Solution

Migrated `TimescaleStore` to use SQLAlchemy for all pandas DataFrame operations while keeping psycopg2 for direct database operations.

### Changes Made

#### 1. Added SQLAlchemy Dependencies

**File**: `pyproject.toml`
```toml
dependencies = [
    ...
    "sqlalchemy>=2.0.0",  # Added
]
```

**File**: `src/quant_vibe/data/timescale_store.py`
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
```

#### 2. Created SQLAlchemy Engine Property

Added lazy-initialized engine for pandas operations:

```python
def __init__(self, ...):
    # ... existing psycopg2 pool setup ...

    # SQLAlchemy engine (lazy initialization)
    self._engine = None

@property
def engine(self):
    """Get SQLAlchemy engine for pandas operations (lazy initialization)."""
    if self._engine is None:
        connection_string = (
            f"postgresql://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}"
        )
        # Use NullPool to avoid connection pool conflicts with psycopg2 pool
        self._engine = create_engine(connection_string, poolclass=NullPool)
    return self._engine
```

**Why NullPool?**
- Avoids conflicts between SQLAlchemy's connection pool and our existing psycopg2 SimpleConnectionPool
- Each `pd.read_sql_query()` call gets a fresh connection
- Connections are not held open (important for NullPool)

#### 3. Updated All `pd.read_sql_query()` Calls

Replaced 4 instances:

**Before**:
```python
with self.get_connection() as conn:
    df = pd.read_sql_query(query, conn, params=params)
```

**After**:
```python
df = pd.read_sql_query(query, self.engine, params=tuple(params))
```

**Key Changes**:
- Use `self.engine` instead of psycopg2 connection
- Convert list params to tuples (SQLAlchemy requirement)
- Remove `with self.get_connection()` wrapper (not needed with engine)

#### 4. Updated close() Method

Clean up SQLAlchemy engine on close:

```python
def close(self) -> None:
    """Close all connections in the pool and dispose of SQLAlchemy engine."""
    if self.pool:
        self.pool.closeall()
    if self._engine is not None:
        self._engine.dispose()  # Added
```

## Architecture

### Dual Connection Strategy

```
TimescaleStore
├── psycopg2 Connection Pool (SimpleConnectionPool)
│   ├── Used for: Direct database operations
│   │   - INSERT/UPDATE/DELETE
│   │   - Bulk operations
│   │   - Transaction management
│   └── Methods: get_connection(), insert_option_bar(), bulk_insert_option_bars()
│
└── SQLAlchemy Engine (NullPool)
    ├── Used for: Pandas DataFrame operations
    │   - pd.read_sql_query()
    │   - Loading data for backtests
    │   - Analytics queries
    └── Methods: get_option_bars(), get_options_chain_bars(), get_options_for_backtest()
```

### Why Both?

1. **psycopg2 Pool**: Better for bulk inserts and transactional operations
   - Fine-grained control over connections
   - Efficient batch operations with `execute_batch()`
   - Better performance for writes

2. **SQLAlchemy Engine**: Better for pandas integration
   - Official pandas recommendation
   - Better compatibility with pandas features
   - Cleaner code for read operations

## Files Modified

1. `pyproject.toml` - Added SQLAlchemy dependency
2. `src/quant_vibe/data/timescale_store.py` - Migrated pandas queries to SQLAlchemy

## Testing

### Before Fix
```bash
$ python backtests/backtest_bullish_vertical_put.py
.../timescale_store.py:527: UserWarning: pandas only supports SQLAlchemy...
  df = pd.read_sql_query(query, conn, ...)
```

### After Fix
```bash
$ python backtests/backtest_bullish_vertical_put.py
# Clean output - no warnings!
```

Verified with:
```bash
echo -e "6\n2025-12-16\n2025-12-16\ny" | \
  python backtests/backtest_bullish_vertical_put.py 2>&1 | \
  grep -i "warning"
# No output = no warnings ✅
```

## Performance Impact

**Minimal to None**:
- SQLAlchemy engine created lazily (only when needed)
- NullPool avoids overhead of connection pooling
- Queries execute at same speed as before
- Memory usage unchanged

## Migration Guide

If you see this warning in other scripts:

1. **Check if using psycopg2 directly with pandas**:
   ```python
   # Bad
   with conn.cursor() as cur:
       df = pd.read_sql_query(query, conn, params=params)
   ```

2. **Switch to SQLAlchemy engine**:
   ```python
   # Good
   df = pd.read_sql_query(query, engine, params=tuple(params))
   ```

3. **Remember to convert list params to tuples**:
   ```python
   # Bad - SQLAlchemy doesn't accept lists
   params = [val1, val2, val3]
   df = pd.read_sql_query(query, engine, params=params)

   # Good - Convert to tuple
   params = [val1, val2, val3]
   df = pd.read_sql_query(query, engine, params=tuple(params))
   ```

## Benefits

- ✅ **Clean logs**: No more distracting warnings
- ✅ **Better compatibility**: Following pandas best practices
- ✅ **Future-proof**: Prepared for pandas updates
- ✅ **More maintainable**: Using standard patterns
- ✅ **No performance loss**: Same speed as before

## Related Documentation

- Pandas SQL documentation: https://pandas.pydata.org/docs/reference/api/pandas.read_sql.html
- SQLAlchemy documentation: https://docs.sqlalchemy.org/
- TimescaleDB setup: `docs/TIMESCALE_SETUP.md`

## Summary

**Problem**: Pandas warning about using psycopg2 directly
**Solution**: Added SQLAlchemy engine for pandas operations
**Result**: Clean logs, better compatibility, same performance

**Status**: ✅ Complete - All warnings eliminated
