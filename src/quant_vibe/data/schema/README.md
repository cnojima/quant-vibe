# TimescaleDB Schema Migrations

This directory contains SQL migration scripts for the QuantVibe TimescaleDB schema.

## Applying Migrations

**IMPORTANT**: Before running migrations:
1. **Stop all services** that write to the database (streaming_service, live_trading_service)
2. **Backup the database** (see below)
3. The migration will decompress all chunks, which may take several minutes

### Local Database

```bash
# Use v2 version (handles compressed chunks)
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -f src/quant_vibe/data/schema/001_fix_iv_precision_v2.sql
```

### Remote Database

```bash
PGPASSWORD=your_remote_password psql -h 192.168.100.197 -U quantvibe -d options_data -f src/quant_vibe/data/schema/001_fix_iv_precision_v2.sql
```

### Docker Container

```bash
docker exec -i timescaledb psql -U quantvibe -d options_data < src/quant_vibe/data/schema/001_fix_iv_precision_v2.sql
```

### Backup Database First

```bash
# Local
pg_dump -h localhost -U quantvibe -d options_data > backup_$(date +%Y%m%d_%H%M%S).sql

# Remote
pg_dump -h 192.168.100.197 -U quantvibe -d options_data > backup_remote_$(date +%Y%m%d_%H%M%S).sql
```

## Migration History

### 001_fix_iv_precision_v2.sql (USE THIS VERSION)
**Date**: 2025-12-26
**Issue**: Numeric field overflow for `implied_volatility`
**Details**: Changed `NUMERIC(8,6)` to `NUMERIC(10,6)` for IV and Greeks columns
**Reason**: Allow values >= 100 when IV is expressed as percentage instead of decimal
**Important**: This version handles compressed TimescaleDB chunks properly

**Migration Steps**:
1. Removes compression policy
2. Decompresses all chunks
3. Disables compression
4. Alters column types
5. Re-enables compression with same settings
6. Re-adds compression policy

**Error Fixed**:
```
psycopg2.errors.NumericValueOutOfRange: numeric field overflow
DETAIL: A field with precision 8, scale 6 must round to an absolute value less than 10^2.
```

**Columns Updated**:
- `implied_volatility`: NUMERIC(8,6) → NUMERIC(10,6)
- `delta`: NUMERIC(8,6) → NUMERIC(10,6)
- `gamma`: NUMERIC(8,6) → NUMERIC(10,6)
- `theta`: NUMERIC(8,6) → NUMERIC(10,6)
- `vega`: NUMERIC(8,6) → NUMERIC(10,6)
- `rho`: NUMERIC(8,6) → NUMERIC(10,6)

**Safe to Rerun**: Yes, uses `ALTER COLUMN TYPE` which is idempotent

## Verifying Migrations

Check current schema:
```bash
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -c "\d options_bars"
```

Check specific columns:
```bash
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -c "
SELECT column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_name = 'options_bars'
    AND column_name IN ('implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho')
ORDER BY column_name;
"
```

Expected output after migration:
```
    column_name     | data_type | numeric_precision | numeric_scale
--------------------+-----------+-------------------+---------------
 delta              | numeric   |                10 |             6
 gamma              | numeric   |                10 |             6
 implied_volatility | numeric   |                10 |             6
 rho                | numeric   |                10 |             6
 theta              | numeric   |                10 |             6
 vega               | numeric   |                10 |             6
```

## Best Practices

1. **Always backup** before applying migrations:
   ```bash
   pg_dump -h localhost -U quantvibe -d options_data > backup_$(date +%Y%m%d).sql
   ```

2. **Test on local** before applying to production

3. **Check for running services**: Stop streaming/live-trading services during migration to avoid conflicts

4. **Verify results**: Always run verification queries after migration

## Rollback

If needed, you can rollback this specific migration:

```sql
BEGIN;

ALTER TABLE options_bars
    ALTER COLUMN implied_volatility TYPE NUMERIC(8,6),
    ALTER COLUMN delta TYPE NUMERIC(8,6),
    ALTER COLUMN gamma TYPE NUMERIC(8,6),
    ALTER COLUMN theta TYPE NUMERIC(8,6),
    ALTER COLUMN vega TYPE NUMERIC(8,6),
    ALTER COLUMN rho TYPE NUMERIC(8,6);

COMMIT;
```

**Warning**: Only rollback if you haven't inserted any values >= 100. Otherwise, the rollback will fail with the same overflow error.
