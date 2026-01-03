# UTC Timezone Verification Report

**Date**: 2026-01-02
**Status**: ✅ **VERIFIED - All database timestamp columns use TIMESTAMPTZ (UTC)**

## Executive Summary

All timestamp columns in the TimescaleDB schema correctly use `TIMESTAMPTZ` (timezone-aware timestamps stored as UTC). There are **zero** instances of naive `TIMESTAMP` (without timezone) columns.

PostgreSQL's `TIMESTAMPTZ` type:
- Stores all values internally as UTC
- Automatically converts input timestamps to UTC
- Returns timestamps in the client's timezone (can be set to UTC)
- Ensures consistent timezone handling across all operations

## Database Schema Analysis

### Market Data Tables

#### 1. `options_bars` (Hypertable)
```sql
timestamp TIMESTAMPTZ NOT NULL,  -- Primary timestamp ✅
created_at TIMESTAMPTZ DEFAULT NOW(),  -- Metadata ✅
```

**Continuous Aggregates** (all use TIMESTAMPTZ):
- `options_bars_5min` → `bucket` column (from `time_bucket()`) ✅
- `options_bars_15min` → `bucket` column ✅
- `options_bars_1hour` → `bucket` column ✅
- `options_bars_daily` → `bucket` column ✅

**Verification**: Line 25, 61 in `scripts/init_timescale.sql`

#### 2. `underlying_bars` (Hypertable)
```sql
timestamp TIMESTAMPTZ NOT NULL,  -- Primary timestamp ✅
created_at TIMESTAMPTZ DEFAULT NOW(),  -- Metadata ✅
```

**Continuous Aggregates** (all use TIMESTAMPTZ):
- `underlying_bars_5min` → `bucket` column ✅
- `underlying_bars_15min` → `bucket` column ✅
- `underlying_bars_1hour` → `bucket` column ✅
- `underlying_bars_daily` → `bucket` column ✅

**Verification**: Line 282, 296 in `scripts/init_timescale.sql`

### Backtest Tables

#### 3. `backtest_runs`
```sql
start_date TIMESTAMPTZ NOT NULL,  -- Backtest period start ✅
end_date TIMESTAMPTZ NOT NULL,  -- Backtest period end ✅
started_at TIMESTAMPTZ,  -- Execution start ✅
completed_at TIMESTAMPTZ,  -- Execution end ✅
created_at TIMESTAMPTZ DEFAULT NOW(),  -- Metadata ✅
```

**Verification**: Line 457-458, 467-468, 486 in `scripts/init_timescale.sql`

#### 4. `backtest_trades`
```sql
entry_time TIMESTAMPTZ NOT NULL,  -- Trade entry ✅
exit_time TIMESTAMPTZ NOT NULL,  -- Trade exit ✅
created_at TIMESTAMPTZ DEFAULT NOW(),  -- Metadata ✅
```

**Verification**: Line 505-506, 529 in `scripts/init_timescale.sql`

#### 5. `backtest_equity_curve` (Hypertable)
```sql
timestamp TIMESTAMPTZ NOT NULL,  -- Equity curve snapshot time ✅
created_at TIMESTAMPTZ DEFAULT NOW(),  -- Metadata ✅
```

**Verification**: Line 540, 553 in `scripts/init_timescale.sql`

### Live Trading Tables

#### 6. `live_engine_state` (Created by Python)
```sql
timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- State timestamp ✅
```

**Verification**: `src/live_trading_service/state_store.py:92`

#### 7. `live_positions` (Created by Python)
```sql
entry_time TIMESTAMPTZ NOT NULL,  -- Position entry ✅
exit_time TIMESTAMPTZ,  -- Position exit ✅
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- Creation timestamp ✅
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- Update timestamp ✅
```

**Verification**: `src/live_trading_service/state_store.py:105, 110, 115, 116`

## Summary Statistics

| Category | Tables | Timestamp Columns | TIMESTAMPTZ ✅ | TIMESTAMP ❌ |
|----------|--------|-------------------|----------------|--------------|
| Market Data | 2 hypertables | 4 | 4 | 0 |
| Continuous Aggregates | 8 materialized views | 8 | 8 | 0 |
| Backtest | 3 tables (1 hypertable) | 10 | 10 | 0 |
| Live Trading | 2 tables | 5 | 5 | 0 |
| **TOTAL** | **15 tables/views** | **27** | **27** | **0** |

## PostgreSQL TIMESTAMPTZ Behavior

### Storage
- **Internal Format**: All timestamps stored as UTC (Unix epoch)
- **Size**: 8 bytes per timestamp
- **Range**: 4713 BC to 294276 AD
- **Precision**: Microseconds (1e-6 seconds)

### Conversion on Insert
```sql
-- All of these are converted to UTC before storage
INSERT INTO options_bars (timestamp, ...) VALUES
  ('2025-12-23 14:30:00+00:00', ...),  -- Already UTC
  ('2025-12-23 09:30:00-05:00', ...),  -- EST → converted to 14:30 UTC
  ('2025-12-23 09:30:00 America/New_York', ...);  -- EST → converted to 14:30 UTC
```

