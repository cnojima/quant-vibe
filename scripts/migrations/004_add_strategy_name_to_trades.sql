-- ============================================================================
-- Add strategy_name to backtest_trades
-- ============================================================================
-- This migration adds strategy_name column to backtest_trades table for
-- easier querying and filtering without joining to backtest_runs
--
-- Usage:
--   docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < scripts/migrations/004_add_strategy_name_to_trades.sql
-- ============================================================================

-- Add strategy_name column to backtest_trades
ALTER TABLE backtest_trades
ADD COLUMN IF NOT EXISTS strategy_name TEXT;

-- Backfill strategy_name from backtest_runs
UPDATE backtest_trades bt
SET strategy_name = br.strategy_name
FROM backtest_runs br
WHERE bt.backtest_id = br.backtest_id
  AND bt.strategy_name IS NULL;

-- Add index for filtering by strategy
CREATE INDEX IF NOT EXISTS idx_backtest_trades_strategy_name
ON backtest_trades (strategy_name, entry_time DESC);

-- Rename columns to match expected schema
-- entry_cost -> entry_premium
-- exit_value -> exit_premium
-- pnl_percent -> pnl_pct
-- underlying_entry -> entry_underlying_price
-- underlying_exit -> exit_underlying_price

DO $$
BEGIN
    -- Check and rename entry_cost to entry_premium
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'backtest_trades' AND column_name = 'entry_cost'
    ) THEN
        ALTER TABLE backtest_trades RENAME COLUMN entry_cost TO entry_premium;
    END IF;

    -- Check and rename exit_value to exit_premium
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'backtest_trades' AND column_name = 'exit_value'
    ) THEN
        ALTER TABLE backtest_trades RENAME COLUMN exit_value TO exit_premium;
    END IF;

    -- Check and rename pnl_percent to pnl_pct
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'backtest_trades' AND column_name = 'pnl_percent'
    ) THEN
        ALTER TABLE backtest_trades RENAME COLUMN pnl_percent TO pnl_pct;
    END IF;

    -- Check and rename underlying_entry to entry_underlying_price
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'backtest_trades' AND column_name = 'underlying_entry'
    ) THEN
        ALTER TABLE backtest_trades RENAME COLUMN underlying_entry TO entry_underlying_price;
    END IF;

    -- Check and rename underlying_exit to exit_underlying_price
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'backtest_trades' AND column_name = 'underlying_exit'
    ) THEN
        ALTER TABLE backtest_trades RENAME COLUMN underlying_exit TO exit_underlying_price;
    END IF;
END $$;

-- Add max_risk column if it doesn't exist (expected by admin UI)
ALTER TABLE backtest_trades
ADD COLUMN IF NOT EXISTS max_risk NUMERIC(15, 2);

-- Grant permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO quantvibe;

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================================';
    RAISE NOTICE 'Migration 004 completed successfully!';
    RAISE NOTICE '============================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Changes made:';
    RAISE NOTICE '  - Added strategy_name column to backtest_trades';
    RAISE NOTICE '  - Backfilled strategy_name from backtest_runs';
    RAISE NOTICE '  - Renamed entry_cost -> entry_premium';
    RAISE NOTICE '  - Renamed exit_value -> exit_premium';
    RAISE NOTICE '  - Renamed pnl_percent -> pnl_pct';
    RAISE NOTICE '  - Renamed underlying_entry -> entry_underlying_price';
    RAISE NOTICE '  - Renamed underlying_exit -> exit_underlying_price';
    RAISE NOTICE '  - Added max_risk column';
    RAISE NOTICE '  - Created index on (strategy_name, entry_time)';
    RAISE NOTICE '';
    RAISE NOTICE '============================================================================';
END $$;
