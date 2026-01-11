# SPXW 0-3 DTE Options Backfill

## Overview

This backfill system fetches historical SPXW (S&P 500 Weekly) options data with 0-3 days to expiration (DTE) from Massive.io's API.

**Key Features**:
- ✅ Dynamic ATM-based strike selection (adapts to SPX price movements)
- ✅ Sampling strategies (weekly/monthly to reduce data volume)
- ✅ Strike step filtering (only fetch strikes at specific intervals)
- ✅ 1-minute bar resolution for accurate backtesting
- ✅ Pydantic schema compliance

## Date Range

- **Available Data**: Feb 14, 2023 - Nov 30, 2025
- **Target DTE**: 0-3 days (short-term options)
- **Underlying**: SPX (S&P 500 Index)

## Enhanced Script: `backfill_spx_options.py`

The existing script has been enhanced with dynamic strike selection and sampling capabilities.

### New Parameters

#### Strike Selection

**`--strike-mode {fixed|dynamic}`** (default: `dynamic`)
- `fixed`: Use explicit `--strike-min` and `--strike-max`
- `dynamic`: Calculate strikes based on ATM ± percentage

**`--strike-range-pct PERCENT`** (default: `5.0`)
- For dynamic mode: percentage above/below ATM
- Example: If SPX @ 6000, 5% = 5700-6300 range

**`--strike-step POINTS`** (default: `50`)
- Only include strikes divisible by this value
- Examples: 50 (every 50 points), 100 (every 100 points), 25 (every 25 points)

**`--strike-min PRICE`** / **`--strike-max PRICE`**
- Explicit strike boundaries (overrides dynamic mode if both set)

#### Sampling

**`--sample-days N`** (default: `1`)
- Process every N days
- Examples: 1 (all days), 7 (weekly), 30 (monthly)

**`--sample-weekday {monday|tuesday|wednesday|thursday|friday}`**
- Process only specific weekday
- Overrides `--sample-days` if set
- Example: `--sample-weekday monday` processes only Mondays

#### DTE Range

**`--max-dte DAYS`** (default: `2`)
- Maximum days before expiration to fetch bars
- For 0-3 DTE: use `--max-dte 3`

## Usage Examples

### Test with One Day

```bash
python scripts/backfill/backfill_spx_options.py \
  --start 2024-12-20 \
  --end 2024-12-21 \
  --max-dte 3 \
  --strike-mode dynamic \
  --strike-range-pct 5 \
  --strike-step 50 \
  --no-greeks
```

**Result**: ~26 contracts × ~1,000 bars = 26,000 bars (1 day)

### Weekly Sampling (Recommended)

```bash
python scripts/backfill/backfill_spx_options.py \
  --start 2023-02-01 \
  --end 2025-11-30 \
  --max-dte 3 \
  --strike-mode dynamic \
  --strike-range-pct 5 \
  --strike-step 50 \
  --sample-weekday monday \
  --no-greeks
```

**Data Volume**:
- ~145 Mondays × 3 expirations × 26 contracts × 1,000 bars = **11.3M bars**
- Runtime: ~12-15 hours
- Storage: ~5-6 GB uncompressed, ~1-1.5 GB compressed

### Bi-Weekly Sampling (Lighter)

```bash
python scripts/backfill/backfill_spx_options.py \
  --start 2023-02-01 \
  --end 2025-11-30 \
  --max-dte 3 \
  --strike-mode dynamic \
  --strike-range-pct 5 \
  --strike-step 100 \  # Wider step for less data
  --sample-days 14 \
  --no-greeks
```

**Data Volume**:
- ~70 dates × 3 expirations × 13 contracts × 1,000 bars = **2.7M bars**
- Runtime: ~3-4 hours
- Storage: ~1.4 GB uncompressed, ~300 MB compressed

### Fixed Strike Range (Legacy Mode)

```bash
python scripts/backfill/backfill_spx_options.py \
  --start 2024-12-01 \
  --end 2024-12-31 \
  --max-dte 3 \
  --strike-min 5800 \
  --strike-max 6200 \
  --no-greeks
```

## Wrapper Script: `run_spxw_0_3dte_backfill.sh`

Preconfigured wrapper for the full historical backfill.

