# Data Sync Guide: Remote to Local TimescaleDB

This guide explains how to efficiently sync options data from your remote TimescaleDB instance (Moirae) to your local development database.

## Overview

The sync workflow consists of three main tools:

1. **`analyze_data_gaps.py`** - Identifies missing or incomplete data
2. **`sync_moirae.py`** - Syncs data from remote to local
3. **`auto_sync_gaps.sh`** - Automated workflow (analyze → sync)

## Quick Start

### 1. Automated Sync (Recommended)

The easiest way to sync is using the automated workflow:

```bash
# Interactive mode (asks for confirmation before syncing)
./scripts/auto_sync_gaps.sh

# Quick scan (last 30 days only)
./scripts/auto_sync_gaps.sh --quick

# Automatic mode (no confirmation)
./scripts/auto_sync_gaps.sh --auto

# Specific date range
./scripts/auto_sync_gaps.sh --since 2025-12-01 --until 2025-12-31
```

### 2. Manual Analysis + Sync

For more control, use the tools separately:

```bash
# Step 1: Analyze gaps
python scripts/analyze_data_gaps.py --quick --detailed

# Step 2: Generate sync commands
python scripts/analyze_data_gaps.py --quick --generate-sync-commands --output /tmp/sync.sh

# Step 3: Review and execute
cat /tmp/sync.sh
chmod +x /tmp/sync.sh
/tmp/sync.sh
```

## Gap Analysis Tool

### Usage

```bash
python scripts/analyze_data_gaps.py [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--quick` | Quick scan (last 30 days) |
| `--since YYYY-MM-DD` | Start date for analysis |
| `--until YYYY-MM-DD` | End date for analysis |
| `--ticker SYMBOL` | Underlying ticker (default: SPX) |
| `--detailed` | Show detailed gap information |
| `--generate-sync-commands` | Generate sync commands for gaps |
| `--output FILE` | Save sync commands to file |

### Examples

```bash
# Quick overview (last 30 days)
python scripts/analyze_data_gaps.py --quick

# Detailed analysis for December 2025
python scripts/analyze_data_gaps.py --since 2025-12-01 --until 2025-12-31 --detailed

# Generate sync commands for all gaps
python scripts/analyze_data_gaps.py --generate-sync-commands

# Save sync commands to script
python scripts/analyze_data_gaps.py --quick --generate-sync-commands --output /tmp/sync_gaps.sh
```

### Gap Types

The tool identifies three types of gaps:

1. **Missing Days** - Entire trading days with no local data
   - Remote has data, local has zero bars
   - Priority: HIGH (complete data loss)

2. **Partial Days** - Days with <80% bar coverage
   - Remote: 700,000 bars, Local: 50,000 bars (7% coverage)
   - Priority: MEDIUM (incomplete data)

3. **Sparse Contracts** - Days with <80% contract coverage
   - Remote: 2,500 contracts, Local: 500 contracts (20% coverage)
   - Priority: LOW (missing some option chains)

### Output Example

```
======================================================================
GAP ANALYSIS SUMMARY
======================================================================

❌ MISSING DAYS: 2 days with no local data
   2025-12-29: 842,661 bars, 2,716 contracts
   2025-12-26: 708,386 bars, 2,915 contracts

⚠️  PARTIAL DAYS: 4 days with <80% coverage
   2025-12-25: 3.7% (2,193/59,394 bars)
   2025-12-24: 53.1% (45,418/85,454 bars)

⚠️  SPARSE CONTRACTS: 1 days with <80% contracts
   2025-12-22: 28.7% (745/2,594 contracts)

======================================================================
SUGGESTED SYNC COMMANDS
======================================================================
python scripts/sync_moirae.py --since 2025-12-29 --until 2025-12-30
python scripts/sync_moirae.py --since 2025-12-26 --until 2025-12-27
python scripts/sync_moirae.py --since 2025-12-25 --until 2025-12-26
======================================================================
```

## Sync Tool

### Usage

```bash
python scripts/sync_moirae.py [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--since YYYY-MM-DD` | Sync data from this date |
| `--until YYYY-MM-DD` | Sync data until this date (exclusive) |
| `--hours N` | Sync last N hours |
| `--days N` | Sync last N days |
| `--auto` | Auto-detect last sync time |
| `--batch-days N` | Split large ranges into N-day batches (default: 7) |

### Examples

