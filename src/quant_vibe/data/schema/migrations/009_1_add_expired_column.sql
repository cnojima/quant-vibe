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
-- Step 2: Migrate existing -9.0 sentinel values
-- =============================================================================

-- Mark records with -9.0 IV as expired and clean up the sentinel values
UPDATE options_bars
SET
    expired = true,
    implied_volatility = NULL,
    delta = NULL,
    gamma = NULL,
    theta = NULL,
    vega = NULL,
    rho = NULL
WHERE implied_volatility = -9.0;

-- Also check for -9.0 in other greeks (defensive)
UPDATE options_bars
SET
    expired = true,
    delta = CASE WHEN delta = -9.0 THEN NULL ELSE delta END,
    gamma = CASE WHEN gamma = -9.0 THEN NULL ELSE gamma END,
    theta = CASE WHEN theta = -9.0 THEN NULL ELSE theta END,
    vega = CASE WHEN vega = -9.0 THEN NULL ELSE vega END,
    rho = CASE WHEN rho = -9.0 THEN NULL ELSE rho END,
    implied_volatility = CASE WHEN implied_volatility = -9.0 THEN NULL ELSE implied_volatility END
WHERE expired = false
  AND (
    delta = -9.0 OR
    gamma = -9.0 OR
    theta = -9.0 OR
    vega = -9.0 OR
    rho = -9.0
  );

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
