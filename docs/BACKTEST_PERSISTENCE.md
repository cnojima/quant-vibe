# Backtest Results Persistence

This document describes the PostgreSQL-based persistence layer for backtest results in the Quant-Vibe system.

## Overview

Backtest results are now automatically persisted to PostgreSQL/TimescaleDB when running backtests through the orchestrator. This provides:

- **Historical tracking**: Complete history of all backtest executions
- **API access**: Query backtest results via REST API for admin UI
- **Performance analysis**: Compare strategies, track improvements over time
- **Audit trail**: Full record of strategy parameters and results

## Architecture

### Database Schema

Three main tables store backtest data:

**1. backtest_runs** (Metadata & Summary)
- Stores metadata about each backtest execution
- Primary key: `backtest_id` (format: `{strategy_name}_{timestamp}`)
- Contains summary metrics (Sharpe ratio, win rate, drawdown, etc.)
- Tracks execution status (`pending`, `running`, `completed`, `failed`)

**2. backtest_trades** (Trade Records)
- Individual trade records from backtest executions
- Foreign key to `backtest_runs.backtest_id`
- Stores multi-leg options positions as JSONB
- Includes entry/exit timing, P&L, triggers, and exit reasons

**3. backtest_equity_curve** (TimescaleDB Hypertable)
- Portfolio value snapshots over time
- Partitioned by `timestamp` for efficient time-series queries
- Includes computed metrics (returns, drawdown, cummax)
- Composite primary key: `(timestamp, backtest_id)`

### Data Flow

```
┌──────────────────────────────────────────────────────┐
│  BacktestOrchestrator                                │
│  ├─ Runs strategy backtest                           │
│  ├─ Collects results (trades, equity curve, metrics) │
│  └─ Calls save_backtest_to_db()                      │
└──────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────┐
│  TimescaleStore (Persistence Layer)                  │
│  ├─ save_backtest_run() → backtest_runs             │
│  ├─ update_backtest_metrics() → backtest_runs       │
│  ├─ save_backtest_trades() → backtest_trades        │
│  └─ save_backtest_equity_curve() → equity curve     │
└──────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────┐
│  PostgreSQL/TimescaleDB                              │
│  ├─ backtest_runs (summary metrics)                  │
│  ├─ backtest_trades (trade records)                  │
│  └─ backtest_equity_curve (time-series data)         │
└──────────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────────┐
│  Admin UI API                                        │
│  ├─ GET /backtests/history (fetch all backtests)    │
│  ├─ GET /backtests/{id}/results (fetch specific)    │
│  └─ Falls back to CSV files if DB unavailable       │
└──────────────────────────────────────────────────────┘
```

## Setup

### 1. Run Database Migration

```bash
# Local database
docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < scripts/migrations/001_add_backtest_results.sql

# Remote database (optional)
export PGPASSWORD=your-password
psql -h your-host -U quantvibe -d options_data < scripts/migrations/001_add_backtest_results.sql
```

### 2. Configure Environment

The system automatically uses the database configured in `.env`:

```bash
# Use local database
USE_REMOTE_TIMESCALE=false

# Or use remote database
USE_REMOTE_TIMESCALE=true
REMOTE_TIMESCALE_HOST=192.168.100.197
REMOTE_TIMESCALE_PORT=5432
REMOTE_TIMESCALE_DB=options_data
REMOTE_TIMESCALE_USER=quantvibe
REMOTE_TIMESCALE_PASSWORD=your-password
```

## Usage

### Running Backtests (Automatic Persistence)

When you run backtests through the orchestrator, results are automatically saved to PostgreSQL:

```bash
# Run backtest (results saved to both CSV and PostgreSQL)
python scripts/run_backtest.py --strategy bullish_vertical_put

# Run with custom date range
python scripts/run_backtest.py --strategy bullish_vertical_put \
  --start-date 2025-12-01 --end-date 2025-12-15
```

The backtest orchestrator (`src/backtest/engine.py`) automatically calls `save_backtest_to_db()` when configured to auto-save results.

### Manual Persistence (Advanced)

For custom backtest scripts, manually save results:

