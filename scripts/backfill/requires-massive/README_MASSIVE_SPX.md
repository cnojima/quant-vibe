# SPX Index Backfill - Massive.io Custom Bars API

This script backfills historical S&P 500 Index (SPX) 1-minute bars from Massive.io's Custom Bars API into the `underlying_bars` table.

## Overview

- **Source**: Massive.io Custom Bars API (`/v2/aggs/ticker/I:SPX/range/...`)
- **Target**: TimescaleDB `underlying_bars` table
- **Ticker**: I:SPX (Massive) → SPX (database)
- **Frequency**: 1-minute bars
- **Range**: 2023-02-01 to Present (configurable)
- **Data Availability**: Massive.io has I:SPX data starting from **February 14, 2023**
- **Data Points**: ~182,000 bars (2 years × ~252 trading days × 390 bars/day)

## Features

✅ **Schema Compliant**: Uses `UnderlyingBar` Pydantic model
✅ **Market Calendar Aware**: Filters weekends and NYSE holidays (2015-2026)
✅ **Gap Detection**: Identifies missing or incomplete trading days
✅ **Idempotent**: Safe to re-run (uses ON CONFLICT DO UPDATE)
✅ **Validation**: Verifies bar counts and data quality
✅ **Progress Tracking**: ETA, statistics, and error reporting
✅ **Chunked Fetching**: 30-day chunks to respect API limits
✅ **Dry Run Mode**: Test without database writes

## Prerequisites

1. **Massive.io API Key**:
   ```bash
   # Add to .env
   MASSIVE_API_KEY=your_api_key_here
   ```

2. **TimescaleDB Connection**:
   ```bash
   # Verify .env has correct credentials
   TIMESCALE_HOST=localhost
   TIMESCALE_PORT=5432
   TIMESCALE_USER=quantvibe
   TIMESCALE_PASSWORD=quantvibe_dev
   TIMESCALE_DB=options_data
   ```

3. **Activate Virtual Environment**:
   ```bash
   source venv/bin/activate
   ```

## Usage

### 1. Test with Single Day (Recommended First)

```bash
python scripts/backfill/backfill_massive_spx_index.py \
  --start-date 2024-12-20 \
  --end-date 2024-12-21 \
  --dry-run
```

**Expected Output**:
```
✅ Fetched 394 bars
✅ Transformed 394 bars
🔍 Validating 1 trading days...
   ✅ 2024-12-20: Valid: 394 bars
🔸 DRY RUN: Would insert 394 bars
```

### 2. Test with One Week

```bash
python scripts/backfill/backfill_massive_spx_index.py \
  --start-date 2024-12-16 \
  --end-date 2024-12-21 \
  --dry-run
```

**Expected Output**:
```
✅ Fetched 1,965 bars
✅ Transformed 1,965 bars
🔍 Validating 5 trading days...
   ✅ 2024-12-16: Valid: 393 bars
   ✅ 2024-12-17: Valid: 392 bars
   ✅ 2024-12-18: Valid: 392 bars
   ✅ 2024-12-19: Valid: 394 bars
   ✅ 2024-12-20: Valid: 394 bars
```

### 3. Backfill Full Available Range (Feb 2023 - Present)

```bash
# First, do a dry run to estimate time
python scripts/backfill/backfill_massive_spx_index.py \
  --start-date 2023-02-01 \
  --end-date 2025-01-01 \
  --dry-run

# Then run the actual backfill (~2 years of data)
python scripts/backfill/backfill_massive_spx_index.py \
  --start-date 2023-02-01 \
  --end-date 2025-01-01
```

**Estimated Runtime**: 1-2 minutes for ~2 years of data

**Note**: Massive.io only has I:SPX data from February 14, 2023 onwards. Earlier dates will return no data.

### 4. Detect Gaps Only

```bash
python scripts/backfill/backfill_massive_spx_index.py \
  --start-date 2015-01-01 \
  --end-date 2025-01-01 \
  --detect-gaps-only
```

### 5. Custom Date Range

```bash
# Backfill specific year with larger chunks
python scripts/backfill/backfill_massive_spx_index.py \
  --start-date 2020-01-01 \
  --end-date 2021-01-01 \
  --chunk-days 60
```

## Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--start-date` | `2023-02-01` | Start date (YYYY-MM-DD, earliest: 2023-02-14) |
| `--end-date` | `2025-01-01` | End date (YYYY-MM-DD) |
| `--chunk-days` | `30` | Days per API call chunk |
| `--dry-run` | `False` | Fetch data but don't insert |
| `--skip-validation` | `False` | Skip bar count validation (faster) |
| `--detect-gaps-only` | `False` | Only detect gaps, don't backfill |

## Data Schema

### Source (Massive.io API)

```json
{
  "ticker": "I:SPX",
  "results": [
    {
      "t": 1703001600000,  // Unix timestamp (ms)
      "o": 4783.45,         // Open
      "h": 4785.23,         // High
      "l": 4781.12,         // Low
      "c": 4784.89          // Close
    }
  ]
}
```

### Target (underlying_bars table)

```sql
CREATE TABLE underlying_bars (
    timestamp TIMESTAMPTZ NOT NULL,
    ticker TEXT NOT NULL,
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    volume INTEGER DEFAULT 0,
    vwap NUMERIC,
    transactions INTEGER,
    data_source TEXT,
    PRIMARY KEY (timestamp, ticker)
);
```

