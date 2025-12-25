-- Fix option_ticker values that start with 'SPX2' to use 'SPXW' instead
-- This handles cases where SPXW (weekly) contracts were incorrectly labeled as SPX2

-- ============================================================================
-- ANALYSIS: Check what needs to be fixed
-- ============================================================================

-- Count affected rows
SELECT
    'Rows to fix' as description,
    COUNT(*) as count
FROM options_bars
WHERE option_ticker LIKE 'SPX2%';

-- Show sample of affected rows
SELECT
    'Sample rows' as description,
    option_ticker,
    underlying_ticker,
    strike_price,
    contract_type,
    expiration_date,
    data_source,
    COUNT(*) as row_count
FROM options_bars
WHERE option_ticker LIKE 'SPX2%'
GROUP BY option_ticker, underlying_ticker, strike_price, contract_type, expiration_date, data_source
ORDER BY option_ticker
LIMIT 10;

-- Check for potential conflicts (tickers that would be created by the fix already exist)
SELECT
    'Potential conflicts' as description,
    COUNT(*) as count
FROM options_bars original
WHERE original.option_ticker LIKE 'SPX2%'
AND EXISTS (
    SELECT 1
    FROM options_bars existing
    WHERE existing.option_ticker = 'SPXW' || SUBSTRING(original.option_ticker FROM 5)
);

-- ============================================================================
-- BACKUP: Create backup table (RECOMMENDED)
-- ============================================================================

-- Create backup table with affected rows
DROP TABLE IF EXISTS options_bars_backup_spx2_fix;

CREATE TABLE options_bars_backup_spx2_fix AS
SELECT *
FROM options_bars
WHERE option_ticker LIKE 'SPX2%';

SELECT
    'Backup created' as status,
    COUNT(*) as backed_up_rows
FROM options_bars_backup_spx2_fix;

-- ============================================================================
-- FIX: Update option_ticker from SPX2* to SPXW*
-- ============================================================================

-- Perform the update
UPDATE options_bars
SET option_ticker = 'SPXW2' || SUBSTRING(option_ticker FROM 5)
WHERE option_ticker LIKE 'SPX2%';

-- Show results
SELECT
    'Update complete' as status,
    COUNT(*) as updated_rows
FROM options_bars
WHERE option_ticker LIKE 'SPXW%'
AND option_ticker IN (
    SELECT 'SPXW' || SUBSTRING(option_ticker FROM 5)
    FROM options_bars_backup_spx2_fix
);

-- ============================================================================
-- VERIFICATION: Confirm fix worked
-- ============================================================================

-- Should return 0 rows (no more SPX2 tickers)
SELECT
    'Remaining SPX2 tickers' as description,
    COUNT(*) as count
FROM options_bars
WHERE option_ticker LIKE 'SPX2%';

-- Should return > 0 rows (new SPXW tickers created)
SELECT
    'New SPXW tickers from fix' as description,
    COUNT(*) as count
FROM options_bars
WHERE option_ticker LIKE 'SPXW%'
AND option_ticker IN (
    SELECT 'SPXW' || SUBSTRING(option_ticker FROM 5)
    FROM options_bars_backup_spx2_fix
);

-- Compare before/after counts
SELECT
    'Before' as stage,
    COUNT(*) as count
FROM options_bars_backup_spx2_fix
UNION ALL
SELECT
    'After' as stage,
    COUNT(*) as count
FROM options_bars
WHERE option_ticker IN (
    SELECT 'SPXW' || SUBSTRING(option_ticker FROM 5)
    FROM options_bars_backup_spx2_fix
);

-- Show sample of fixed rows
SELECT
    backup.option_ticker as old_ticker,
    current.option_ticker as new_ticker,
    current.underlying_ticker,
    current.strike_price,
    current.contract_type,
    current.expiration_date,
    current.data_source
FROM options_bars_backup_spx2_fix backup
JOIN options_bars current ON
    current.timestamp = backup.timestamp
    AND current.option_ticker = 'SPXW' || SUBSTRING(backup.option_ticker FROM 5)
LIMIT 10;

-- ============================================================================
-- CLEANUP (optional - only run after verification)
-- ============================================================================

-- Uncomment to remove backup table after confirming fix worked
-- DROP TABLE IF EXISTS options_bars_backup_spx2_fix;

-- ============================================================================
-- NOTES
-- ============================================================================

-- This script:
-- 1. Analyzes which rows need fixing
-- 2. Creates a backup table
-- 3. Updates option_ticker: SPX2* → SPXW*
-- 4. Verifies the fix worked
-- 5. Preserves backup for safety

-- Example transformations:
-- SPX251226C06875000 → SPXW251226C06875000
-- SPX251227P06850000 → SPXW251227P06850000
-- SPX260123C06860000 → SPXW260123C06860000

-- IMPORTANT:
-- - Review the analysis output before running the UPDATE
-- - Check for conflicts (shouldn't happen but good to verify)
-- - Keep the backup table until you're confident the fix is correct
-- - The backup can be used to rollback if needed:
--   DELETE FROM options_bars WHERE option_ticker IN (SELECT 'SPXW' || SUBSTRING(option_ticker FROM 5) FROM options_bars_backup_spx2_fix);
--   INSERT INTO options_bars SELECT * FROM options_bars_backup_spx2_fix;
