-- Fix contract_type values from single letters to full words
-- This migration standardizes 'c'/'p' (from Massive API) to 'call'/'put' (Schwab format)

-- Temporarily increase decompression limit for this migration
-- (TimescaleDB compresses old data and needs to decompress it for updates)
SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0;  -- unlimited

BEGIN;

-- Show current state
SELECT
    contract_type,
    COUNT(*) as count,
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest
FROM options_bars
GROUP BY contract_type
ORDER BY contract_type;

-- Update 'c' to 'call'
UPDATE options_bars
SET contract_type = 'call'
WHERE contract_type = 'c';

-- Update 'p' to 'put'
UPDATE options_bars
SET contract_type = 'put'
WHERE contract_type = 'p';

-- Show new state
SELECT
    contract_type,
    COUNT(*) as count,
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest
FROM options_bars
GROUP BY contract_type
ORDER BY contract_type;

-- Commit the changes
COMMIT;

-- Verification query
SELECT
    'Total records: ' || COUNT(*) as summary
FROM options_bars
UNION ALL
SELECT
    'Call contracts: ' || COUNT(*)
FROM options_bars
WHERE contract_type = 'call'
UNION ALL
SELECT
    'Put contracts: ' || COUNT(*)
FROM options_bars
WHERE contract_type = 'put'
UNION ALL
SELECT
    'Invalid contract_type: ' || COUNT(*)
FROM options_bars
WHERE contract_type NOT IN ('call', 'put');