### Conversion on Query
```sql
-- PostgreSQL returns timestamps in session timezone
SET TIMEZONE TO 'UTC';  -- Always use UTC for consistency
SELECT timestamp FROM options_bars;  -- Returns as UTC

SET TIMEZONE TO 'America/New_York';
SELECT timestamp FROM options_bars;  -- Returns converted to EST
```

### Python Interaction (psycopg2/psycopg3)

**Inserting Timestamps**:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

# ✅ CORRECT: Timezone-aware datetime
utc_time = datetime(2025, 12, 23, 14, 30, tzinfo=ZoneInfo("UTC"))
cursor.execute("INSERT INTO options_bars (timestamp, ...) VALUES (%s, ...)", (utc_time,))
# PostgreSQL receives UTC timestamp, stores as-is

# ✅ CORRECT: Using now_utc() utility
from quant_vibe.utils import now_utc
cursor.execute("INSERT INTO options_bars (timestamp, ...) VALUES (%s, ...)", (now_utc(),))

# ⚠️ WARNING: Naive datetime (psycopg2 assumes local timezone!)
naive_time = datetime(2025, 12, 23, 14, 30)  # No timezone
cursor.execute("INSERT INTO options_bars (timestamp, ...) VALUES (%s, ...)", (naive_time,))
# psycopg2 assumes naive time is in server's local timezone
# This can cause bugs if server timezone != UTC!
```

**Querying Timestamps**:
```python
# psycopg2 returns timezone-aware datetime objects by default
cursor.execute("SELECT timestamp FROM options_bars LIMIT 1")
row = cursor.fetchone()
timestamp = row[0]  # datetime object with tzinfo=UTC

# Verify it's UTC-aware
from quant_vibe.utils import is_utc_aware
assert is_utc_aware(timestamp)  # True
```

## Common Pitfalls (Avoided)

### ❌ Pitfall 1: Using TIMESTAMP (without TZ)
```sql
-- BAD: No timezone information
CREATE TABLE bad_table (
    created_at TIMESTAMP  -- ❌ Naive timestamp
);

-- GOOD: Always use TIMESTAMPTZ
CREATE TABLE good_table (
    created_at TIMESTAMPTZ  -- ✅ Timezone-aware
);
```

**Impact**:
- Ambiguous timestamps (is it UTC? Local? Unknown!)
- Daylight saving time bugs
- Cannot reliably compare across timezones

**Our Status**: ✅ No naive TIMESTAMP columns found

### ❌ Pitfall 2: Inserting Naive Datetimes from Python
```python
# BAD: Naive datetime
timestamp = datetime.now()  # No timezone!
cursor.execute("INSERT INTO options_bars (timestamp, ...) VALUES (%s, ...)", (timestamp,))
# psycopg2 assumes server local timezone → potential bug

# GOOD: Use timestamp utilities
from quant_vibe.utils import now_utc
timestamp = now_utc()  # Always UTC-aware
cursor.execute("INSERT INTO options_bars (timestamp, ...) VALUES (%s, ...)", (timestamp,))
```

**Impact**:
- Server timezone changes can break data
- Inconsistent timestamps across environments
- Hard-to-debug timezone bugs

**Our Status**: ✅ Timestamp utilities enforcing UTC-aware datetimes

### ❌ Pitfall 3: Session Timezone Mismatch
```sql
-- BAD: Session timezone affects query results
SET TIMEZONE TO 'America/Los_Angeles';  -- Server returns timestamps in PT!
SELECT timestamp FROM options_bars;

-- GOOD: Always set to UTC for consistency
SET TIMEZONE TO 'UTC';
SELECT timestamp FROM options_bars;
```

**Impact**:
- Query results vary based on session settings
- Confusion when comparing timestamps
- Pandas DataFrame index timezone inconsistency

**Our Status**: ⚠️ Should verify Python clients set session timezone to UTC

## Recommendations

### ✅ Already Implemented

1. **Database Schema**: All timestamp columns use `TIMESTAMPTZ` ✅
2. **Timestamp Utilities**: Created `timestamp_utils.py` with `now_utc()`, `to_utc()` ✅
3. **Schema Tests**: Verification tests in `test_schema_consistency.py` ✅
4. **Documentation**: Schema mapping and timezone requirements documented ✅

### 🔧 Additional Improvements (Optional)

#### 1. Set PostgreSQL Session Timezone in Connection
```python
# src/quant_vibe/data/timescale_store.py

def __init__(self):
    self.conn = psycopg2.connect(...)
    # Always set session timezone to UTC
    cursor = self.conn.cursor()
    cursor.execute("SET TIMEZONE TO 'UTC'")
    cursor.close()
