# Schema Mapping Reference

## Column Name Mapping

This document defines the official column name mapping across different parts of the system.

### The `option_ticker` ↔ `contract_symbol` Problem

**Issue**: The database uses `option_ticker` but application code expects `contract_symbol`.

**Why**: Historical reasons - database schema was created first with `option_ticker`, but strategies adopted `contract_symbol` as more descriptive name.

**Current State**:

| Component | Column Name | Notes |
|-----------|-------------|-------|
| TimescaleDB `options_bars` table | `option_ticker` | Database column name |
| Redis messages (streaming) | `option_ticker` | Published from aggregators |
| TimescaleDB queries (backtesting) | `contract_symbol` | **Aliased** in SQL: `SELECT option_ticker AS contract_symbol` |
| LiveMarketDataProvider | `contract_symbol` | **Renamed** via pandas: `rename(columns={'option_ticker': 'contract_symbol'})` |
| Strategy code | `contract_symbol` | Expected by all strategies |

### Critical Code Locations

**1. Database Query Aliasing** (`src/quant_vibe/data/timescale_store.py:546-547`)
```python
SELECT
    {time_column} as timestamp,
    option_ticker as contract_symbol,  # ← ALIAS HERE
    strike_price,
    ...
```

**2. Live Data Renaming** (`src/quant_vibe/data/live_market_data.py:152-154`)
```python
if not all_bars.empty and 'option_ticker' in all_bars.columns:
    all_bars = all_bars.rename(columns={'option_ticker': 'contract_symbol'})  # ← RENAME HERE
```

**3. Strategy Access** (all strategies)
```python
# Strategies expect 'contract_symbol' column
options_data['contract_symbol'].apply(lambda x: ...)
```

### Other Column Names

| Data Field | Database Column | DataFrame Column | Notes |
|------------|----------------|------------------|-------|
| Symbol | `option_ticker` | `contract_symbol` | **Inconsistent** (see above) |
| Underlying | `underlying_ticker` | `underlying_ticker` | Consistent |
| Strike | `strike_price` | `strike_price` | Consistent |
| Contract type | `contract_type` | `contract_type` | Consistent (lowercase "call"/"put") |
| Expiration | `expiration_date` | `expiration_date` | Consistent |
| OHLCV | `open`, `high`, `low`, `close`, `volume` | Same | Consistent |
| Quotes | `bid`, `ask` | `bid`, `ask` | Consistent |
| Mark price | N/A (calculated in SQL) | `mark` | Calculated: `(bid + ask) / 2` |
| Greeks | `delta`, `gamma`, `theta`, `vega`, `rho` | Same | Consistent |

## Symbol Format Standards

### Normalized Format
**Standard**: `SPXW260123P06860000`

**Components**:
- Root: `SPXW` (4 chars, can vary)
- Expiration: `260123` (YYMMDD format)
- Type: `P` (put) or `C` (call)
- Strike: `06860000` (8 digits, price × 1000)

**Example Parsing**:
```python
from quant_vibe.utils.symbol_utils import (
    normalize_option_ticker,
    parse_contract_type_from_ticker,
    parse_strike_from_ticker,
    parse_expiration_from_ticker,
)

symbol = "SPXW  260123P06860000"  # Raw from Schwab
normalized = normalize_option_ticker(symbol)  # "SPXW260123P06860000"

contract_type = parse_contract_type_from_ticker(normalized)  # "put" (lowercase!)
strike = parse_strike_from_ticker(normalized)  # 6860.0
expiration = parse_expiration_from_ticker(normalized)  # datetime.date(2026, 1, 23)
```

### Symbol Format Variations by Source

| Source | Format | Example | Normalization Needed? |
|--------|--------|---------|----------------------|
| Schwab API | With spaces | `"SPXW  260123P06860000"` | Yes - remove spaces |
| Massive API | `O:` prefix | `"O:SPXW251219C06945000"` | Yes - remove prefix |
| Database | Normalized | `"SPXW260123P06860000"` | No |
| Strategies | Normalized | `"SPXW260123P06860000"` | No |

**Normalization locations**:
1. Streaming aggregator (`streaming_service/aggregator.py:138`)
2. Database insert (`data/timescale_store.py:227`)
3. Redis data feed (`data/redis_data_feed.py:186`)

## Timestamp Standards

### UTC Requirement

