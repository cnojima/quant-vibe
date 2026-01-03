# Data Sync Quick Start

## TL;DR

Sync data from remote (Moirae) to local in one command:

```bash
./scripts/auto_sync_gaps.sh --auto
```

## What This Does

1. **Analyzes** your local database and compares it to remote
2. **Identifies** three types of gaps:
   - Missing days (no data at all)
   - Partial days (<80% coverage)
   - Sparse contracts (<80% of option chains)
3. **Generates** sync commands for all gaps
4. **Executes** the sync automatically

## Usage

### Daily Sync (Recommended)

Run once per day to stay current:

```bash
./scripts/auto_sync_gaps.sh --auto
```

Add to cron for automation:

```bash
# Edit crontab
crontab -e

# Add line (runs at 6 AM daily)
0 6 * * * cd /path/to/quant-vibe && ./scripts/auto_sync_gaps.sh --auto >> logs/daily_sync.log 2>&1
```

### Interactive Mode

Preview commands before running:

```bash
./scripts/auto_sync_gaps.sh
```

This will:
1. Show you what gaps exist
2. Display sync commands
3. Ask for confirmation before executing

### Quick Scan

Analyze only the last 30 days:

```bash
./scripts/auto_sync_gaps.sh --quick --auto
```

### Specific Date Range

Sync a specific time period:

```bash
./scripts/auto_sync_gaps.sh --since 2025-12-01 --until 2025-12-31 --auto
```

## Manual Workflow

For more control, use the tools separately:

### 1. Analyze Gaps

```bash
# Quick overview
python scripts/analyze_data_gaps.py --quick

# Detailed analysis
python scripts/analyze_data_gaps.py --quick --detailed

# Specific date range
python scripts/analyze_data_gaps.py --since 2025-12-01 --until 2025-12-31 --detailed
```

### 2. Generate Sync Commands

```bash
# Generate and display commands
python scripts/analyze_data_gaps.py --quick --generate-sync-commands

# Save to file
python scripts/analyze_data_gaps.py --quick --generate-sync-commands --output /tmp/sync.sh
```

### 3. Execute Sync

```bash
# Run individual sync commands
python scripts/sync_moirae.py --since 2025-12-29 --until 2025-12-30

# Or run generated script
chmod +x /tmp/sync.sh
/tmp/sync.sh
```

## Understanding the Output

### Gap Analysis

```
❌ MISSING DAYS: 2 days with no local data
   2025-12-29: 842,661 bars, 2,716 contracts
   2025-12-26: 708,386 bars, 2,915 contracts
```

These days have zero data locally. **High priority.**

```
⚠️  PARTIAL DAYS: 4 days with <80% coverage
   2025-12-25: 3.7% (2,193/59,394 bars)
```

These days have some data but are incomplete. **Medium priority.**

```
⚠️  SPARSE CONTRACTS: 1 days with <80% contracts
   2025-12-22: 28.7% (745/2,594 contracts)
```

These days are missing many option contracts. **Low priority** (usually specific strikes/expirations).

### Sync Progress

```
Progress: 100,000/842,661 (11.9%)
Progress: 200,000/842,661 (23.7%)
...
```

Real-time progress as data syncs. Large syncs can take several minutes.

## Common Scenarios

### First Time Setup

Sync entire historical dataset:

```bash
# This will automatically batch into 7-day chunks
python scripts/sync_moirae.py --since 2025-06-01 --until 2025-12-31
```

### After Extended Absence

Catch up after being offline:

```bash
./scripts/auto_sync_gaps.sh --auto
```

The tool auto-detects what's missing.

### Fixing Corrupted Data

Re-sync specific dates (safe, uses `ON CONFLICT`):

```bash
python scripts/sync_moirae.py --since 2025-12-15 --until 2025-12-16
```

### Keeping Current

Run daily sync automatically:

```bash
# Set and forget
crontab -e
# Add: 0 6 * * * cd /path/to/quant-vibe && ./scripts/auto_sync_gaps.sh --auto
```

## Troubleshooting

### "Failed to connect to remote database"

Check `.env` file has:

```bash
REMOTE_TIMESCALE_HOST=192.168.100.197
REMOTE_TIMESCALE_PASSWORD=your-password
```

Test connection:

```bash
psql -h 192.168.100.197 -U quantvibe -d options_data
```

### "No new data to sync"

Either:
- Local database is already current
- Date range has no data (weekends, holidays)
- Remote has no data for that period

Verify with:

```bash
python scripts/analyze_data_gaps.py --quick --detailed
```

### Slow Syncs

Large syncs (millions of rows) take time. Optimize:

```bash
# Smaller date ranges
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-08

# Let auto-batching handle it
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31 --batch-days 3
```

## Best Practices

1. ✅ **Run daily syncs** - Keeps data current automatically
2. ✅ **Use `--auto` flag** - For unattended operation
3. ✅ **Check logs** - Monitor for errors in cron jobs
4. ✅ **Validate after large syncs** - Run gap analysis to confirm
5. ✅ **Use batching for large ranges** - More reliable than one huge query

## Need More Details?

See `docs/DATA_SYNC_GUIDE.md` for comprehensive documentation including:
- Advanced usage
- Performance tuning
- Custom gap detection
- Database validation queries
- Complete troubleshooting guide

## Quick Reference

| Task | Command |
|------|---------|
| Daily sync | `./scripts/auto_sync_gaps.sh --auto` |
| Check gaps | `python scripts/analyze_data_gaps.py --quick` |
| Sync last week | `python scripts/sync_moirae.py --days 7` |
| Sync date range | `python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31` |
| Fix specific day | `python scripts/sync_moirae.py --since 2025-12-15 --until 2025-12-16` |
