-- Migration 007: Add ID column to options_bars and make it the primary key
-- Date: 2026-01-11
-- Purpose: Replace composite (timestamp, option_ticker) key with auto-incrementing ID
--          to handle duplicate entries and improve performance
-- Usage:
--   PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/007_add_id_column_to_options_bars.sql

-- Step 1: Drop existing primary key constraint if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'options_bars_pkey'
        AND conrelid = 'options_bars'::regclass
    ) THEN
        ALTER TABLE options_bars DROP CONSTRAINT options_bars_pkey CASCADE;
        RAISE NOTICE 'Dropped existing options_bars_pkey constraint';
    ELSE
        RAISE NOTICE 'No existing primary key constraint found';
    END IF;
END $$;

-- Step 2: Add the ID column
-- Using BIGSERIAL for large-scale data (auto-incrementing BIGINT)
ALTER TABLE options_bars ADD COLUMN IF NOT EXISTS id BIGSERIAL;

-- Step 3: Backfill ID values for existing rows (if needed)
-- This is handled automatically by SERIAL, but we verify
DO $$
DECLARE
    null_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO null_count FROM options_bars WHERE id IS NULL;
    IF null_count > 0 THEN
        RAISE NOTICE 'Found % rows with NULL id, this should not happen with SERIAL', null_count;
    ELSE
        RAISE NOTICE 'All rows have id values';
    END IF;
END $$;

-- Step 4: Create the new primary key on ID column
-- For TimescaleDB hypertables, we need to include the partitioning column (timestamp) in the PK
ALTER TABLE options_bars ADD CONSTRAINT options_bars_pkey PRIMARY KEY (id, timestamp);

-- Step 5: Create a non-unique index on (timestamp, option_ticker) for queries
-- This replaces the old primary key but allows duplicates
CREATE INDEX IF NOT EXISTS idx_options_bars_timestamp_ticker
ON options_bars (timestamp, option_ticker);

-- Step 6: Verify the migration
DO $$
DECLARE
    pk_count INTEGER;
    idx_count INTEGER;
BEGIN
    -- Check primary key exists
    SELECT COUNT(*) INTO pk_count
    FROM pg_constraint
    WHERE conname = 'options_bars_pkey'
    AND conrelid = 'options_bars'::regclass;

    -- Check index exists
    SELECT COUNT(*) INTO idx_count
    FROM pg_indexes
    WHERE tablename = 'options_bars'
    AND indexname = 'idx_options_bars_timestamp_ticker';

    RAISE NOTICE 'Migration verification:';
    RAISE NOTICE '  Primary key exists: %', pk_count > 0;
    RAISE NOTICE '  Timestamp/ticker index exists: %', idx_count > 0;

    IF pk_count = 0 THEN
        RAISE EXCEPTION 'Migration failed: Primary key not created';
    END IF;
END $$;

-- Step 7: Show table info
\d options_bars

-- Step 8: Report on duplicate entries (for information only)
SELECT 'Duplicate (timestamp, option_ticker) pairs:' as info, COUNT(*) as count
FROM (
    SELECT timestamp, option_ticker
    FROM options_bars
    GROUP BY timestamp, option_ticker
    HAVING COUNT(*) > 1
) dups;

-- Migration completed successfully
