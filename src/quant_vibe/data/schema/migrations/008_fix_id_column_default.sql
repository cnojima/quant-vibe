-- Migration 009: Fix ID column default for TimescaleDB hypertable chunks
-- Date: 2026-01-11
-- Purpose: Ensure ID column default propagates correctly to all chunks
--
-- Background: When adding a BIGSERIAL column to a hypertable, new chunks
-- created after the migration may not properly inherit the default value.
-- This migration ensures all chunks have the correct default.
-- Usage:
--    PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/008_fix_id_column_default.sql
-- Step 1: Verify the sequence exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = 'options_bars_id_seq') THEN
        RAISE EXCEPTION 'Sequence options_bars_id_seq does not exist. Run migration 007 first.';
    END IF;
    RAISE NOTICE 'Sequence options_bars_id_seq exists';
END $$;

-- Step 2: Ensure the column has the default on the parent table
ALTER TABLE options_bars
ALTER COLUMN id SET DEFAULT nextval('options_bars_id_seq'::regclass);

-- Step 3: Fix any NULL id values that might exist
-- (This shouldn't happen, but let's be safe)
DO $$
DECLARE
    null_count BIGINT;
    max_id BIGINT;
BEGIN
    -- Count NULL ids
    SELECT COUNT(*) INTO null_count FROM options_bars WHERE id IS NULL;

    IF null_count > 0 THEN
        RAISE NOTICE 'Found % rows with NULL id, backfilling...', null_count;

        -- Get current max ID
        SELECT COALESCE(MAX(id), 0) INTO max_id FROM options_bars WHERE id IS NOT NULL;

        -- Backfill NULL ids with new sequence values
        -- We use a temp sequence starting after max_id
        WITH null_rows AS (
            SELECT ctid, ROW_NUMBER() OVER (ORDER BY timestamp, option_ticker) as rn
            FROM options_bars
            WHERE id IS NULL
        )
        UPDATE options_bars
        SET id = max_id + null_rows.rn
        FROM null_rows
        WHERE options_bars.ctid = null_rows.ctid;

        -- Adjust the sequence to account for the backfilled values
        PERFORM setval('options_bars_id_seq', max_id + null_count);

        RAISE NOTICE 'Backfilled % rows with new id values', null_count;
    ELSE
        RAISE NOTICE 'No NULL id values found';
    END IF;
END $$;

-- Step 4: Add a constraint to prevent NULL ids in the future
-- (Already should be NOT NULL, but let's enforce it)
ALTER TABLE options_bars
ALTER COLUMN id SET NOT NULL;

-- Step 5: Verify the fix
DO $$
DECLARE
    null_count BIGINT;
    default_value TEXT;
BEGIN
    -- Check for NULL ids
    SELECT COUNT(*) INTO null_count FROM options_bars WHERE id IS NULL;

    -- Get the default value
    SELECT pg_get_expr(d.adbin, d.adrelid) INTO default_value
    FROM pg_attribute a
    LEFT JOIN pg_attrdef d ON (a.attrelid, a.attnum) = (d.adrelid, d.adnum)
    WHERE a.attrelid = 'options_bars'::regclass
    AND a.attname = 'id';

    RAISE NOTICE 'Migration 009 verification:';
    RAISE NOTICE '  NULL id count: %', null_count;
    RAISE NOTICE '  Default value: %', default_value;

    IF null_count > 0 THEN
        RAISE EXCEPTION 'Migration failed: Still have % rows with NULL id', null_count;
    END IF;

    IF default_value IS NULL OR default_value NOT LIKE '%nextval%' THEN
        RAISE EXCEPTION 'Migration failed: Default value not properly set';
    END IF;

    RAISE NOTICE 'Migration 009 completed successfully!';
END $$;