**Rule**: ALL timestamps MUST be:
1. Timezone-aware (not naive)
2. In UTC timezone
3. Created via `timestamp_utils.py` functions

### Timestamp Creation

```python
from quant_vibe.utils.timestamp_utils import now_utc, to_utc

# ✅ CORRECT: Create current UTC timestamp
timestamp = now_utc()

# ✅ CORRECT: Convert naive to UTC
naive_dt = datetime(2025, 12, 23, 14, 30)
utc_dt = to_utc(naive_dt)

# ❌ WRONG: Naive datetime
timestamp = datetime.now()  # No timezone!

# ❌ WRONG: Assumed UTC without marking
timestamp = datetime.utcnow()  # Naive!
```

### Timestamp Formats by Component

| Component | Format | Timezone | Notes |
|-----------|--------|----------|-------|
| Streaming aggregators | `datetime` object | **Must be UTC-aware** | Use `now_utc()` |
| Redis messages | ISO string | UTC (no explicit tz) | Serialized via `datetime.isoformat()` |
| TimescaleDB | `TIMESTAMPTZ` | UTC | PostgreSQL native |
| Backtest queries | `datetime` object | **Must be UTC-aware** | Use `to_utc()` |
| Strategy code | `datetime` object | **Must be UTC-aware** | From DataFrame index |

### Market Hours (EST)

**Market Hours**: 9:30 AM - 4:00 PM EST (Eastern Time)

**Conversion to UTC** (via `datetime_utils.py`):
```python
from quant_vibe.utils.datetime_utils import trading_day_to_utc

# Get market hours for a trading day
market_open, market_close = trading_day_to_utc(2025, 12, 23)

# Returns: (
#   datetime(2025, 12, 23, 14, 30, tzinfo=UTC),  # 9:30 AM EST
#   datetime(2025, 12, 23, 21, 0, tzinfo=UTC)    # 4:00 PM EST
# )
```

**EST ↔ UTC Offset**:
- EST (winter): UTC - 5 hours
- EDT (summer): UTC - 4 hours
- 9:30 AM EST = 2:30 PM UTC (14:30)
- 4:00 PM EST = 9:00 PM UTC (21:00)

## Data Type Constraints

### Greeks

**Database**: `NUMERIC(10,6)` with max value `99.999999`

**Issue**: Implied volatility can exceed 100% during high volatility periods.

**Solution**: Values > 99.999999 are **silently coerced** to 99.999999 in `timescale_store.py:_coerce_greek_value()`

**Code Location**: `src/quant_vibe/data/timescale_store.py:262-294`

```python
def _coerce_greek_value(value: float | None, greek_name: str) -> float | None:
    """Coerce Greek value to fit NUMERIC(10,6) constraint"""
    if value is None:
        return None
    if abs(value) > 99.999999:
        logger.warning(f"{greek_name} value {value} exceeds max, coercing to 99.999999")
        return 99.999999 if value > 0 else -99.999999
    return value
```

**Impact**:
- ⚠️ **Data loss**: IV > 100% gets truncated
- ⚠️ **Silent failure**: Only logged as warning
- ⚠️ **Inconsistency**: Redis messages may have different values than database

**Recommendation**: Consider changing database schema to `NUMERIC(12,6)` to allow values up to 999,999.999999.

### Contract Type

**Standard**: Lowercase `"call"` or `"put"` (not `"C"` or `"P"`)

**Parsing** (`src/quant_vibe/utils/symbol_utils.py:83-86`):
```python
if type_char == 'C':
    return 'call'  # lowercase!
elif type_char == 'P':
    return 'put'   # lowercase!
```

**Storage**:
- Database: `contract_type TEXT` (lowercase)
- Redis: `"call"` or `"put"` (lowercase)
- Strategies: `"call"` or `"put"` (lowercase)

### Strike Price

**Format**: Float representation of strike price

**Parsing from symbol**:
```python
# Symbol: "SPXW260123P06860000"
# Last 8 digits: "06860000"
# Strike: 06860000 / 1000 = 6860.0
```

**Storage**:
- Database: `NUMERIC(10,2)` (e.g., 6860.00)
- DataFrame: `float64` (e.g., 6860.0)
- Strategies: `float` (e.g., 6860.0)

## DataFrame Schema

### Options Data (from backtesting or live data)

