# Data Sync Guide

## Overview

The `sync_moirae.py` script syncs options data from a remote TimescaleDB instance (where the real-time collector runs) to your local TimescaleDB for backtesting and analysis.

## Setup

### 1. Add Remote Database Credentials to `.env`

Add these variables to your `.env` file:

```bash
# Remote TimescaleDB (Moirae server)
REMOTE_TIMESCALE_HOST=your-remote-host.com
REMOTE_TIMESCALE_PORT=5432
REMOTE_TIMESCALE_DB=options_data
REMOTE_TIMESCALE_USER=quantvibe
REMOTE_TIMESCALE_PASSWORD=your-remote-password

# Local TimescaleDB (already configured)
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DB=options_data
TIMESCALE_USER=quantvibe
TIMESCALE_PASSWORD=quantvibe_dev
```

**Security Note**: Never commit `.env` to version control! It's already in `.gitignore`.

### 2. Install Dependencies

The script requires `psycopg2` and `python-dotenv`:

```bash
pip install psycopg2-binary python-dotenv
```

## Usage

### Basic Sync

```bash
# Sync last 24 hours (default)
python scripts/sync_moirae.py

# Sync last 3 days
python scripts/sync_moirae.py --days 3

# Sync last 12 hours
python scripts/sync_moirae.py --hours 12
```

### Advanced Sync

```bash
# Sync from specific date
python scripts/sync_moirae.py --since 2025-12-10

# Auto-detect and sync only new data
python scripts/sync_moirae.py --auto
```

### Auto Mode (Recommended)

The `--auto` flag automatically detects the last synced timestamp in your local database and syncs only new data:

```bash
python scripts/sync_moirae.py --auto
```

This is the most efficient method for regular syncs.

## Automated Syncing

### Using Cron (Linux/Mac)

Add to crontab (`crontab -e`):

```bash
# Sync every hour
0 * * * * cd /Users/curisu/dev/quant-vibe && source venv/bin/activate && python scripts/sync_moirae.py --auto >> logs/sync.log 2>&1

# Sync every 4 hours
0 */4 * * * cd /Users/curisu/dev/quant-vibe && source venv/bin/activate && python scripts/sync_moirae.py --auto >> logs/sync.log 2>&1
```

### Using a Shell Script

Create `scripts/auto_sync.sh`:

```bash
#!/bin/bash
cd /Users/curisu/dev/quant-vibe
source venv/bin/activate
python scripts/sync_moirae.py --auto
```

Then run it periodically or add to cron.

## How It Works

1. **Connects** to both remote and local TimescaleDB instances
2. **Queries** remote database for data newer than `since_time`
3. **Fetches** all matching rows (timestamp, OHLCV, Greeks, etc.)
4. **Inserts** into local database in batches (default: 10,000 rows)
5. **Handles duplicates** using `ON CONFLICT DO UPDATE` (upsert)
6. **Shows progress** with row counts and percentages

## Features

### Duplicate Handling

The script uses PostgreSQL's `ON CONFLICT` to handle duplicates:
- If row exists: **Updates** with newer data
- If row new: **Inserts** as normal

This means you can safely run the script multiple times without creating duplicates.

### Batch Inserts

Data is inserted in batches (default 10,000 rows) for performance:
- Faster than row-by-row inserts
- Lower memory usage
- Progress tracking

### Timezone Aware

All timestamps are handled as UTC, matching the database schema and backtest requirements.

## Monitoring

### Check Sync Status

```bash
# View recent syncs
tail -f logs/sync.log

# Check local data status
python scripts/check_data_timezone.py
```

### Database Query

Check what data you have locally:

```sql
-- Recent data summary
SELECT
    DATE(timestamp) as date,
    COUNT(*) as bars,
    MIN(timestamp) as first_bar,
    MAX(timestamp) as last_bar
FROM options_bars
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY DATE(timestamp)
ORDER BY date DESC;

-- Latest synced data
SELECT
    MAX(timestamp) as latest_data,
    COUNT(*) as total_bars
FROM options_bars;
```

## Troubleshooting

### Error: Missing required environment variables

