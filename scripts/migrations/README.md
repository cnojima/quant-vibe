# Database Migrations

This directory contains SQL migration scripts for the Quant-Vibe TimescaleDB database.

## Running Migrations

### Local Database

```bash
# Run migration on local TimescaleDB
docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < scripts/migrations/001_add_backtest_results.sql
```

### Remote Database

```bash
# Set remote database credentials
export PGPASSWORD=your-remote-password

# Run migration on remote TimescaleDB
psql -h 192.168.100.197 -p 5432 -U quantvibe -d options_data < scripts/migrations/001_add_backtest_results.sql
```

## Migration History

### 001_add_backtest_results.sql

**Purpose**: Add backtest results persistence tables

**Tables Created**:
- `backtest_runs` - Metadata and summary metrics for each backtest execution
- `backtest_trades` - Individual trade records from backtests
- `backtest_equity_curve` - Portfolio value snapshots over time (hypertable)

**Features**:
- Stores complete backtest execution history in PostgreSQL
- Supports querying by strategy, date range, status
- Includes performance metrics (Sharpe ratio, win rate, drawdown, etc.)
- Trade details include multi-leg options positions as JSON
- Equity curve is a TimescaleDB hypertable for efficient time-series queries

**Helper Functions**:
- `get_latest_backtest(strategy)` - Get most recent backtest for a strategy
- `get_backtest_summary(backtest_id)` - Get summary statistics for a backtest

**Usage**:

After running this migration, backtests will automatically be persisted to PostgreSQL when using:

```python
from quant_vibe.utils import save_backtest_to_db

save_backtest_to_db(
    backtest_id="strategy_20251230_143022",
    strategy_name="bullish_vertical_put",
    start_date=datetime(2025, 12, 1),
    end_date=datetime(2025, 12, 15),
    initial_capital=100000.0,
    results=results,
    parameters={'spread_width': 20, 'min_dte': 0}
)
```

## Verifying Migrations

Check if tables exist:

```sql
-- List all backtest-related tables
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'backtest%';

-- Check backtest runs count
SELECT COUNT(*) FROM backtest_runs;

-- Check if equity curve is a hypertable
SELECT * FROM timescaledb_information.hypertables
WHERE hypertable_name = 'backtest_equity_curve';
```

## Rollback

To remove the backtest tables:

```sql
DROP TABLE IF EXISTS backtest_equity_curve CASCADE;
DROP TABLE IF EXISTS backtest_trades CASCADE;
DROP TABLE IF EXISTS backtest_runs CASCADE;
DROP FUNCTION IF EXISTS get_latest_backtest(TEXT);
DROP FUNCTION IF EXISTS get_backtest_summary(TEXT);
```