```python
from datetime import datetime
from quant_vibe.utils import save_backtest_to_db

# After running backtest
save_backtest_to_db(
    backtest_id="bullish_vertical_put_20251230_143022",
    strategy_name="bullish_vertical_put",
    start_date=datetime(2025, 12, 1),
    end_date=datetime(2025, 12, 15),
    initial_capital=100000.0,
    results=results,  # From OptionsBacktestEngine
    parameters={'spread_width': 20, 'min_dte': 0, 'max_dte': 0},
)
```

### Querying Results

**Python API (Direct Database Access):**

```python
from quant_vibe.data.timescale_store import TimescaleStore

ts_store = TimescaleStore()

# Get backtest history
history = ts_store.get_backtest_history(
    strategy_name="bullish_vertical_put",
    limit=10
)

# Get specific backtest
backtest_run = ts_store.get_backtest_run("bullish_vertical_put_20251230_143022")

# Get trades
trades_df = ts_store.get_backtest_trades("bullish_vertical_put_20251230_143022")

# Get equity curve
equity_df = ts_store.get_backtest_equity_curve("bullish_vertical_put_20251230_143022")

ts_store.close()
```

**REST API (Admin UI):**

```bash
# Get backtest history
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/backtests/history

# Filter by strategy
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/backtests/history?strategy_name=bullish_vertical_put

# Get specific backtest results
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/backtests/bullish_vertical_put_20251230_143022/results
```

**SQL Queries (Direct PostgreSQL):**

```sql
-- List all backtests for a strategy
SELECT backtest_id, started_at, status, total_return_pct, win_rate
FROM backtest_runs
WHERE strategy_name = 'bullish_vertical_put'
ORDER BY created_at DESC
LIMIT 10;

-- Get latest backtest (using helper function)
SELECT * FROM get_latest_backtest('bullish_vertical_put');

-- Get backtest summary (using helper function)
SELECT * FROM get_backtest_summary('bullish_vertical_put_20251230_143022');

-- Get all trades for a backtest
SELECT entry_time, exit_time, pnl, exit_reason
FROM backtest_trades
WHERE backtest_id = 'bullish_vertical_put_20251230_143022'
ORDER BY entry_time;

-- Get equity curve
SELECT timestamp, portfolio_value, drawdown
FROM backtest_equity_curve
WHERE backtest_id = 'bullish_vertical_put_20251230_143022'
ORDER BY timestamp;
```

## Data Retention

By default, all backtest data is kept indefinitely.

### Automatic Retention (Optional)

To enable automatic retention policies on the equity curve hypertable:

```sql
-- Keep backtest equity curves for 90 days
SELECT add_retention_policy('backtest_equity_curve', INTERVAL '90 days');

-- Or use longer retention periods
SELECT add_retention_policy('backtest_equity_curve', INTERVAL '180 days');  -- 6 months
SELECT add_retention_policy('backtest_equity_curve', INTERVAL '365 days');  -- 1 year
```

**Note**: Retention policies only apply to hypertables (equity_curve). Trade records and metadata in `backtest_runs` and `backtest_trades` must be cleaned up manually.

### Manual Cleanup

Use the provided cleanup utility to delete old backtests:

```bash
# Preview what would be deleted (dry run)
./scripts/cleanup_old_backtests.sh 90 --dry-run

# Delete backtests older than 90 days
./scripts/cleanup_old_backtests.sh 90

# Delete backtests older than 180 days
./scripts/cleanup_old_backtests.sh 180
```

The cleanup script:
- Deletes old backtest runs, trades, and equity curves
- Cascades deletions via foreign keys
- Runs VACUUM to reclaim disk space
- Shows before/after table sizes
- Works with both local and remote databases

Manual SQL cleanup:

```sql
-- Delete all backtests older than 90 days
-- This cascades to trades and equity curve via foreign keys
DELETE FROM backtest_runs
WHERE created_at < NOW() - INTERVAL '90 days';

-- Reclaim disk space
VACUUM ANALYZE backtest_runs;
VACUUM ANALYZE backtest_trades;
VACUUM ANALYZE backtest_equity_curve;
```

## Performance Optimization

### Indexes

The system includes optimized indexes for common queries:

- `backtest_runs`: Indexed on `created_at`, `strategy_name`, `status`
- `backtest_trades`: Indexed on `backtest_id`, `position_id`, `entry_time`
- `backtest_equity_curve`: Indexed on `backtest_id`, `timestamp`