### Transformation

```python
UnderlyingBar(
    timestamp=to_utc(timestamp_ms),  # UTC-aware
    ticker='SPX',                    # Normalized from I:SPX
    open=Decimal('4783.45'),         # Decimal precision
    high=Decimal('4785.23'),
    low=Decimal('4781.12'),
    close=Decimal('4784.89'),
    volume=0,                        # Indices have no volume
    vwap=None,                       # Not provided by API
    transactions=None,               # Not provided by API
    data_source='massive',
)
```

## Market Calendar

### Trading Hours
- **NYSE**: 9:30 AM - 4:00 PM ET (6.5 hours = 390 minutes)
- **Expected bars per day**: 390 ± 5 (allows for slight variations)

### Excluded Days
- **Weekends**: Saturday, Sunday
- **Holidays**: NYSE market holidays (2015-2026 calendar included)

### Early Close Days
Some days have fewer than 390 bars due to early market close:
- Christmas Eve (typically 1:00 PM close = 210 bars)
- Day after Thanksgiving (typically 1:00 PM close = 210 bars)
- July 3rd (when July 4th falls on certain days)

The script allows bars < 390 but > 100 to accommodate these days.

## Error Handling

### Common Issues

**1. API Rate Limits**
```
Error: 429 Too Many Requests
```
**Solution**: Script includes 0.5s pause between chunks. Increase `--chunk-days` to reduce API calls.

**2. Missing Data Days**
```
⚠️  2024-01-15: Insufficient bars: 0 (expected ~390)
```
**Solution**: Likely a market holiday or data outage. Check NYSE calendar.

**3. Connection Errors**
```
❌ Failed to connect to TimescaleDB
```
**Solution**: Verify database is running and .env credentials are correct.

**4. Validation Errors**
```
⚠️  2024-12-24: Insufficient bars: 214 (expected ~390)
```
**Solution**: Likely an early close day. This is expected and not an error.

## Performance

### Benchmark (2-year backfill, Feb 2023 - Jan 2025)

| Metric | Value |
|--------|-------|
| Total bars | ~182,000 |
| Total chunks | ~24 (30 days each) |
| API calls | ~24 |
| Fetch time | ~30 seconds |
| Transform time | ~10 seconds |
| Insert time | ~30 seconds |
| **Total time** | **~1-2 minutes** |

### Optimization Tips

1. **Increase chunk size** for faster backfill:
   ```bash
   --chunk-days 60  # Fewer API calls
   ```

2. **Skip validation** if data quality is trusted:
   ```bash
   --skip-validation  # ~30% faster
   ```

3. **Run during off-peak hours** to avoid rate limits

## Validation

After backfill, verify data:

```python
from quant_vibe.data.timescale_store import TimescaleStore
import pandas as pd

ts = TimescaleStore()

# Query sample
query = """
SELECT
    DATE(timestamp) as date,
    COUNT(*) as bars,
    MIN(close::numeric) as low,
    MAX(close::numeric) as high
FROM underlying_bars
WHERE ticker = 'SPX'
  AND timestamp >= '2024-01-01'
  AND timestamp < '2025-01-01'
GROUP BY DATE(timestamp)
ORDER BY date;
"""

# Should show ~252 trading days with ~390 bars each
```

## Idempotency

The script uses `ON CONFLICT (timestamp, ticker) DO UPDATE`, making it safe to:
- Re-run for the same date range (overwrites existing data)
- Resume interrupted backfills
- Fix corrupted data by re-fetching

Example:
```bash
# Run 1: Backfills 2020
python ... --start-date 2020-01-01 --end-date 2021-01-01

# Run 2: Same command - safely overwrites 2020 data
python ... --start-date 2020-01-01 --end-date 2021-01-01
```

## Troubleshooting

### Check Massive.io API Key
```bash
python -c "from quant_vibe.data.massive_client import MassiveClient; m = MassiveClient(); print('✅ API key valid')"
```

### Check Database Connection
```bash
python -c "from quant_vibe.data.timescale_store import TimescaleStore; t = TimescaleStore(); print('✅ Database connected')"
```

### Check Existing Data
```bash
python scripts/backfill/backfill_massive_spx_index.py \
  --start-date 2015-01-01 \
  --end-date 2025-01-01 \
  --detect-gaps-only
```

## Next Steps

After successful backfill:

1. **Verify data quality**:
   ```sql
   SELECT MIN(timestamp), MAX(timestamp), COUNT(*)
   FROM underlying_bars
   WHERE ticker = 'SPX';
   ```

2. **Test backtesting engine** with the new data

3. **Set up incremental updates** for ongoing data collection

4. **Create continuous aggregates** for higher timeframes (5-min, 15-min, 1-hour)

## Related Scripts

- `backfill_spx_underlying_1min.py` - Schwab API backfill (less historical data)
- `backfill_spx_options.py` - Options data backfill
- `backfill_stream_greeks.py` - Greeks calculation backfill

## Support

For issues or questions:
1. Check this README
2. Review script output for specific error messages
3. Verify prerequisites (API key, database connection)
4. Test with `--dry-run` first
5. Report issues with full error output

---

**Author**: Claude Code
**Date**: 2026-01-10
**API**: Massive.io Custom Bars v2
**Schema**: UnderlyingBar Pydantic model
