# Option Symbol Normalization

## Overview

Option symbols from different data sources use different formats. To ensure consistent storage and lookups across the quant-vibe system, all option symbols are normalized to a canonical format.

## Symbol Formats

### Input Formats

Different data sources use different formatting:

| Source | Format | Example |
|--------|--------|---------|
| **Schwab Streaming** | Extra spaces between underlying and date | `SPXW  260123P06860000` |
| **Schwab Poll** | Already normalized | `SPXW251226C06875000` |
| **Massive API** | `O:` prefix | `O:SPXW251219C06945000` |

### Canonical Format

The target format used throughout the system:

```
{UNDERLYING}{YYMMDD}{C|P}{STRIKE8DIGITS}
```

**Example:** `SPXW251226C06875000`

**Components:**
- `SPXW` - Underlying symbol (4 chars)
- `251226` - Expiration date (YYMMDD, 6 digits)
- `C` or `P` - Option type (Call or Put, 1 char)
- `06875000` - Strike price × 1000 (8 digits)

**Characteristics:**
- ✅ No spaces
- ✅ No `O:` prefix
- ✅ Consistent length and structure

## Implementation

### Utility Function

Centralized in `src/quant_vibe/utils/symbol_utils.py`:

```python
from quant_vibe.utils import normalize_option_ticker

# Normalize any format to canonical format
normalized = normalize_option_ticker("SPXW  260123P06860000")
# Returns: "SPXW260123P06860000"
```

### Updated Components

The following components now use the normalization utility:

1. **Streaming Service** (`src/streaming_service/aggregator.py`)
   - Normalizes symbols before storing bars to database
   - Ensures all streaming data uses canonical format

2. **Contract Enricher** (`src/streaming_service/enrich_stream_with_chain.py`)
   - Normalizes symbols when caching contract details
   - Normalizes symbols during lookup

3. **Poll Script** (`scripts/poll-schwab-py-spxw.py`)
   - Normalizes symbols before inserting into database
   - Ensures poll data matches streaming format

4. **Backfill Scripts** (`scripts/backfill/massive_spx_options.py`)
   - Uses `TimescaleStore.normalize_contract_symbol()` which implements the same logic
   - Ensures historical data matches real-time format

## Benefits

### 1. Consistent Storage

All option symbols in the `options_bars` table use the same format:

```sql
SELECT DISTINCT option_ticker FROM options_bars LIMIT 5;

-- All results use canonical format:
-- SPXW251226C06875000
-- SPXW251226P06850000
-- SPXW251227C06900000
-- SPXW251227P06875000
-- SPXW260123C06860000
```

### 2. Reliable Lookups

Queries work regardless of input format:

```python
from quant_vibe.utils import normalize_option_ticker

# User provides Massive format
user_input = "O:SPXW251226C06875000"

# Normalize before query
normalized = normalize_option_ticker(user_input)

# Query always works
bars = ts_store.get_option_bars(normalized, start_time, end_time)
```

### 3. Data Source Independence

No need to remember which format each source uses:

```python
# All of these normalize to the same result
normalize_option_ticker("SPXW  260123P06860000")  # Schwab streaming
normalize_option_ticker("SPXW260123P06860000")    # Schwab poll
normalize_option_ticker("O:SPXW260123P06860000")  # Massive API
# All return: "SPXW260123P06860000"
```

### 4. Simplified Caching

Contract enrichment cache uses consistent keys:

```python
# Cache lookup works with any format
details = enricher.get_contract_details("SPXW  260123P06860000")
details = enricher.get_contract_details("O:SPXW260123P06860000")
# Both return the same cached data
```

## Usage Examples

### Basic Normalization

```python
from quant_vibe.utils import normalize_option_ticker

# Schwab streaming format (with spaces)
symbol = "SPXW  260123P06860000"
normalized = normalize_option_ticker(symbol)
print(normalized)  # "SPXW260123P06860000"

# Massive API format (with O: prefix)
symbol = "O:SPXW251219C06945000"
normalized = normalize_option_ticker(symbol)
print(normalized)  # "SPXW251219C06945000"

# Already normalized
symbol = "SPXW251226C06875000"
normalized = normalize_option_ticker(symbol)
print(normalized)  # "SPXW251226C06875000"
```

