# SPX Underlying Data Backfill Scripts

This directory contains scripts for backfilling historical $SPX 1-minute bars into the `underlying_bars` TimescaleDB table.

## Overview

The backfill system automatically detects and fills gaps in underlying price data, ensuring you have complete and consistent market data for backtesting and analysis.

**Key Features:**
- 🔍 **Automatic gap detection** - Scans for missing or incomplete trading days
- 🕐 **Market-hours aware** - Respects 9:30 AM - 4:00 PM EST trading hours
- 🌍 **Timezone handling** - Properly converts EST ↔ UTC
- ♻️ **Idempotent** - Safe to run multiple times (uses ON CONFLICT)
- 📊 **Statistics reporting** - Shows complete/incomplete/missing days

## Quick Start

### Basic Usage

```bash
# Scan last 7 days and backfill gaps (default)
python scripts/backfill/backfill_spx_underlying_1min.py

# Backfill today only
python scripts/backfill/backfill_spx_underlying_1min.py --today

# Scan specific date range
python scripts/backfill/backfill_spx_underlying_1min.py --start-date 2025-12-01 --end-date 2025-12-30
```

### Advanced Options

```bash
# Show stats only (no backfill)
python scripts/backfill/backfill_spx_underlying_1min.py --stats-only

# Dry run (show gaps without fetching/inserting)
python scripts/backfill/backfill_spx_underlying_1min.py --dry-run

# Custom chunk size (useful for large date ranges)
python scripts/backfill/backfill_spx_underlying_1min.py --chunk-days 14
```

## How It Works

### 1. Gap Detection

The script scans the specified date range and identifies:

- **Missing days** - Trading days with 0 bars in database
- **Incomplete days** - Trading days with < 80% of expected bars (< 312 out of 390)

Expected bars per trading day: **390 bars** (9:30 AM - 4:00 PM EST = 6.5 hours × 60 minutes)

### 2. Backfilling

For each gap detected:
1. Fetches 1-minute OHLCV data from Schwab API
2. Converts to proper format (handles case sensitivity)
3. Inserts into `underlying_bars` table using `ON CONFLICT` (safe to re-run)
4. Rate limits to 1 request/second to respect API limits

### 3. Verification

After backfilling, the script shows:
- Total bars fetched and inserted
- Any errors encountered
- Sample data from first/last bars

## Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--start-date YYYY-MM-DD` | Start date for gap scan | 7 days ago |
| `--end-date YYYY-MM-DD` | End date for gap scan | Today |
| `--today` | Backfill today only | False |
| `--stats-only` | Show statistics without backfilling | False |
| `--dry-run` | Show gaps without fetching/inserting | False |
| `--chunk-days N` | Days per API request (max 30) | 30 |

## Examples

### Daily Backfill (Cron Job)

Run this daily to keep data up to date:

```bash
# Add to crontab (runs at 5 PM EST daily)
0 17 * * 1-5 cd /path/to/quant-vibe && python scripts/backfill/backfill_spx_underlying_1min.py --today >> logs/backfill.log 2>&1
```

### Check for Gaps

See what's missing without fetching:

```bash
python scripts/backfill/backfill_spx_underlying_1min.py --start-date 2025-12-01 --end-date 2025-12-30 --stats-only
```

Output:
```
================================================================================
DETECTING GAPS IN UNDERLYING_BARS
================================================================================
Scan range: 2025-12-01 to 2025-12-30

Expected trading days in range: 22

✅ Complete days: 18

❌ Missing days (3):
   2025-12-05
   2025-12-12
   2025-12-19

⚠️  Incomplete days (1):
   2025-12-23: 198/390 bars (50.8%)

Total gaps to backfill: 4
```

### Backfill Specific Date Range

```bash
# Backfill December 2025
python scripts/backfill/backfill_spx_underlying_1min.py --start-date 2025-12-01 --end-date 2025-12-31
```

### Test Without Modifying Database

```bash
# Dry run - see what would happen without inserting
python scripts/backfill/backfill_spx_underlying_1min.py --dry-run
```

## Technical Details

### Database Schema

Data is inserted into the `underlying_bars` table:

```sql
CREATE TABLE underlying_bars (
    timestamp TIMESTAMPTZ NOT NULL,
    ticker TEXT NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    vwap DOUBLE PRECISION,
    transactions INTEGER,
    data_source TEXT,
    PRIMARY KEY (timestamp, ticker)
);
```

### Column Name Handling

**Important:** The Schwab API returns capitalized column names (`Open`, `High`, `Low`, `Close`, `Volume`), but the database uses lowercase column names (`open`, `high`, `low`, `close`, `volume`).

The script handles this conversion automatically:

```python
# Schwab API returns: Open, High, Low, Close, Volume (capitalized)
# Database expects: open, high, low, close, volume (lowercase)

bars.append({
    'timestamp': timestamp.to_pydatetime(),
    'ticker': 'SPX',
    'open': float(row['Open']),     # Convert from capitalized
    'high': float(row['High']),
    'low': float(row['Low']),
    'close': float(row['Close']),
    'volume': int(row['Volume']),
    'data_source': 'schwab'
})
```

### Market Hours & Timezone

- **Market hours:** 9:30 AM - 4:00 PM EST
- **Database storage:** UTC timestamps
- **Conversion:** Script automatically converts EST → UTC

Example for December 23, 2025:
- EST market open: 2025-12-23 09:30:00 EST
- UTC equivalent: 2025-12-23 14:30:00 UTC
- EST market close: 2025-12-23 16:00:00 EST
- UTC equivalent: 2025-12-23 21:00:00 UTC

### Schwab API Limits

- **1-minute data:** Maximum ~30 days per request
- **Rate limiting:** Script waits 1 second between requests
- **Chunking:** Large date ranges are automatically split into 30-day chunks

## Troubleshooting

### No data returned for today

**Reason:** Market hasn't closed yet or today is a weekend/holiday.

**Solution:** Run after 4 PM EST or use `--start-date` for past dates.

### Column name errors (KeyError: 'Low')

**Reason:** Mismatch between API column names (capitalized) and database columns (lowercase).

**Solution:** This is fixed in the current version. If you see this error, update your script.

### Connection errors

**Reason:** TimescaleDB not running or credentials incorrect.

**Solution:**
```bash
# Check if database is running
docker ps | grep timescale

# Check connection settings in .env
cat .env | grep TIMESCALE
```

### Incomplete days showing 0% coverage

**Reason:** Data exists but query didn't find it (timezone issue).

**Solution:** The script now properly handles timezone conversions. Re-run the backfill.

## Best Practices

1. **Run daily** - Keep data fresh by running daily after market close (5 PM EST)
2. **Monitor logs** - Save output to log files for debugging
3. **Use --stats-only first** - Check what's missing before backfilling large ranges
4. **Test with --dry-run** - Verify behavior before inserting data
5. **Check existing data** - Use `--stats-only` to see current coverage

## Related Scripts

- `backfill_0dte_spxw.py` - Backfill options data (different table)
- `sync_moirae.py` - Sync from remote database
- `analyze_data_gaps.py` - Comprehensive gap analysis tool

## Support

If you encounter issues:
1. Check logs for detailed error messages
2. Verify database connection (`docker ps`)
3. Check API credentials (`.env` file)
4. Review Schwab API limits and quotas

For questions or bugs, see the main project documentation.
