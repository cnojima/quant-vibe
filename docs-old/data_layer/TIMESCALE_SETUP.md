# TimescaleDB Setup for High-Frequency Options Data

This guide explains how to set up and use TimescaleDB for storing gigabytes of 1-minute options bars combined with quote data.

## Why TimescaleDB?

For your use case (1-minute bars + Schwab quotes for SPX options over 1+ years):

- **Storage Efficiency**: 10-20x compression (GB → MB)
- **Query Performance**: Optimized for time-range queries
- **Automatic Aggregates**: Pre-computed 5min, 15min, 1hour, daily bars
- **Scalability**: Handles TB of data efficiently
- **Concurrent Access**: Supports live trading + backtesting simultaneously

## Quick Start

### 1. Start TimescaleDB

```bash
# Start the database
docker-compose up -d

# Check if it's running
docker ps | grep timescaledb

# View logs
docker logs quant-vibe-timescaledb
```

The database will automatically:
- Create the `options_data` database
- Initialize the schema (hypertables, indexes, continuous aggregates)
- Enable compression policies

### 2. Install Python Dependencies

```bash
pip install -e ".[dev]"
```

This installs `psycopg2-binary` for PostgreSQL connectivity.

### 3. Verify Connection

```bash
# Test connection
docker exec -it quant-vibe-timescaledb psql -U quantvibe -d options_data

# Once in psql:
\dt  # List tables
\d options_bars  # Show schema

# Check TimescaleDB version
SELECT default_version, installed_version FROM pg_available_extensions WHERE name = 'timescaledb';

# Exit
\q
```

## Database Schema

### Main Hypertable: `options_bars`

Stores 1-minute OHLCV bars with quote data and Greeks:

```sql
options_bars (
    timestamp,           -- Bar timestamp (partitioning key)
    option_ticker,       -- e.g., 'O:SPX241220C04500000'
    underlying_ticker,   -- e.g., 'SPX'

    -- OHLCV from Massive
    open, high, low, close, volume, vwap, transactions,

    -- Quotes from Schwab
    bid, ask, bid_size, ask_size,

    -- Contract details
    strike_price, contract_type, expiration_date,

    -- Greeks
    implied_volatility, delta, gamma, theta, vega, rho,

    -- Metadata
    data_source, created_at
)
```

### Continuous Aggregates (Auto-computed)

Pre-aggregated views for faster queries:

- `options_bars_5min` - 5-minute bars
- `options_bars_15min` - 15-minute bars
- `options_bars_1hour` - 1-hour bars
- `options_bars_daily` - Daily bars

These are automatically updated every 5 minutes, 15 minutes, 1 hour, and 1 day respectively.

### Compression

- Raw 1-minute data compressed after 7 days (10-20x reduction)
- Compressed by `option_ticker` and `underlying_ticker`
- Still fully queryable after compression

## Collecting Data

### Collect SPX Options Data

```bash
# Collect today's data (OHLCV from Massive)
python scripts/collect_options_1min_data.py --ticker SPX

# Collect historical data
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2024-01-01 \
    --to 2024-12-31

# Collect specific expiration with strike range
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --expiration 2024-12-20 \
    --strike-min 4000 \
    --strike-max 5000 \
    --contract-type call

# Enrich with Schwab quotes (adds bid/ask/Greeks)
# Requires: pip install -e ".[schwab]"
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --enrich-schwab
```

**Schwab Enrichment Details:**
- Adds real-time bid/ask prices
- Includes bid/ask sizes
- Provides Greeks (delta, gamma, theta, vega, rho)
- Includes implied volatility
- Note: Uses current quote for all bars (not historical quotes)
- Requires Schwab API credentials and OAuth authentication

### Script Features

- **Automatic batching**: Inserts in batches of 1000 rows
- **Upsert logic**: Updates existing bars if timestamps conflict
- **Rate limiting**: Built-in delays to respect API limits
- **Progress tracking**: Shows contract-by-contract progress
- **Error handling**: Continues on failures, logs errors

## Using TimescaleStore in Code

### Basic Usage

```python
from quant_vibe.data import TimescaleStore
from datetime import datetime, timedelta

# Initialize connection
store = TimescaleStore()

# Get 1-minute bars for an option
bars = store.get_option_bars(
    option_ticker="O:SPX241220C04500000",
    start_time=datetime(2024, 1, 1),
    end_time=datetime(2024, 12, 20),
    timeframe="1min"  # or '5min', '15min', '1hour', 'daily'
)

# Get entire options chain at a specific time
chain = store.get_options_chain_bars(
    underlying_ticker="SPX",
    expiration_date=datetime(2024, 12, 20),
    timestamp=datetime(2024, 12, 19, 15, 30),  # 3:30 PM
    strike_min=4000,
    strike_max=5000
)

# Get available expiration dates
expirations = store.get_available_expirations("SPX")

# Check data availability
time_range = store.get_data_range("O:SPX241220C04500000")
print(f"Data from {time_range[0]} to {time_range[1]}")

# Get database statistics
stats = store.get_database_stats()
print(f"Total rows: {stats['total_rows']}")
print(f"Database size: {stats['database_size']}")
print(f"Compressed chunks: {stats['compressed_chunks']}")
```

### Bulk Insert

```python
from quant_vibe.data import TimescaleStore
from datetime import datetime

store = TimescaleStore()

# Prepare data
bars = [
    {
        'timestamp': datetime(2024, 1, 1, 9, 30),
        'option_ticker': 'O:SPX241220C04500000',
        'underlying_ticker': 'SPX',
        'open': 100.5,
        'high': 101.0,
        'low': 100.0,
        'close': 100.75,
        'volume': 1000,
        'strike_price': 4500.0,
        'contract_type': 'call',
        'expiration_date': datetime(2024, 12, 20),
        'bid': 100.5,
        'ask': 101.0,
        'data_source': 'combined'
    },
    # ... more bars
]

# Bulk insert
count = store.bulk_insert_option_bars(bars, batch_size=1000)
print(f"Inserted {count} bars")
```