```bash
# Sync last 24 hours (default)
python scripts/sync_moirae.py

# Sync last 7 days
python scripts/sync_moirae.py --days 7

# Sync specific date range
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31

# Auto-detect and sync missing data
python scripts/sync_moirae.py --auto

# Large date range (automatically batched into 7-day chunks)
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31

# Custom batch size for large ranges
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31 --batch-days 14
```

### Batch Processing

For large date ranges, the sync tool automatically splits the work into batches:

```bash
# This will sync 180 days in 26 batches of 7 days each
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31

# Output:
# 📦 Large date range detected. Splitting into 7-day batches...
#
# BATCH 1: 2025-06-01 to 2025-06-08
# BATCH 2: 2025-06-08 to 2025-06-15
# ...
```

### Conflict Handling

The sync tool uses PostgreSQL's `ON CONFLICT` to handle duplicates:

- If a bar already exists (same timestamp + option_ticker), it **updates** the values
- This means re-syncing a date range is safe and idempotent
- Useful for fixing partial/corrupted data

## Automated Workflow

### Usage

```bash
./scripts/auto_sync_gaps.sh [OPTIONS]
```

### Options

| Option | Description |
|--------|-------------|
| `--auto` | Auto-execute without confirmation |
| `--quick` | Quick scan (last 30 days) |
| `--since YYYY-MM-DD` | Start date for analysis |
| `--until YYYY-MM-DD` | End date for analysis |

### Examples

```bash
# Interactive mode (default)
# - Analyzes gaps
# - Shows sync commands
# - Asks for confirmation before running
./scripts/auto_sync_gaps.sh

# Quick scan + interactive
./scripts/auto_sync_gaps.sh --quick

# Fully automated (no prompts)
./scripts/auto_sync_gaps.sh --auto

# Specific date range + auto
./scripts/auto_sync_gaps.sh --since 2025-12-01 --until 2025-12-31 --auto
```

### Workflow Steps

1. **Analyze** - Identifies gaps using `analyze_data_gaps.py`
2. **Generate** - Creates sync commands for all gaps
3. **Execute** - Runs sync commands (with or without confirmation)
4. **Cleanup** - Removes temporary files

### Output Example

```
======================================================================
AUTOMATIC GAP SYNC WORKFLOW
======================================================================

Step 1: Analyzing data gaps...
✅ Sync commands saved to: /tmp/sync_gaps_1234567890.sh

Step 2: Found 6 sync operations

Generated sync commands:
----------------------------------------
python scripts/sync_moirae.py --since 2025-12-29 --until 2025-12-30
python scripts/sync_moirae.py --since 2025-12-26 --until 2025-12-27
...
----------------------------------------

Step 3: Ready to execute sync commands

Execute these sync commands? (y/n):
```

## Environment Configuration

### Required Variables

Make sure these are set in your `.env` file:

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

## Performance Tips

### 1. Batch Size

The default batch size is 10,000 rows per insert. Adjust for your network:

```python
# In sync_moirae.py (advanced users)
sync_options_bars(since_time=..., batch_size=50000)  # Faster on fast networks
```

### 2. Network Optimization

For large syncs over slow networks:

```bash
# Use smaller date ranges
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-08  # 1 week

# Let it batch automatically
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31 --batch-days 3
```

### 3. Continuous Aggregates

After syncing raw data, refresh TimescaleDB continuous aggregates:

```bash
# Connect to local database
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data

# Refresh aggregates
CALL refresh_continuous_aggregate('options_bars_5min', NULL, NULL);
CALL refresh_continuous_aggregate('options_bars_15min', NULL, NULL);
CALL refresh_continuous_aggregate('options_bars_1hour', NULL, NULL);
CALL refresh_continuous_aggregate('options_bars_daily', NULL, NULL);
```

Or let the automatic refresh policies handle it (may take up to 5-15 minutes).

## Common Workflows

### Daily Sync

Recommended: Run once per day to keep local database current.

```bash
# Quick automated sync
./scripts/auto_sync_gaps.sh --auto

# Or use cron
0 6 * * * cd /path/to/quant-vibe && ./scripts/auto_sync_gaps.sh --auto >> logs/daily_sync.log 2>&1
```

### Historical Backfill

Syncing large historical ranges (e.g., 6 months):