**Required columns**:
```python
{
    'timestamp': datetime (UTC-aware),
    'contract_symbol': str,        # ← Note: not 'option_ticker'
    'underlying_ticker': str,
    'strike_price': float,
    'contract_type': str,          # 'call' or 'put' (lowercase)
    'expiration_date': datetime.date,
    'open': float,
    'high': float,
    'low': float,
    'close': float,
    'volume': int,
    'bid': float,
    'ask': float,
    'mark': float,                 # (bid + ask) / 2
    'delta': float | None,
    'gamma': float | None,
    'theta': float | None,
    'vega': float | None,
    'rho': float | None,
    'implied_volatility': float | None,
}
```

### Underlying Data

**Required columns**:
```python
{
    'timestamp': datetime (UTC-aware, index),
    'open': float,
    'high': float,
    'low': float,
    'close': float,
    'volume': int,
}
```

## Strategy Access Patterns

### Accessing Options Data

```python
# ✅ CORRECT: Use 'contract_symbol'
contract = options_data['contract_symbol'].iloc[0]

# ✅ CORRECT: Filter by contract_symbol
spxw_options = options_data[options_data['contract_symbol'].str.startswith('SPXW')]

# ❌ WRONG: Use 'option_ticker' (will fail with KeyError)
contract = options_data['option_ticker'].iloc[0]
```

### Accessing Contract Details

```python
# ✅ CORRECT: Access from parsed columns
strike = options_data['strike_price'].iloc[0]  # From database or enrichment
contract_type = options_data['contract_type'].iloc[0]  # "call" or "put"

# ✅ ACCEPTABLE: Parse from symbol if columns missing
from quant_vibe.utils.symbol_utils import parse_strike_from_ticker
strike = parse_strike_from_ticker(options_data['contract_symbol'].iloc[0])
```

### Checking Timestamps

```python
# ✅ CORRECT: Filter with UTC-aware datetimes
from quant_vibe.utils.timestamp_utils import to_utc

start = to_utc(datetime(2025, 12, 23, 14, 30))
end = to_utc(datetime(2025, 12, 23, 21, 0))

filtered = options_data[
    (options_data['timestamp'] >= start) &
    (options_data['timestamp'] <= end)
]

# ❌ WRONG: Use naive datetime (may fail with mixed tz data)
start = datetime(2025, 12, 23, 14, 30)  # Naive!
filtered = options_data[options_data['timestamp'] >= start]
```

## Testing Schema Consistency

### Unit Test Pattern

```python
def test_schema_consistency():
    """Verify column names match across data sources"""
    # Load from different sources
    db_data = timescale_store.get_options_for_backtest(...)
    live_data = live_market_data.get_recent_bars(...)

    # Required columns
    required = {
        'timestamp', 'contract_symbol', 'strike_price',
        'contract_type', 'bid', 'ask', 'mark'
    }

    # Verify both have same columns
    assert required.issubset(db_data.columns)
    assert required.issubset(live_data.columns)

    # Verify timestamp is UTC-aware
    assert db_data['timestamp'].iloc[0].tzinfo is not None
    assert live_data['timestamp'].iloc[0].tzinfo is not None
```

## Migration Path

### Phase 1: Add Validation (Immediate)
1. Use `timestamp_utils.py` for all datetime creation
2. Add schema validation tests
3. Document mappings (this file)

### Phase 2: Standardize Code (Week 2)
1. Update streaming to use `timestamp_utils.now_utc()`
2. Add validation at Redis publish/subscribe
3. Add validation at TimescaleDB insert/query

### Phase 3: Database Migration (Week 3)
1. Create view: `CREATE VIEW options_bars_v2 AS SELECT option_ticker AS contract_symbol, ...`
2. Update all queries to use view
3. Eventually rename column in database (breaking change)

### Phase 4: Pydantic Models (Week 4+)
1. Define `OptionsBar` Pydantic model
2. Enforce at all system boundaries
3. Remove manual column renames
4. Compile-time type checking

## See Also

- `src/quant_vibe/utils/timestamp_utils.py` - Timestamp utilities
- `src/quant_vibe/utils/symbol_utils.py` - Symbol parsing
- `src/quant_vibe/utils/datetime_utils.py` - Market hours / trading days
- `src/quant_vibe/data/timescale_store.py` - Database access
- `src/quant_vibe/data/live_market_data.py` - Live data access