### Querying Different Timeframes

```python
# Fast queries using continuous aggregates
bars_5min = store.get_option_bars(ticker, timeframe="5min")
bars_15min = store.get_option_bars(ticker, timeframe="15min")
bars_hourly = store.get_option_bars(ticker, timeframe="1hour")
bars_daily = store.get_option_bars(ticker, timeframe="daily")
```

## Database Management

### Monitor Database Size

```bash
# Connect to database
docker exec -it quant-vibe-timescaledb psql -U quantvibe -d options_data

# Check database size
SELECT pg_size_pretty(pg_database_size('options_data'));

# Check table size
SELECT pg_size_pretty(pg_total_relation_size('options_bars'));

# Check compression stats
SELECT
    hypertable_name,
    total_chunks,
    number_compressed_chunks,
    pg_size_pretty(before_compression_total_bytes) as before,
    pg_size_pretty(after_compression_total_bytes) as after
FROM timescaledb_information.compression_settings
JOIN timescaledb_information.hypertables USING (hypertable_name);
```

### Manual Compression

```sql
-- Compress specific chunks
SELECT compress_chunk(chunk_name)
FROM timescaledb_information.chunks
WHERE hypertable_name = 'options_bars'
    AND is_compressed = FALSE
    AND range_end < NOW() - INTERVAL '7 days';

-- Decompress if needed
SELECT decompress_chunk('_timescaledb_internal._hyper_1_1_chunk');
```

### Data Retention

Uncomment in `init_timescale.sql` to auto-delete old data:

```sql
-- Keep raw 1-minute data for 90 days
SELECT add_retention_policy('options_bars', INTERVAL '90 days');
```

### Backup and Restore

```bash
# Backup
docker exec quant-vibe-timescaledb pg_dump -U quantvibe options_data > backup.sql

# Restore
docker exec -i quant-vibe-timescaledb psql -U quantvibe options_data < backup.sql
```

## Performance Optimization

### Index Usage

The following indexes are automatically created:

- `(option_ticker, timestamp)` - Single contract queries
- `(underlying_ticker, timestamp)` - Chain queries
- `(expiration_date, timestamp)` - Expiration filtering
- `(underlying_ticker, contract_type, timestamp)` - Type filtering
- `(underlying_ticker, expiration_date, strike_price, timestamp)` - Strike queries

### Query Tips

```sql
-- FAST: Uses index
SELECT * FROM options_bars
WHERE option_ticker = 'O:SPX241220C04500000'
    AND timestamp >= '2024-01-01'
    AND timestamp <= '2024-12-31';

-- FAST: Uses continuous aggregate
SELECT * FROM options_bars_5min
WHERE option_ticker = 'O:SPX241220C04500000'
    AND bucket >= '2024-01-01';

-- SLOW: Full table scan
SELECT * FROM options_bars
WHERE strike_price = 4500;  -- Missing underlying_ticker filter!

-- FAST: With proper filtering
SELECT * FROM options_bars
WHERE underlying_ticker = 'SPX'
    AND strike_price = 4500
    AND timestamp >= '2024-01-01';
```

### Connection Pooling

TimescaleStore uses connection pooling by default (5 connections). Adjust if needed:

```python
store = TimescaleStore(pool_size=10)  # For high-concurrency workloads
```

## Troubleshooting

### Can't Connect to Database

```bash
# Check if container is running
docker ps | grep timescaledb

# Check logs
docker logs quant-vibe-timescaledb

# Restart if needed
docker-compose restart timescaledb
```

### Database Not Initialized

```bash
# Manually run init script
docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < src/quant_vibe/data/schema/init_timescale.sql
```

### Slow Queries

1. Check if you're using indexes properly
2. Use EXPLAIN ANALYZE to see query plan
3. Consider using continuous aggregates for higher timeframes
4. Ensure data is compressed (check compression stats)

### Out of Disk Space

```bash
# Check disk usage
docker exec quant-vibe-timescaledb df -h

# Enable retention policy to auto-delete old data
# Or manually delete old data:
docker exec -it quant-vibe-timescaledb psql -U quantvibe -d options_data -c \
    "DELETE FROM options_bars WHERE timestamp < NOW() - INTERVAL '90 days';"
```

## Migrating from SQLite

If you have existing data in SQLite:

1. Export from SQLite to CSV/Parquet
2. Transform to TimescaleDB format
3. Bulk insert using `bulk_insert_option_bars()`

Example migration script:

```python
from quant_vibe.data import DataStore, TimescaleStore
import sqlite3
import pandas as pd

# Read from SQLite
sqlite_store = DataStore("data/backtest_db/options_data.db")
# ... read data ...

# Write to TimescaleDB
timescale_store = TimescaleStore()
timescale_store.bulk_insert_option_bars(bars)
```

## Production Deployment

For production:

1. **Change passwords**: Update `TIMESCALE_PASSWORD` in `.env`
2. **Enable SSL**: Add SSL certificates to docker-compose
3. **Backup strategy**: Set up automated backups
4. **Monitoring**: Use pg_stat_statements for query monitoring
5. **Resource limits**: Adjust PostgreSQL memory settings based on server
6. **Retention policy**: Enable auto-deletion of old data
7. **Read replicas**: For read-heavy workloads

## References

- [TimescaleDB Documentation](https://docs.timescale.com/)
- [Continuous Aggregates](https://docs.timescale.com/use-timescale/latest/continuous-aggregates/)
- [Compression](https://docs.timescale.com/use-timescale/latest/compression/)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