**Configuration**:
- Date Range: 2023-02-01 to 2025-11-30
- DTE: 0-3 days
- Strike Mode: Dynamic ATM ± 5%
- Strike Step: 50 points
- Sampling: Weekly (Mondays only)
- Greeks: Disabled (run separately)

### Usage

```bash
# Test configuration (no actual backfill)
./scripts/backfill/run_spxw_0_3dte_backfill.sh dry-run

# Run full backfill
./scripts/backfill/run_spxw_0_3dte_backfill.sh
```

## Data Volume Estimates

### Comparison by Sampling Strategy

| Strategy | Days | Contracts/Day | Bars/Contract | Total Bars | Storage | Runtime |
|----------|------|---------------|---------------|------------|---------|---------|
| **All Days** | 700 | 78 | 1,000 | 54.6M | 27 GB | 80 hours |
| **Weekly (Mon)** | 145 | 78 | 1,000 | 11.3M | 5.6 GB | 15 hours |
| **Bi-weekly** | 70 | 78 | 1,000 | 5.5M | 2.7 GB | 7 hours |
| **Monthly** | 23 | 78 | 1,000 | 1.8M | 900 MB | 2 hours |

**With Wider Strike Step (100 points)**:

| Strategy | Days | Contracts/Day | Total Bars | Storage | Runtime |
|----------|------|---------------|------------|---------|---------|
| **Weekly** | 145 | 39 | 5.7M | 2.8 GB | 8 hours |
| **Bi-weekly** | 70 | 39 | 2.7M | 1.4 GB | 4 hours |
| **Monthly** | 23 | 39 | 900K | 450 MB | 1 hour |

*Note: Estimates assume 3 expirations per day (0, 1, 2-3 DTE) and ~1,000 bars per contract*

## How Dynamic Strike Selection Works

For each expiration date:

1. **Get SPX Price**: Query `underlying_bars` table for SPX closing price on that date
   ```sql
   SELECT close FROM underlying_bars
   WHERE ticker='SPX' AND DATE(timestamp)='2024-12-20'
   ORDER BY timestamp DESC LIMIT 1;
   ```

2. **Calculate Strike Range**:
   ```python
   atm_price = 5930.85  # SPX close
   range_pct = 5.0      # ±5%
   strike_step = 50     # Round to 50s

   raw_min = 5930.85 * 0.95 = 5634.31
   raw_max = 5930.85 * 1.05 = 6227.39

   strike_min = round(5634.31 / 50) * 50 = 5650
   strike_max = round(6227.39 / 50) * 50 = 6250
   ```

3. **Fetch Contracts**:
   ```python
   contracts = massive.list_options_contracts(
       underlying='SPX',
       expiration_date='2024-12-20',
       strike_gte=5650,
       strike_lte=6250,
   )
   ```

4. **Filter by Strike Step**:
   ```python
   # Only keep strikes divisible by 50
   contracts = [c for c in contracts if c.strike % 50 == 0]
   # Result: 5650, 5700, 5750, ..., 6200, 6250
   ```

## Advantages of Dynamic Strike Selection

1. **Adapts to Market Conditions**:
   - SPX @ 4000 (2023): Strikes 3800-4200
   - SPX @ 6000 (2024): Strikes 5700-6300
   - Always captures ATM and near-the-money strikes

2. **Reduces Data Volume**:
   - Fixed range (5000-7000) = 80 strikes
   - Dynamic ATM ± 5% = ~26 strikes (67% reduction)

3. **Improves Relevance**:
   - Only fetches tradeable strikes
   - Avoids deep OTM/ITM strikes with no liquidity

4. **Consistent Moneyness**:
   - Always ±5% from ATM regardless of SPX level
   - Better for backtesting strategies that use moneyness

## Workflow

### Phase 1: Initial Backfill (No Greeks)

```bash
# Run weekly sampling backfill
./scripts/backfill/run_spxw_0_3dte_backfill.sh

# Or run manually with custom parameters
python scripts/backfill/backfill_spx_options.py \
  --start 2023-02-01 \
  --end 2025-11-30 \
  --max-dte 3 \
  --strike-mode dynamic \
  --strike-range-pct 5 \
  --strike-step 50 \
  --sample-weekday monday \
  --no-greeks
```