### Database Queries

```python
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.utils import normalize_option_ticker

ts_store = TimescaleStore()

# User provides symbol in any format
user_symbol = "SPXW  260123P06860000"

# Normalize before querying
normalized_symbol = normalize_option_ticker(user_symbol)

# Query database
bars = ts_store.get_option_bars(
    option_ticker=normalized_symbol,
    start_time=start,
    end_time=end
)
```

### Backtest Data Loading

```python
from quant_vibe.utils import load_options_backtest_data, normalize_option_ticker

# Normalize symbols for filtering
symbols = [
    "SPXW  251226C06875000",  # Schwab format
    "O:SPXW251226P06850000",  # Massive format
]

normalized_symbols = [normalize_option_ticker(s) for s in symbols]

# Load data (already normalized in database)
options_data, underlying_data = load_options_backtest_data(
    underlying_ticker="SPX",
    start_date=start_date,
    end_date=end_date,
    min_dte=0,
    max_dte=45,
)

# Filter for specific symbols
filtered = options_data[options_data['option_ticker'].isin(normalized_symbols)]
```

## Migration Notes

### Existing Data

If you have existing data with non-normalized symbols, run this migration:

```sql
-- Update Schwab streaming format (with spaces)
UPDATE options_bars
SET option_ticker = REPLACE(option_ticker, '  ', '')
WHERE option_ticker LIKE '%  %';

-- Update Massive format (with O: prefix)
UPDATE options_bars
SET option_ticker = SUBSTRING(option_ticker FROM 3)
WHERE option_ticker LIKE 'O:%';
```

### Verification

Check that all symbols are normalized:

```sql
-- Should return 0 rows
SELECT COUNT(*) FROM options_bars
WHERE option_ticker LIKE '%  %'      -- Has spaces
   OR option_ticker LIKE 'O:%';      -- Has O: prefix
```

## Testing

Comprehensive tests in `tests/unit/utils/test_symbol_utils.py`:

```bash
# Run tests
pytest tests/unit/utils/test_symbol_utils.py -v

# All tests should pass:
# ✅ test_schwab_streaming_format
# ✅ test_schwab_poll_format
# ✅ test_massive_format
# ✅ test_already_normalized
# ✅ test_multiple_normalizations_idempotent
# ... and more
```

## Best Practices

### 1. Always Normalize on Input

Normalize symbols as soon as they enter the system:

```python
# ✅ Good: Normalize immediately
def process_quote(raw_quote):
    raw_quote['symbol'] = normalize_option_ticker(raw_quote['symbol'])
    # ... rest of processing

# ❌ Bad: Store raw format
def process_quote(raw_quote):
    # ... processing with raw symbol
```

### 2. Normalize Before Lookups

Always normalize before cache/database lookups:

```python
# ✅ Good: Normalize before lookup
normalized_symbol = normalize_option_ticker(user_input)
cached_data = cache.get(normalized_symbol)

# ❌ Bad: Lookup with raw symbol
cached_data = cache.get(user_input)  # Might miss cache hit
```

### 3. Idempotent Normalization

It's safe to normalize multiple times:

```python
# This is fine
symbol = normalize_option_ticker(normalize_option_ticker(raw_symbol))
```

### 4. Use Utility, Don't Duplicate

Always import the utility instead of rewriting:

```python
# ✅ Good: Use centralized utility
from quant_vibe.utils import normalize_option_ticker

# ❌ Bad: Duplicate logic
def my_normalize(symbol):
    return symbol.replace(" ", "").replace("O:", "")
```

## Related Files

- **Utility:** `src/quant_vibe/utils/symbol_utils.py`
- **Tests:** `tests/unit/utils/test_symbol_utils.py`
- **Streaming:** `src/streaming_service/aggregator.py`
- **Enricher:** `src/streaming_service/enrich_stream_with_chain.py`
- **Poll:** `scripts/poll-schwab-py-spxw.py`
- **Backfill:** `scripts/backfill/massive_spx_options.py`

## Support

For questions or issues:
1. Check this documentation
2. Review test cases in `test_symbol_utils.py`
3. See implementation in `symbol_utils.py`
