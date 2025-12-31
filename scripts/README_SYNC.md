# Data Sync Scripts

Scripts for syncing options data between remote (Moirae) and local TimescaleDB instances.

## Quick Start

```bash
# Automated sync (one command)
./scripts/auto_sync_gaps.sh --auto

# Check what needs syncing (no execution)
python scripts/analyze_data_gaps.py --quick --detailed
```

## Scripts Overview

### 1. `auto_sync_gaps.sh` (Recommended)

**Purpose:** Automated workflow combining gap analysis and sync.

**Usage:**
```bash
./scripts/auto_sync_gaps.sh [OPTIONS]
```

**Options:**
- `--auto` - Execute without confirmation
- `--quick` - Scan last 30 days only
- `--since YYYY-MM-DD` - Start date
- `--until YYYY-MM-DD` - End date

**Examples:**
```bash
# Interactive (shows commands, asks confirmation)
./scripts/auto_sync_gaps.sh

# Fully automated
./scripts/auto_sync_gaps.sh --auto

# Quick scan (30 days)
./scripts/auto_sync_gaps.sh --quick --auto

# Specific date range
./scripts/auto_sync_gaps.sh --since 2025-12-01 --until 2025-12-31
```

**What it does:**
1. Analyzes gaps between remote and local
2. Generates sync commands
3. Executes syncs (with or without confirmation)
4. Cleans up temporary files

---

### 2. `analyze_data_gaps.py`

**Purpose:** Identify missing or incomplete data.

**Usage:**
```bash
python scripts/analyze_data_gaps.py [OPTIONS]
```

**Options:**
- `--quick` - Last 30 days
- `--since YYYY-MM-DD` - Start date
- `--until YYYY-MM-DD` - End date
- `--ticker SYMBOL` - Underlying ticker (default: SPX)
- `--detailed` - Show detailed gap information
- `--generate-sync-commands` - Generate sync commands
- `--output FILE` - Save commands to file

**Examples:**
```bash
# Quick overview
python scripts/analyze_data_gaps.py --quick

# Detailed analysis
python scripts/analyze_data_gaps.py --quick --detailed

# Specific date range
python scripts/analyze_data_gaps.py --since 2025-12-01 --until 2025-12-31

# Generate sync commands
python scripts/analyze_data_gaps.py --quick --generate-sync-commands

# Save to file
python scripts/analyze_data_gaps.py --quick --generate-sync-commands --output /tmp/sync.sh
```

**Gap Types Detected:**
- **Missing Days:** Days with no local data
- **Partial Days:** Days with <80% bar coverage
- **Sparse Contracts:** Days with <80% contract coverage

**Output:**
```
❌ MISSING DAYS: 2 days with no local data
   2025-12-29: 842,661 bars, 2,716 contracts
   2025-12-26: 708,386 bars, 2,915 contracts

⚠️  PARTIAL DAYS: 4 days with <80% coverage
   2025-12-25: 3.7% (2,193/59,394 bars)

SUGGESTED SYNC COMMANDS
python scripts/sync_moirae.py --since 2025-12-29 --until 2025-12-30
python scripts/sync_moirae.py --since 2025-12-26 --until 2025-12-27
```

---

### 3. `sync_moirae.py`

**Purpose:** Sync data from remote to local with conflict handling.

**Usage:**
```bash
python scripts/sync_moirae.py [OPTIONS]
```

**Options:**
- `--since YYYY-MM-DD` - Start date
- `--until YYYY-MM-DD` - End date (exclusive)
- `--hours N` - Last N hours
- `--days N` - Last N days
- `--auto` - Auto-detect last sync time
- `--batch-days N` - Batch size for large ranges (default: 7)

**Examples:**
```bash
# Sync last 24 hours (default)
python scripts/sync_moirae.py

# Sync last 7 days
python scripts/sync_moirae.py --days 7

# Sync specific date range
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31

# Auto-detect missing data
python scripts/sync_moirae.py --auto

# Large range (auto-batched)
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31
```

**Features:**
- **Idempotent:** Safe to re-run (uses `ON CONFLICT UPDATE`)
- **Batching:** Large ranges split into manageable chunks
- **Progress tracking:** Real-time progress updates
- **Conflict handling:** Updates existing bars, inserts new ones

**Output:**
```
SYNCING OPTIONS DATA FROM REMOTE
Since: 2025-12-29 00:00:00+00:00
Until: 2025-12-30 00:00:00+00:00
Batch size: 10,000

1. Connecting to remote database...
   ✅ Connected to 192.168.100.197

2. Connecting to local database...
   ✅ Connected to localhost

3. Querying remote data...
   ✅ Fetched 842,661 rows from remote

4. Inserting into local database...
   Progress: 100,000/842,661 (11.9%)
   Progress: 200,000/842,661 (23.7%)
   ...
   ✅ Successfully synced 842,661 rows

   Date range: 2025-12-29 to 2025-12-29

SYNC COMPLETE
```