**Timeline**: ~12-15 hours

### Phase 2: Verify Data Quality

```sql
-- Check data coverage
SELECT
    DATE(timestamp) as date,
    COUNT(DISTINCT contract_symbol) as contracts,
    COUNT(*) as bars
FROM options_bars
WHERE timestamp >= '2023-02-01'
GROUP BY DATE(timestamp)
ORDER BY date;

-- Check for gaps
SELECT generate_series::date as missing_monday
FROM generate_series('2023-02-01'::date, '2025-11-30'::date, '7 days'::interval)
WHERE EXTRACT(DOW FROM generate_series) = 1  -- Monday
  AND generate_series::date NOT IN (
      SELECT DISTINCT DATE(timestamp)
      FROM options_bars
      WHERE timestamp >= '2023-02-01'
  );
```

### Phase 3: Refresh Continuous Aggregates

```bash
# Refresh 5-min, 15-min, 1-hour, daily aggregates
source venv/bin/activate && python -c "
from quant_vibe.data.timescale_store import TimescaleStore

ts = TimescaleStore()
conn = ts.pool.getconn()
conn.autocommit = True
cur = conn.cursor()

aggregates = [
    'options_bars_5min',
    'options_bars_15min',
    'options_bars_1hour',
    'options_bars_daily'
]

for agg in aggregates:
    print(f'Refreshing {agg}...')
    cur.execute(
        f\"CALL refresh_continuous_aggregate('{agg}', '2023-02-01', '2025-12-01')\"
    )
    print(f'✅ {agg} refreshed')

cur.close()
ts.pool.putconn(conn)
print('✅ All aggregates refreshed!')
"
```

### Phase 4: Greeks Enrichment (Optional)

**Warning**: This is VERY slow (~48+ hours for full dataset)

```bash
python scripts/backfill/backfill_stream_greeks.py \
  --start 2023-02-01 \
  --end 2025-11-30
```

**Recommendation**: Only run Greeks for recent data needed for backtesting
```bash
# Just the last 6 months
python scripts/backfill/backfill_stream_greeks.py \
  --start 2024-06-01 \
  --end 2024-12-31
```

## Troubleshooting

### No SPX Price Found

```
⚠️  No SPX price found for 2024-12-25
⚠️  Skipping 2024-12-25 - no SPX price available
```

**Cause**: No underlying_bars data for that date (market holiday or missing data)

**Solution**:
1. Check if it's a holiday (expected)
2. Ensure `underlying_bars` backfill is complete
3. Run `backfill_massive_spx_index.py` to fill gaps

### API Rate Limits

```
Error 429: Too Many Requests
```

**Solution**: Add delay between requests (script has 0.5s built-in)
- Reduce parallelism
- Use smaller date ranges
- Contact Massive.io for rate limit increase

### Out of Memory

```
MemoryError: Unable to allocate array
```

**Solution**: Reduce batch size
```bash
python scripts/backfill/backfill_spx_options.py \
  --batch-size 500 \  # Default is 1000
  ...
```

## Performance Optimization

1. **Parallel Processing**: The script processes contracts sequentially. Could be parallelized.

2. **Caching**: SPX prices are queried for each expiration. Could cache in memory.

3. **Incremental Updates**: Check existing data and only fetch missing days.

## Related Scripts

- `backfill_massive_spx_index.py`: Backfill underlying SPX prices (required first)
- `backfill_stream_greeks.py`: Calculate and populate Greeks
- `backfill_spx_underlying_1min.py`: Schwab API underlying backfill (pre-2023 data)

## Data Schema

Data is stored in `options_bars` table following the `OptionsBar` Pydantic model:

```python
OptionsBar(
    timestamp=utc_aware_datetime,
    contract_symbol='SPXW241220P05950000',  # Normalized format
    underlying_ticker='SPX',
    strike_price=Decimal('5950.0'),
    contract_type='put',  # or 'call'
    expiration_date=date(2024, 12, 20),
    open/high/low/close=Decimal,
    volume=int,
    bid/ask/mark=Decimal,
    data_source='massive',
)
```

See `docs/SCHEMA_MAPPING.md` for full details.

---

**Author**: Claude Code
**Date**: 2026-01-11
**Last Updated**: 2026-01-11