```bash
# Method 1: Let auto-batching handle it
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31

# Method 2: Monthly batches (more control)
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-07-01
python scripts/sync_moirae.py --since 2025-07-01 --until 2025-08-01
python scripts/sync_moirae.py --since 2025-08-01 --until 2025-09-01
# ... etc
```

### Fixing Corrupted Data

If you suspect data corruption on specific dates:

```bash
# Re-sync specific days (will update existing bars)
python scripts/sync_moirae.py --since 2025-12-15 --until 2025-12-16

# Verify fix
python scripts/analyze_data_gaps.py --since 2025-12-15 --until 2025-12-16 --detailed
```

### Validation After Sync

Always validate after large syncs:

```bash
# Check data coverage
python scripts/analyze_data_gaps.py --quick --detailed

# Check database stats
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -c "
SELECT
    COUNT(*) as total_bars,
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest,
    COUNT(DISTINCT DATE(timestamp)) as unique_days,
    COUNT(DISTINCT option_ticker) as unique_contracts
FROM options_bars;
"
```

## Troubleshooting

### Connection Issues

```
❌ Failed to connect to remote database
```

**Solution:**
1. Check `.env` file has correct `REMOTE_TIMESCALE_*` variables
2. Verify network connectivity: `ping 192.168.100.197`
3. Test database access: `psql -h 192.168.100.197 -U quantvibe -d options_data`

### No Data Fetched

```
✅ Fetched 0 rows from remote
No new data to sync.
```

**Causes:**
1. Remote database has no data for the specified date range
2. Local database is already up-to-date
3. Date range is outside market hours (weekends, holidays)

**Solution:**
- Check remote database: `python scripts/analyze_data_gaps.py --detailed`
- Verify date range includes trading days (Mon-Fri, not holidays)

### Slow Syncs

Large syncs (millions of rows) can take time. Optimize:

1. Use smaller batches: `--batch-days 3`
2. Increase batch size (advanced): Edit `batch_size=50000` in script
3. Run during off-peak hours
4. Consider direct database dump/restore for very large datasets:

```bash
# On remote server
pg_dump -h localhost -U quantvibe -d options_data \
    -t options_bars --data-only > options_data.sql

# Transfer file to local machine
scp user@remote:/path/options_data.sql .

# On local machine
psql -h localhost -U quantvibe -d options_data < options_data.sql
```

## Advanced Usage

### Custom Gap Detection

Modify `analyze_data_gaps.py` for custom gap detection logic:

```python
# Example: Find days with <50% coverage instead of <80%
if coverage_pct < 50:  # Changed from 80
    gaps['partial_days'].append(...)
```

### Selective Syncing

Sync only specific contracts or time ranges:

```python
# Edit sync_moirae.py query to add WHERE filters
cur.execute("""
    SELECT ...
    FROM options_bars
    WHERE timestamp >= %s AND timestamp < %s
    AND option_ticker LIKE 'SPXW251231%'  -- Only Dec 31 contracts
    ORDER BY timestamp ASC
""", (since_time, until_time))
```

### Monitoring Sync Progress

The sync tool shows real-time progress:

```
Progress: 10,000/842,661 (1.2%)
Progress: 20,000/842,661 (2.4%)
Progress: 30,000/842,661 (3.6%)
...
```

For long-running syncs, redirect to log file:

```bash
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31 > sync.log 2>&1 &

# Monitor progress
tail -f sync.log
```

## Best Practices

1. **Run gap analysis before syncing** - Know what you're syncing
2. **Use batching for large ranges** - More reliable than one huge query
3. **Validate after sync** - Check data integrity with analysis tool
4. **Automate daily syncs** - Keep local database current
5. **Monitor disk space** - Options data grows quickly (1M+ bars/day)
6. **Refresh aggregates** - Keep continuous aggregates up-to-date

## Summary

| Task | Command |
|------|---------|
| Quick sync | `./scripts/auto_sync_gaps.sh --quick --auto` |
| Analyze gaps | `python scripts/analyze_data_gaps.py --quick --detailed` |
| Sync specific date | `python scripts/sync_moirae.py --since 2025-12-15 --until 2025-12-16` |
| Historical backfill | `python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31` |
| Auto-detect and sync | `python scripts/sync_moirae.py --auto` |

For most use cases, the automated workflow is recommended:

```bash
./scripts/auto_sync_gaps.sh --auto
```

This will analyze, generate commands, and sync all gaps in one command.
