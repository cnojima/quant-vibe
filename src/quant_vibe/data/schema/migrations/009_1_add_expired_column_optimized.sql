-- Migration: Add 'expired' column to mark expired contracts (OPTIMIZED)
-- Replaces the -9.0 sentinel value approach with proper boolean flag
--
-- This optimized version processes data in batches to avoid timeouts on large tables
-- Run with:
-- PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -f src/quant_vibe/data/schema/migrations/009_1_add_expired_column_optimized.sql

SET timescaledb.max_tuples_decompressed_per_dml_transaction TO 0;

BEGIN;

-- =============================================================================
-- Step 1: Add 'expired' column to base table (if not exists)
-- =============================================================================

ALTER TABLE options_bars
ADD COLUMN IF NOT EXISTS expired BOOLEAN DEFAULT false;

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_options_bars_expired
ON options_bars(expired)
WHERE expired = true;

COMMENT ON COLUMN options_bars.expired IS
'Flag indicating if contract has expired (true) or is still valid (false). Replaces -9.0 sentinel value.';

-- =============================================================================
-- Step 2: Check if migration is already complete
-- =============================================================================

DO $$
DECLARE
    records_to_process INTEGER;
BEGIN
    -- Count records that still need processing
    SELECT COUNT(*) INTO records_to_process
    FROM options_bars
    WHERE implied_volatility = -9.0
    LIMIT 1000;  -- Check first 1000 to avoid full scan

    IF records_to_process = 0 THEN
        RAISE NOTICE 'Migration already complete - no -9.0 values found';
    ELSE
        RAISE NOTICE 'Found records to process, continuing migration...';
    END IF;
END $$;

-- =============================================================================
-- Step 3: Migrate existing -9.0 sentinel values (BATCH PROCESSING)
-- =============================================================================

-- First pass: Handle implied_volatility = -9.0 (most common case)
-- Process in smaller chunks by time range to avoid long-running queries
DO $$
DECLARE
    batch_size INTEGER := 10000;
    rows_updated INTEGER;
    total_updated INTEGER := 0;
    start_time TIMESTAMP;
    end_time TIMESTAMP;
BEGIN
    -- Get time range
    SELECT MIN(timestamp), MAX(timestamp)
    INTO start_time, end_time
    FROM options_bars
    WHERE implied_volatility = -9.0
    LIMIT 1;

    IF start_time IS NULL THEN
        RAISE NOTICE 'No records with implied_volatility = -9.0 found';
    ELSE
        RAISE NOTICE 'Processing records from % to %', start_time, end_time;

        -- Process in batches using CTID for efficient updates
        LOOP
            UPDATE options_bars
            SET
                expired = true,
                implied_volatility = NULL,
                delta = NULL,
                gamma = NULL,
                theta = NULL,
                vega = NULL,
                rho = NULL
            WHERE ctid IN (
                SELECT ctid
                FROM options_bars
                WHERE implied_volatility = -9.0
                  AND expired = false
                LIMIT batch_size
            );

            GET DIAGNOSTICS rows_updated = ROW_COUNT;
            total_updated := total_updated + rows_updated;

            EXIT WHEN rows_updated = 0;

            -- Progress indicator
            IF total_updated % 50000 = 0 THEN
                RAISE NOTICE 'Processed % records...', total_updated;
            END IF;

            -- Brief pause to avoid overwhelming the system
            PERFORM pg_sleep(0.1);
        END LOOP;

        RAISE NOTICE 'Total records with IV=-9.0 updated: %', total_updated;
    END IF;
END $$;

-- Second pass: Handle other greeks with -9.0 (less common, skip if too slow)
-- This is optional and can be commented out if the table is too large
DO $$
DECLARE
    other_greeks_count INTEGER;
BEGIN
    -- Quick check if there are any other -9.0 values
    SELECT COUNT(*) INTO other_greeks_count
    FROM (
        SELECT 1 FROM options_bars
        WHERE expired = false
          AND (delta = -9.0 OR gamma = -9.0 OR theta = -9.0 OR vega = -9.0 OR rho = -9.0)
        LIMIT 100
    ) t;

    IF other_greeks_count > 0 THEN
        RAISE NOTICE 'Found other greeks with -9.0, processing in small batch...';

        -- Process only first 1000 records to avoid timeout
        UPDATE options_bars
        SET
            expired = true,
            delta = CASE WHEN delta = -9.0 THEN NULL ELSE delta END,
            gamma = CASE WHEN gamma = -9.0 THEN NULL ELSE gamma END,
            theta = CASE WHEN theta = -9.0 THEN NULL ELSE theta END,
            vega = CASE WHEN vega = -9.0 THEN NULL ELSE vega END,
            rho = CASE WHEN rho = -9.0 THEN NULL ELSE rho END
        WHERE ctid IN (
            SELECT ctid
            FROM options_bars
            WHERE expired = false
              AND (delta = -9.0 OR gamma = -9.0 OR theta = -9.0 OR vega = -9.0 OR rho = -9.0)
            LIMIT 1000
        );

        RAISE NOTICE 'Processed first batch of other greeks with -9.0';
    ELSE
        RAISE NOTICE 'No other greeks with -9.0 found';
    END IF;
END $$;

COMMIT;

-- =============================================================================
-- Step 4: Verification (Run separately after commit)
-- =============================================================================

-- Show summary of expired contracts
SELECT
    'options_bars' as table_name,
    COUNT(*) FILTER (WHERE expired = true) as expired_count,
    COUNT(*) FILTER (WHERE expired = false) as active_count,
    COUNT(*) FILTER (WHERE implied_volatility = -9.0) as remaining_negative_nine,
    COUNT(*) as total
FROM options_bars;

-- Show sample of migrated records
SELECT
    timestamp,
    option_ticker,
    expired,
    implied_volatility,
    delta,
    gamma
FROM options_bars
WHERE expired = true
LIMIT 5;

-- Check for any remaining -9.0 values (should be minimal or zero)
SELECT COUNT(*) as remaining_sentinel_values
FROM options_bars
WHERE implied_volatility = -9.0
   OR delta = -9.0
   OR gamma = -9.0
   OR theta = -9.0
   OR vega = -9.0
   OR rho = -9.0;

-- =============================================================================
-- Notes:
-- =============================================================================
-- If this migration times out, you can:
-- 1. Run it multiple times - it's idempotent and will continue where it left off
-- 2. Adjust the batch_size variable to process smaller chunks
-- 3. Comment out the second pass if not needed
-- 4. Run during off-peak hours when the database has less load