### TimescaleDB Benefits

The equity curve table uses TimescaleDB hypertable features:

- **Automatic partitioning**: Data partitioned by time (7-day chunks)
- **Efficient queries**: Fast time-range queries on large datasets
- **Compression**: ✅ **Enabled** - Automatically compresses data older than 7 days

Compression is already enabled on the `backtest_equity_curve` table:

- **Segmented by**: `backtest_id` (each backtest compressed independently)
- **Ordered by**: `timestamp DESC` (most recent data accessible fastest)
- **Compression ratio**: Typically 10-20x for time-series data
- **Automatic**: Chunks older than 7 days are compressed automatically

To view compression statistics:

```sql
-- Check compression settings
SELECT * FROM timescaledb_information.compression_settings
WHERE hypertable_name = 'backtest_equity_curve';

-- View compression stats
SELECT * FROM timescaledb_information.compressed_chunk_stats
WHERE hypertable_name = 'backtest_equity_curve';

-- Manually compress a specific chunk (if needed)
SELECT compress_chunk(show_chunks('backtest_equity_curve'));
```

## Backward Compatibility

The system maintains backward compatibility with CSV-based storage:

- Backtest results are saved to **both** PostgreSQL and CSV files
- Admin UI API falls back to CSV files if database query fails
- Existing backtests stored only in CSV remain accessible

## Migration Path

### For Existing Backtests

To migrate old CSV-based backtests to PostgreSQL:

1. Parse CSV files using `pandas`
2. Call `save_backtest_to_db()` with reconstructed data
3. Verify migration with database queries

Example migration script:

```python
import pandas as pd
from datetime import datetime
from quant_vibe.utils import save_backtest_to_db

# Load CSV files
trades_df = pd.read_csv("backtests/backtest_results/strategy_trades_20251220_123456.csv")
equity_df = pd.read_csv("backtests/backtest_results/strategy_equity_20251220_123456.csv")

# Reconstruct results dict
results = {
    'trades': trades_df,
    'equity_curve': equity_df,
    'final_capital': equity_df['portfolio_value'].iloc[-1],
    'num_trades': len(trades_df),
    # ... other metrics
}

# Save to database
save_backtest_to_db(
    backtest_id="strategy_20251220_123456",
    strategy_name="strategy",
    start_date=datetime(2025, 12, 1),
    end_date=datetime(2025, 12, 20),
    initial_capital=100000.0,
    results=results,
)
```

## Troubleshooting

### Database Connection Issues

If persistence fails, the system will:

1. Log error to console
2. Continue saving to CSV files
3. Backtest completes successfully

Check logs for connection errors:

```
❌ Error saving to database: connection to server failed
✅ Results still available in CSV files
```

### Missing Data

If data doesn't appear in queries:

```sql
-- Check if migration ran
SELECT table_name
FROM information_schema.tables
WHERE table_name LIKE 'backtest%';

-- Verify backtest exists
SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT 5;

-- Check for errors in backtest run
SELECT backtest_id, status, error_message
FROM backtest_runs
WHERE status = 'failed';
```

### Performance Issues

For slow queries on large datasets:

```sql
-- Analyze query performance
EXPLAIN ANALYZE
SELECT * FROM backtest_equity_curve
WHERE backtest_id = 'strategy_20251230_143022';

-- Update table statistics
ANALYZE backtest_equity_curve;
ANALYZE backtest_trades;
ANALYZE backtest_runs;
```

## Future Enhancements

Potential improvements:

1. **Real-time backtest streaming**: Stream equity curve updates during backtest execution
2. **Comparative analysis**: Built-in queries to compare multiple strategy runs
3. **Alerts**: Notifications when backtest metrics exceed thresholds
4. **Visualization**: Direct database → chart rendering in admin UI
5. **Data aggregation**: Pre-computed monthly/yearly strategy performance summaries

## See Also

- [Migration README](../scripts/migrations/README.md) - Database migration guide
- [CLAUDE.md](../CLAUDE.md) - Main development documentation
- [Admin UI API](../src/admin_ui/backend/api/backtests.py) - REST API implementation
- [TimescaleStore](../src/quant_vibe/data/timescale_store.py) - Database client implementation
