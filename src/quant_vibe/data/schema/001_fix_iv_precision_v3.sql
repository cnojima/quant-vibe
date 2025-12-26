-- Migration: Fix implied_volatility and Greeks precision (v3 - compatible with TimescaleDB API)
-- Date: 2025-12-26
-- Issue: NUMERIC(8,6) only allows values < 100, causing overflow errors
--        when IV is expressed as percentage (e.g., 150%) instead of decimal (1.50)
--
-- Solution: Decompress chunks, change to NUMERIC(10,6), re-compress
--
-- Error that prompted this fix:
--   psycopg2.errors.NumericValueOutOfRange: numeric field overflow
--   DETAIL: A field with precision 8, scale 6 must round to an absolute value less than 10^2.
-- APPLY with:   cat src/quant_vibe/data/schema/001_fix_iv_precision_v3.sql |
--               docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data`
-- Step 1: Check if compression policy exists and remove it
DO $$
DECLARE
    policy_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_schema = 'timescaledb_internal'
        AND hypertable_name = 'options_bars'
        AND proc_name LIKE '%compress%'
    ) INTO policy_exists;

    IF policy_exists THEN
        PERFORM remove_compression_policy('options_bars');
        RAISE NOTICE 'Compression policy removed';
    ELSE
        RAISE NOTICE 'No compression policy found';
    END IF;
END $$;

-- Step 2: Decompress all compressed chunks
DO $$
DECLARE
    chunk_name text;
BEGIN
    FOR chunk_name IN
        SELECT c.chunk_schema || '.' || c.chunk_name
        FROM timescaledb_information.chunks c
        WHERE c.hypertable_name = 'options_bars'
        AND c.is_compressed = true
    LOOP
        EXECUTE format('SELECT decompress_chunk(%L)', chunk_name);
        RAISE NOTICE 'Decompressed chunk: %', chunk_name;
    END LOOP;
END $$;

-- Step 3: Drop compression
ALTER TABLE options_bars SET (
    timescaledb.compress = false
);

-- Step 4: Alter column types
ALTER TABLE options_bars
    ALTER COLUMN implied_volatility TYPE NUMERIC(10,6);

ALTER TABLE options_bars
    ALTER COLUMN delta TYPE NUMERIC(10,6),
    ALTER COLUMN gamma TYPE NUMERIC(10,6),
    ALTER COLUMN theta TYPE NUMERIC(10,6),
    ALTER COLUMN vega TYPE NUMERIC(10,6),
    ALTER COLUMN rho TYPE NUMERIC(10,6);

-- Step 5: Re-enable compression with same settings
ALTER TABLE options_bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'option_ticker, underlying_ticker',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Step 6: Re-add compression policy (compress data older than 7 days)
SELECT add_compression_policy('options_bars', INTERVAL '7 days');

-- Verify the changes
\echo 'Column types after migration:'
SELECT
    column_name,
    data_type,
    numeric_precision,
    numeric_scale
FROM information_schema.columns
WHERE table_name = 'options_bars'
    AND column_name IN ('implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho')
ORDER BY column_name;

-- Show compression status
\echo 'Compression status (recent chunks):'
SELECT
    chunk_name,
    is_compressed,
    range_start,
    range_end
FROM timescaledb_information.chunks
WHERE hypertable_name = 'options_bars'
ORDER BY range_start DESC
LIMIT 10;
