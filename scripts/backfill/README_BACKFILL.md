# Backfill Stream Greeks - Quick Reference

## Purpose

Fill in missing Greeks, strike price, and implied volatility for existing streaming data records that have NULL values for these fields.

## When to Use

- ✅ After adding enrichment to streaming (backfill old data)
- ✅ After stream downtime (fill gaps)
- ✅ Periodic maintenance (ensure complete data)
- ✅ **Off-market hours** (safe to run anytime)

## Quick Start

### 1. Check What Needs Backfilling

```bash
python scripts/backfill_stream_greeks.py --stats-only
```

### 2. Dry Run (Preview Changes)

```bash
python scripts/backfill_stream_greeks.py --dry-run
```

### 3. Run Backfill

```bash
# Backfill all missing data
python scripts/backfill_stream_greeks.py

# Backfill specific date range
python scripts/backfill_stream_greeks.py --start 2025-12-10 --end 2025-12-17

# Limit to 1000 records (for testing)
python scripts/backfill_stream_greeks.py --limit 1000
```

## How It Works

```
Database Query → Fetch Option Chain → Build Cache → Update Records → Show Results
     ↓                    ↓                ↓              ↓              ↓
Find NULLs        Schwab REST API    Cache Greeks   COALESCE update  Statistics
```

## What Gets Updated

Fields updated **only if NULL** (never overrides existing data):
- `strike_price` (from chain or parsed from symbol)
- `implied_volatility` (from chain)
- `delta` (from chain)
- `gamma` (from chain)
- `theta` (from chain)
- `vega` (from chain)
- `rho` (from chain)

## Data Sources

### Primary: Option Chain API
- Provides: Full Greeks + IV + Strike
- Coverage: ~85-90% (contracts in current chain)
- Used for: Recent expirations (0-45 DTE)

### Fallback: Symbol Parsing
- Provides: Strike price only
- Coverage: 100% (all option symbols)
- Used for: When contract not in chain
- Example: `SPXW  251219C06100000` → Strike = 6100.0

## Safety Features

- ✅ **Idempotent** - Can run multiple times safely
- ✅ **COALESCE** - Never overrides existing non-NULL data
- ✅ **Dry run** - Preview changes before committing
- ✅ **Rate limiting** - Respects Schwab API limits
- ✅ **Progress tracking** - Shows real-time progress
- ✅ **Error handling** - Continues on errors, reports at end

## All Options

```bash
python scripts/backfill_stream_greeks.py [OPTIONS]

Options:
  --stats-only              Show statistics only, don't backfill
  --dry-run                 Preview changes without updating database
  --start YYYY-MM-DD        Start date filter
  --end YYYY-MM-DD          End date filter
  --limit N                 Limit to N records
  --batch-size N            Progress update interval (default: 100)
  -h, --help               Show help message
```

## Examples

### Example 1: Check Status
```bash
$ python scripts/backfill_stream_greeks.py --stats-only

======================================================================
STREAMING DATA STATISTICS
======================================================================

Total streaming records: 125,482

Records with missing data: 45,203 (36.0%)
  Missing strike_price: 45,203
  Missing delta: 45,203
  Missing gamma: 45,203
  ...
```

### Example 2: Dry Run
```bash
$ python scripts/backfill_stream_greeks.py --dry-run --limit 100

✓ Found 100 records needing enrichment
✓ Cached 412 contracts from option chain
  Progress: 100/100 (100.0%) | Updated: 98 | Skipped: 2

⚠️  DRY RUN - No changes were made
Would have updated: 98 records
```

### Example 3: Backfill Last Week
```bash
$ python scripts/backfill_stream_greeks.py --start 2025-12-10 --end 2025-12-17

✓ Found 12,458 records needing enrichment
  Date range: 2025-12-10 06:30:00 to 2025-12-16 14:13:00
  Unique contracts: 145

✓ Cached 287 contracts from option chain
Cache coverage:
  In cache: 145 / 145 (100.0%)

  Progress: 12,458/12,458 (100.0%) | Updated: 12,458 | Skipped: 0

✅ Updated: 12,458 records
⏱️  Time: 42.1s (296.0 records/sec)
```

### Example 4: Test with Small Batch
```bash
$ python scripts/backfill_stream_greeks.py --limit 10

✓ Found 10 records needing enrichment
✓ Cached 412 contracts
✅ Updated: 10 records
```

## Performance

- **Speed**: ~300-400 records/sec
- **API calls**: 1-2 calls total (fetch option chain)
- **Memory**: Minimal (~1 MB for cache)
- **Database**: Uses COALESCE (efficient updates)

### Time Estimates

| Records | Estimated Time |
|---------|----------------|
| 1,000   | ~3 seconds     |
| 10,000  | ~30 seconds    |
| 50,000  | ~2.5 minutes   |
| 100,000 | ~5 minutes     |

## Troubleshooting

### "No records need enrichment"

All data is already complete! ✅

```bash
# Verify
python scripts/backfill_stream_greeks.py --stats-only
```

### High skip rate

```
⏭️  Skipped: 15,000 records (no data available)
```

**Cause**: Contracts not in current option chain (expired or far DTE)

**Solution**:
- Strike price still filled via symbol parsing
- Greeks remain NULL (unavailable for expired contracts)
- This is expected for old data

### API errors

```
❌ Error fetching option chain: Rate limit exceeded
```

**Solution**:
- Wait a few minutes
- Run with smaller `--limit`
- Run during off-market hours (less traffic)

### Database connection errors

```
❌ Failed to connect to database
```

**Solution**:
1. Check Docker: `docker ps`
2. Start TimescaleDB: `docker-compose up -d`
3. Verify `.env` settings

## Verification

After backfill, verify the updates:

```sql
-- Check updated records
SELECT
    COUNT(*) as total,
    COUNT(strike_price) as has_strike,
    COUNT(delta) as has_delta,
    COUNT(implied_volatility) as has_iv
FROM options_bars
WHERE data_source = 'schwabdev_stream';

-- Sample updated records
SELECT
    timestamp,
    option_ticker,
    strike_price,
    delta,
    gamma,
    implied_volatility
FROM options_bars
WHERE data_source = 'schwabdev_stream'
AND strike_price IS NOT NULL
LIMIT 10;
```

## Workflow

### Complete Workflow

```bash
# 1. Check current status
python scripts/backfill_stream_greeks.py --stats-only

# 2. Test with dry run
python scripts/backfill_stream_greeks.py --dry-run --limit 100

# 3. Run full backfill
python scripts/backfill_stream_greeks.py

# 4. Verify results
python scripts/backfill_stream_greeks.py --stats-only
```

### Scheduled Maintenance

Add to cron for weekly maintenance:

```bash
# Every Sunday at 2 AM
0 2 * * 0 cd /path/to/quant-vibe && source venv/bin/activate && python scripts/backfill_stream_greeks.py >> logs/backfill.log 2>&1
```

## Related Documentation

- `docs/STREAM_ENRICHMENT.md` - Complete enrichment guide
- `scripts/stream_spxw_schwabdev.py` - Main streaming script
- `scripts/enrich_stream_with_chain.py` - Enrichment module

## Support

For issues:
1. Check logs for error messages
2. Run with `--dry-run` to test
3. Verify Schwab API credentials
4. Check TimescaleDB is running
5. Review `docs/STREAM_ENRICHMENT.md`
