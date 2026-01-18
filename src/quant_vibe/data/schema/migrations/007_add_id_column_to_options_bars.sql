-- Migration 007: Add ID column to options_bars (SAFE VERSION)
-- This version is safe for large tables and won't crash the database
-- Date: 2026-01-17
-- Purpose: Add auto-incrementing ID column without creating constraints that crash the DB

BEGIN;

-- Step 1: Add the ID column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'options_bars' AND column_name = 'id') THEN
        -- Create sequence if not exists
        CREATE SEQUENCE IF NOT EXISTS options_bars_id_seq;

        -- Add column with proper type and default
        ALTER TABLE options_bars ADD COLUMN id BIGINT DEFAULT nextval('options_bars_id_seq');

        -- Set sequence ownership
        ALTER SEQUENCE options_bars_id_seq OWNED BY options_bars.id;

        RAISE NOTICE 'Added id column to options_bars';
    ELSE
        RAISE NOTICE 'Column id already exists, skipping';

        -- Ensure the sequence exists and is properly set
        IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'options_bars_id_seq') THEN
            CREATE SEQUENCE options_bars_id_seq;
            ALTER TABLE options_bars ALTER COLUMN id SET DEFAULT nextval('options_bars_id_seq');
            ALTER SEQUENCE options_bars_id_seq OWNED BY options_bars.id;
            RAISE NOTICE 'Created missing sequence for existing id column';
        END IF;
    END IF;
END $$;

-- Step 2: Create non-unique indexes for performance
-- These don't require uniqueness so they're safe for hypertables
CREATE INDEX IF NOT EXISTS idx_options_bars_id ON options_bars (id);
CREATE INDEX IF NOT EXISTS idx_options_bars_id_timestamp ON options_bars (id, timestamp);
CREATE INDEX IF NOT EXISTS idx_options_bars_timestamp_ticker ON options_bars (timestamp, option_ticker);

COMMIT;

-- Step 3: Verify the migration (non-transactional)
DO $$
DECLARE
    has_id_column BOOLEAN;
    has_indexes BOOLEAN;
    sample_count INTEGER;
BEGIN
    -- Check column exists
    SELECT EXISTS(SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'options_bars' AND column_name = 'id')
    INTO has_id_column;

    -- Check indexes exist
    SELECT COUNT(*) > 0 FROM pg_indexes
    WHERE tablename = 'options_bars' AND indexname LIKE '%id%'
    INTO has_indexes;

    -- Get sample count
    SELECT COUNT(*) FROM (SELECT 1 FROM options_bars WHERE id IS NOT NULL LIMIT 1000) t
    INTO sample_count;

    RAISE NOTICE 'Migration 007 verification:';
    RAISE NOTICE '  ID column exists: %', has_id_column;
    RAISE NOTICE '  ID indexes exist: %', has_indexes;
    RAISE NOTICE '  Sample records with ID: %', sample_count;

    IF has_id_column AND sample_count > 0 THEN
        RAISE NOTICE 'Migration 007 completed successfully';
    ELSE
        RAISE WARNING 'Migration 007 may not be complete - please verify manually';
    END IF;
END $$;