-- Fix implied_volatility precision to allow values >= 100
--
-- Problem: Current schema uses NUMERIC(8,6) which only allows values < 100
-- Solution: Change to NUMERIC(10,6) to allow values up to 9999.999999
--
-- This handles cases where IV is expressed as percentage (e.g., 150%) instead of decimal (1.50)

BEGIN;

-- Alter the main options_bars table
ALTER TABLE options_bars
ALTER COLUMN implied_volatility TYPE NUMERIC(10,6);

-- Also fix the Greeks columns to use same precision for consistency
ALTER TABLE options_bars
ALTER COLUMN delta TYPE NUMERIC(10,6),
ALTER COLUMN gamma TYPE NUMERIC(10,6),
ALTER COLUMN theta TYPE NUMERIC(10,6),
ALTER COLUMN vega TYPE NUMERIC(10,6),
ALTER COLUMN rho TYPE NUMERIC(10,6);

COMMIT;

-- Verify the changes
\d options_bars