```
❌ ERROR: Missing required environment variables in .env:
   - REMOTE_TIMESCALE_HOST
   - REMOTE_TIMESCALE_PASSWORD
```

**Solution**: Add the missing variables to `.env`

### Error: Failed to connect to remote database

```
❌ Failed to connect to remote database: could not connect to server
```

**Solutions**:
1. Check `REMOTE_TIMESCALE_HOST` is correct
2. Verify remote server is running and accessible
3. Check firewall allows PostgreSQL port (5432)
4. Test connection manually: `psql -h hostname -U quantvibe -d options_data`

### Error: Failed to connect to local database

```
❌ Failed to connect to local database
```

**Solutions**:
1. Ensure Docker container is running: `docker ps`
2. Start TimescaleDB: `docker-compose up -d`
3. Check `TIMESCALE_*` variables in `.env`

### No new data to sync

```
No new data to sync.
```

This is normal if:
- Remote collector hasn't collected new data yet
- You've already synced all available data
- Market is closed

## Performance

### Sync Time Estimates

- **1 hour of data**: ~50,000 bars, ~5-10 seconds
- **1 day of data**: ~800,000 bars, ~60-90 seconds
- **1 week of data**: ~5,000,000 bars, ~5-10 minutes

Actual times depend on:
- Network speed between remote and local
- Database load
- Number of contracts being tracked

### Optimization Tips

1. **Use --auto for regular syncs** - Only fetches new data
2. **Sync during off-hours** - Less database contention
3. **Increase batch_size** - Edit script to use larger batches (e.g., 50,000)
4. **Filter by ticker** - Modify query to sync only specific symbols

## Data Integrity

### Verification

After syncing, verify data integrity:

```python
# scripts/verify_sync.py
from quant_vibe.data.timescale_store import TimescaleStore

ts = TimescaleStore()

# Check for gaps in data
query = """
SELECT
    timestamp,
    LAG(timestamp) OVER (ORDER BY timestamp) as prev_timestamp,
    timestamp - LAG(timestamp) OVER (ORDER BY timestamp) as gap
FROM (
    SELECT DISTINCT timestamp
    FROM options_bars
    WHERE DATE(timestamp) = '2025-12-16'
    ORDER BY timestamp
) t
WHERE timestamp - LAG(timestamp) OVER (ORDER BY timestamp) > INTERVAL '2 minutes';
"""

with ts.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(query)
        gaps = cur.fetchall()

        if gaps:
            print(f"Found {len(gaps)} gaps in data:")
            for gap in gaps:
                print(f"  {gap[0]} (gap: {gap[2]})")
        else:
            print("No gaps found - data looks good!")
```

## Example Output

```
✅ Configuration loaded from /Users/curisu/dev/quant-vibe/.env
   Remote: quantvibe@moirae.example.com:5432/options_data
   Local:  quantvibe@localhost:5432/options_data

======================================================================
SYNCING OPTIONS DATA FROM REMOTE
======================================================================
Since: 2025-12-16 00:00:00+00:00
Batch size: 10,000

1. Connecting to remote database...
   ✅ Connected to moirae.example.com

2. Connecting to local database...
   ✅ Connected to localhost

3. Querying remote data since 2025-12-16 00:00:00+00:00...
   ✅ Fetched 796,739 rows from remote

4. Inserting into local database...
   Progress: 10,000/796,739 (1.3%)
   Progress: 20,000/796,739 (2.5%)
   Progress: 30,000/796,739 (3.8%)
   ...
   Progress: 796,739/796,739 (100.0%)

   ✅ Successfully synced 796,739 rows

   Date range: 2025-12-16 06:27:00+00:00 to 2025-12-16 14:13:00+00:00

======================================================================
SYNC COMPLETE
======================================================================
```

## Related Scripts

- `scripts/check_data_timezone.py` - Diagnose timezone and data availability issues
- `scripts/test_0dte_availability.py` - Check 0 DTE data coverage
- `backtests/backtest_bullish_vertical_put.py` - Run backtests with synced data

## Support

For issues or questions:
1. Check logs: `logs/sync.log`
2. Verify configuration: `cat .env | grep TIMESCALE`
3. Test database connections manually
4. Review this guide's troubleshooting section