```

**Benefit**: Ensures all queries return timestamps as UTC regardless of server config

#### 2. Add Database-Level Timezone Enforcement
```sql
-- In init_timescale.sql or postgresql.conf
ALTER DATABASE options_data SET TIMEZONE TO 'UTC';
```

**Benefit**: Database-wide consistency, no per-connection setup needed

#### 3. Add Timestamp Validation Trigger
```sql
-- Optional: Validate all inserted timestamps are UTC
CREATE OR REPLACE FUNCTION validate_utc_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    -- PostgreSQL TIMESTAMPTZ is always stored as UTC internally,
    -- but we can log a warning if input timezone is non-UTC
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to critical tables
CREATE TRIGGER validate_options_bars_timestamp
    BEFORE INSERT OR UPDATE ON options_bars
    FOR EACH ROW
    EXECUTE FUNCTION validate_utc_timestamp();
```

**Benefit**: Extra safety layer, logs non-UTC inputs (though they're converted anyway)

#### 4. Monitor for Naive Timestamp Insertions
```python
# Add to logging/monitoring
import logging

def log_timestamp_insert(timestamp, table):
    if timestamp.tzinfo is None:
        logging.warning(
            f"Naive timestamp inserted into {table}: {timestamp}. "
            "Use now_utc() or to_utc() instead."
        )
```

**Benefit**: Catch code paths still using naive datetimes

## Testing Verification

### Manual Verification (Run in psql)
```sql
-- Connect to database
psql -U quantvibe -d options_data

-- Verify all timestamp columns are TIMESTAMPTZ
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND data_type LIKE '%timestamp%'
ORDER BY table_name, ordinal_position;

-- Expected output: All columns should show 'timestamp with time zone'
```

**Sample Output**:
```
       table_name        |    column_name     |        data_type
-------------------------+--------------------+---------------------------
 backtest_equity_curve   | timestamp          | timestamp with time zone
 backtest_equity_curve   | created_at         | timestamp with time zone
 backtest_runs           | start_date         | timestamp with time zone
 backtest_runs           | end_date           | timestamp with time zone
 backtest_runs           | started_at         | timestamp with time zone
 backtest_runs           | completed_at       | timestamp with time zone
 backtest_runs           | created_at         | timestamp with time zone
 backtest_trades         | entry_time         | timestamp with time zone
 backtest_trades         | exit_time          | timestamp with time zone
 backtest_trades         | created_at         | timestamp with time zone
 live_engine_state       | timestamp          | timestamp with time zone
 live_positions          | entry_time         | timestamp with time zone
 live_positions          | exit_time          | timestamp with time zone
 live_positions          | created_at         | timestamp with time zone
 live_positions          | updated_at         | timestamp with time zone
 options_bars            | timestamp          | timestamp with time zone
 options_bars            | created_at         | timestamp with time zone
 underlying_bars         | timestamp          | timestamp with time zone
 underlying_bars         | created_at         | timestamp with time zone
```

### Automated Test
```python
# tests/integration/test_database_timezone.py
import psycopg2
import pytest

def test_all_timestamp_columns_are_timestamptz():
    """Verify all timestamp columns use TIMESTAMPTZ (not TIMESTAMP)"""
    conn = psycopg2.connect(...)
    cursor = conn.cursor()

    # Query all timestamp columns
    cursor.execute("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type LIKE '%timestamp%'
    """)

    rows = cursor.fetchall()

    # Verify all are 'timestamp with time zone' (TIMESTAMPTZ)
    for table, column, dtype in rows:
        assert dtype == 'timestamp with time zone', \
            f"{table}.{column} uses {dtype} instead of TIMESTAMPTZ"

    cursor.close()
    conn.close()

    print(f"✅ Verified {len(rows)} timestamp columns are all TIMESTAMPTZ")
```

## Conclusion

**Status**: ✅ **ALL VERIFIED - 100% TIMESTAMPTZ compliance**

All 27 timestamp columns across 15 tables/views correctly use `TIMESTAMPTZ` (timezone-aware, stored as UTC). No naive `TIMESTAMP` columns found.

The database schema is correctly configured for UTC timezone handling. Combined with the Python `timestamp_utils` module, the system has a solid foundation for consistent timezone handling.

### Next Steps (Optional Enhancements)

1. Add session-level `SET TIMEZONE TO 'UTC'` in Python connection setup
2. Add automated integration test to verify database schema
3. Monitor application logs for any naive timestamp warnings
4. Consider database-level timezone enforcement via `ALTER DATABASE`

## References

- PostgreSQL TIMESTAMPTZ Documentation: https://www.postgresql.org/docs/current/datatype-datetime.html
- TimescaleDB Hypertable Documentation: https://docs.timescale.com/use-timescale/latest/hypertables/
- psycopg2 Timestamp Handling: https://www.psycopg.org/docs/usage.html#date-time-objects
- Python datetime with ZoneInfo: https://docs.python.org/3/library/zoneinfo.html

---

**Last Updated**: 2026-01-02
**Verified By**: Database schema analysis + SQL grep verification
**Schema Version**: init_timescale.sql (current)
