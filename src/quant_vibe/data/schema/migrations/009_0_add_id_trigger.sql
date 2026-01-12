-- Migration 009: Add trigger to ensure ID is always populated
-- Date: 2026-01-11
-- Purpose: Protect against NULL IDs by auto-populating from sequence
--
-- This is a defensive measure to handle edge cases where something
-- tries to INSERT or UPDATE with a NULL id value.
-- Usage:
--    PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/009_0_add_id_trigger.sql
-- Create trigger function
CREATE OR REPLACE FUNCTION ensure_options_bars_id()
RETURNS TRIGGER AS $$
BEGIN
    -- If id is NULL, populate it
    IF NEW.id IS NULL THEN
        -- For UPDATE: try to preserve OLD.id if it exists
        IF TG_OP = 'UPDATE' AND OLD.id IS NOT NULL THEN
            NEW.id := OLD.id;
        ELSE
            -- For INSERT or UPDATE with NULL old id: get new id from sequence
            NEW.id := nextval('options_bars_id_seq'::regclass);
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger (fires before INSERT and UPDATE)
DROP TRIGGER IF EXISTS tr_ensure_options_bars_id ON options_bars;
CREATE TRIGGER tr_ensure_options_bars_id
    BEFORE INSERT OR UPDATE ON options_bars
    FOR EACH ROW
    EXECUTE FUNCTION ensure_options_bars_id();

-- Verification
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'tr_ensure_options_bars_id'
        AND tgrelid = 'options_bars'::regclass
    ) THEN
        RAISE NOTICE 'Trigger tr_ensure_options_bars_id created successfully';
    ELSE
        RAISE EXCEPTION 'Failed to create trigger';
    END IF;
END $$;

-- Test the trigger with INSERT and UPDATE
DO $$
DECLARE
    test_id_insert BIGINT;
    test_id_before_update BIGINT;
    test_id_after_update BIGINT;
BEGIN
    -- Test 1: INSERT with NULL id (trigger should populate it)
    INSERT INTO options_bars (
        timestamp, option_ticker, underlying_ticker,
        open, high, low, close, strike_price, contract_type,
        expiration_date
    ) VALUES (
        NOW(), 'TEST_TRIGGER_DELETE_ME', 'SPX',
        100, 100, 100, 100, 5000, 'call',
        CURRENT_DATE
    ) RETURNING id INTO test_id_insert;

    IF test_id_insert IS NULL THEN
        RAISE EXCEPTION 'INSERT test failed: ID is still NULL';
    END IF;
    RAISE NOTICE 'INSERT test passed: ID auto-populated to %', test_id_insert;

    -- Test 2: UPDATE the row (trigger should preserve the ID)
    SELECT id INTO test_id_before_update
    FROM options_bars
    WHERE option_ticker = 'TEST_TRIGGER_DELETE_ME';

    UPDATE options_bars
    SET open = 101, close = 101
    WHERE option_ticker = 'TEST_TRIGGER_DELETE_ME'
    RETURNING id INTO test_id_after_update;

    IF test_id_after_update IS NULL THEN
        RAISE EXCEPTION 'UPDATE test failed: ID became NULL';
    END IF;

    IF test_id_before_update != test_id_after_update THEN
        RAISE EXCEPTION 'UPDATE test failed: ID changed from % to %',
            test_id_before_update, test_id_after_update;
    END IF;

    RAISE NOTICE 'UPDATE test passed: ID preserved as %', test_id_after_update;

    -- Clean up test row
    DELETE FROM options_bars WHERE option_ticker = 'TEST_TRIGGER_DELETE_ME';
    RAISE NOTICE 'All trigger tests passed!';
END $$;

-- Migration completed successfully
