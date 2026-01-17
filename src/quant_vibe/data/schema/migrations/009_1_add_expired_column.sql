-- Migration: Add 'expired' column to mark expired contracts
-- Replaces the -9.0 sentinel value approach with proper boolean flag
--
-- Run with:
-- PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -f src/quant_vibe/data/schema/migrations/009_1_add_expired_column.sql
SET timescaledb.max_tuples_decompressed_per_dml_transaction TO 0;

BEGIN;

-- =============================================================================
-- Step 1: Add 'expired' column to base table (options_bars)
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
-- Step 2: Migrate existing -9.0 sentinel values (OPTIMIZED WITH BATCHING)
-- =============================================================================

-- First, check if migration is already complete
DO $$
DECLARE
    records_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO records_count
    FROM (
        SELECT 1 FROM options_bars
        WHERE implied_volatility = -9.0
        LIMIT 1
    ) t;

    IF records_count = 0 THEN
        RAISE NOTICE 'No records with implied_volatility = -9.0 found, skipping migration';
    ELSE
        RAISE NOTICE 'Found records to migrate, processing...';
    END IF;
END $$;

-- Process implied_volatility = -9.0 in batches to avoid timeout
DO $$
DECLARE
    batch_size INTEGER := 5000;
    rows_updated INTEGER;
    total_updated INTEGER := 0;
BEGIN
    LOOP
        -- Update in batches using CTID for efficiency
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

        -- Progress log every 25k records
        IF total_updated % 25000 = 0 THEN
            RAISE NOTICE 'Processed % records...', total_updated;
        END IF;
    END LOOP;

    RAISE NOTICE 'Completed: % total records updated', total_updated;
END $$;

-- Skip the complex multi-column check as it's rarely needed and causes timeouts
-- If needed, run separately with: UPDATE options_bars SET expired=true WHERE delta=-9.0 OR gamma=-9.0...

COMMIT;

-- =============================================================================
-- Step 4: Verification
-- =============================================================================

-- Show summary of expired contracts
SELECT
    'options_bars' as table_name,
    COUNT(*) FILTER (WHERE expired = true) as expired_count,
    COUNT(*) FILTER (WHERE expired = false) as active_count,
    COUNT(*) FILTER (WHERE implied_volatility = -9.0) as still_has_negative_nine,
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

-- =============================================================================
-- Rollback (if needed)
-- =============================================================================

-- To rollback this migration:
-- BEGIN;
-- ALTER TABLE options_bars DROP COLUMN IF EXISTS expired;
-- COMMIT;
