# Optimization Service Performance Fix

## Issue Description
The optimization worker was making multiple redundant queries to TimescaleDB, causing high CPU usage and database overload. The queries would hang when processing date ranges that included future dates or very recent data.

## Root Causes
1. **Future Date Queries**: Optimizations with end dates in the future or today caused slow/hanging queries
2. **No Query Timeout**: Database queries had no timeout, allowing them to run indefinitely
3. **Stuck Optimizations**: Old optimizations remained in "running" state, preventing cleanup
4. **Large Date Ranges**: Queries for large date ranges (months/years) were slow without proper indexing

## Fixes Applied

### 1. Date Range Validation
Added validation to prevent querying future dates:
```python
# Validate date range - don't query future dates
today = datetime.now().date()
if end_date.date() > today:
    logger.warning(f"End date {end_date.date()} is in the future, adjusting to today {today}")
    end_date = datetime.combine(today, datetime.min.time())
```

### 2. Query Timeout
Implemented 30-second timeout for database queries:
```python
options_df, underlying_df = await asyncio.wait_for(
    loop.run_in_executor(
        None,
        load_options_backtest_data,
        ...
    ),
    timeout=30.0  # 30 second timeout
)
```

### 3. Database Cleanup
Clean up stuck optimizations:
```sql
UPDATE optimization_runs
SET status = 'failed',
    error_message = 'Optimization timed out or was stuck'
WHERE status = 'running'
  AND created_at < NOW() - INTERVAL '1 hour';
```

## Best Practices

### 1. Date Range Selection
- **Use historical dates**: Always use dates at least 1 day in the past
- **Available data range**: SPX options data is available from 2024-01-22 onwards
- **Reasonable ranges**: Use 1-3 months for optimizations, not full years
- **Example**:
  ```python
  # Good
  train_start_date = datetime(2024, 2, 1)
  train_end_date = datetime(2024, 3, 1)

  # Bad (future date)
  train_end_date = datetime.now() + timedelta(days=1)

  # Bad (too large)
  train_start_date = datetime(2024, 1, 1)
  train_end_date = datetime(2025, 12, 31)
  ```

### 2. Timeframe Selection
Use appropriate timeframes to reduce data volume:
- **"1hour"**: Good for quick tests and optimizations
- **"5min"**: Recommended for detailed backtests (95% less memory than 1min)
- **"1min"**: Only when highest resolution is required (uses most memory)

### 3. Parameter Grid Size
Keep parameter combinations reasonable:
- **< 100 combinations**: Quick optimization (< 10 minutes)
- **100-500 combinations**: Standard optimization (10-60 minutes)
- **> 500 combinations**: Long optimization (hours)

### 4. Worker Configuration
Ensure proper worker settings:
```yaml
# docker-compose.yml
environment:
  WORKER_CONCURRENCY: 1  # Don't run multiple optimizations in parallel
  MAX_MEMORY_MB: 7000    # Sufficient memory for large datasets
```

## Monitoring

### Check Worker Status
```bash
# View worker logs
docker logs quant-vibe-optimization --tail 50

# Check worker health
docker ps | grep optimization
```

### Check Queue Status
```bash
# Check optimization queue size
docker exec quant-vibe-redis redis-cli -n 0 LLEN optimization:queue

# View running optimizations
psql -h localhost -U quantvibe -d options_data -c \
  "SELECT optimization_id, status, train_start_date, train_end_date
   FROM optimization_runs
   WHERE status IN ('running', 'pending')
   ORDER BY created_at DESC;"
```

### Clean Up Stuck Optimizations
```bash
# Mark old running optimizations as failed
psql -h localhost -U quantvibe -d options_data -c \
  "UPDATE optimization_runs
   SET status = 'failed', error_message = 'Timeout'
   WHERE status = 'running'
   AND created_at < NOW() - INTERVAL '1 hour';"
```

## Performance Improvements
With these fixes:
- Database queries timeout after 30 seconds instead of hanging indefinitely
- Future dates are automatically adjusted to prevent invalid queries
- Worker won't get stuck on problematic optimizations
- CPU usage remains normal even with large date ranges

## Error Prevention
The system now:
- Validates date ranges before querying
- Times out slow queries
- Logs detailed error messages
- Prevents multiple workers from processing the same optimization