---

## Common Workflows

### Daily Sync

Keep local database current:

```bash
# Add to crontab
crontab -e

# Add line (6 AM daily)
0 6 * * * cd /path/to/quant-vibe && ./scripts/auto_sync_gaps.sh --auto >> logs/daily_sync.log 2>&1
```

### Historical Backfill

Sync large date range:

```bash
# Automatically batched into 7-day chunks
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31
```

### Fix Corrupted Data

Re-sync specific dates:

```bash
# Safe to re-run (uses ON CONFLICT UPDATE)
python scripts/sync_moirae.py --since 2025-12-15 --until 2025-12-16
```

### Validation

Check sync success:

```bash
# Analyze gaps
python scripts/analyze_data_gaps.py --quick --detailed

# Database stats
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -c "
SELECT
    COUNT(*) as total_bars,
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest,
    COUNT(DISTINCT DATE(timestamp)) as unique_days
FROM options_bars;"
```

---

## Configuration

### Environment Variables

Required in `.env`:

```bash
# Remote database (Moirae)
REMOTE_TIMESCALE_HOST=192.168.100.197
REMOTE_TIMESCALE_PORT=5432
REMOTE_TIMESCALE_DB=options_data
REMOTE_TIMESCALE_USER=quantvibe
REMOTE_TIMESCALE_PASSWORD=your-password

# Local database
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DB=options_data
TIMESCALE_USER=quantvibe
TIMESCALE_PASSWORD=quantvibe_dev
```

### Network Requirements

- Remote database must be reachable from local machine
- Port 5432 must be open
- VPN or direct network access required

Test connectivity:

```bash
# Ping test
ping 192.168.100.197

# Database connection test
psql -h 192.168.100.197 -U quantvibe -d options_data -c "SELECT 1;"
```

---

## Troubleshooting

### Connection Failed

```
❌ Failed to connect to remote database
```

**Solutions:**
1. Check `.env` file has correct credentials
2. Verify network connectivity: `ping 192.168.100.197`
3. Test database: `psql -h 192.168.100.197 -U quantvibe -d options_data`
4. Check VPN connection if applicable

### No Data to Sync

```
✅ Fetched 0 rows from remote
No new data to sync.
```

**Causes:**
- Local database already current
- Date range outside trading hours
- Remote has no data for period

**Check:**
```bash
python scripts/analyze_data_gaps.py --quick --detailed
```

### Slow Performance

**Optimizations:**
```bash
# Smaller batches
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31 --batch-days 3

# Monitor progress
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31 > sync.log 2>&1 &
tail -f sync.log
```

---

## Advanced Usage

### Custom Batch Size

For very fast networks, increase batch size (edit script):

```python
sync_options_bars(since_time=..., batch_size=50000)  # Default: 10000
```

### Selective Syncing

Edit SQL query in `sync_moirae.py` to add filters:

```python
cur.execute("""
    SELECT ...
    FROM options_bars
    WHERE timestamp >= %s AND timestamp < %s
    AND option_ticker LIKE 'SPXW251231%'  -- Only specific contracts
    ORDER BY timestamp ASC
""", (since_time, until_time))
```

### Continuous Aggregates

After large syncs, refresh aggregates:

```bash
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data <<EOF
CALL refresh_continuous_aggregate('options_bars_5min', NULL, NULL);
CALL refresh_continuous_aggregate('options_bars_15min', NULL, NULL);
CALL refresh_continuous_aggregate('options_bars_1hour', NULL, NULL);
CALL refresh_continuous_aggregate('options_bars_daily', NULL, NULL);
EOF
```

---

## Documentation

- **Quick Start:** `docs/SYNC_QUICKSTART.md`
- **Complete Guide:** `docs/DATA_SYNC_GUIDE.md`
- **Project Docs:** `CLAUDE.md` (Data Sync section)

---

## Summary

| Task | Command |
|------|---------|
| **Quick sync** | `./scripts/auto_sync_gaps.sh --auto` |
| **Check gaps** | `python scripts/analyze_data_gaps.py --quick` |
| **Sync last week** | `python scripts/sync_moirae.py --days 7` |
| **Sync date range** | `python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31` |
| **Fix specific day** | `python scripts/sync_moirae.py --since 2025-12-15 --until 2025-12-16` |

For most use cases, the automated workflow is recommended:

```bash
./scripts/auto_sync_gaps.sh --auto
```
