-- ============================================================================
-- Migration 010: Trading Mode Schemas (Real/Paper/Replay Isolation)
-- ============================================================================
-- Purpose: Create completely isolated schemas for real, paper, and replay trading
-- Strategy: Zero breaking changes - 100% backward compatible with existing code
-- Date: 2026-01-12
-- ============================================================================
-- Usage:
--    PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/010_add_trading_modes.sql
-- ============================================================================
-- STEP 1: Create Trading Mode Schemas
-- ============================================================================
-- Note: Only real and paper schemas - replay is just a data source, not a mode

CREATE SCHEMA IF NOT EXISTS real_trading;
CREATE SCHEMA IF NOT EXISTS paper_trading;

COMMENT ON SCHEMA real_trading IS 'Real money trading data (persistent)';
COMMENT ON SCHEMA paper_trading IS 'Paper trading data (persistent - use for replay testing too)';

-- ============================================================================
-- STEP 2: Grant Permissions
-- ============================================================================

GRANT ALL ON SCHEMA real_trading TO quantvibe;
GRANT ALL ON SCHEMA paper_trading TO quantvibe;

-- ============================================================================
-- STEP 3: Create Tables in Each Schema
-- ============================================================================
-- We'll use a function to create identical tables in each schema

CREATE OR REPLACE FUNCTION create_trading_mode_tables(schema_name TEXT)
RETURNS VOID AS $$
DECLARE
    full_table_name TEXT;
BEGIN
    -- ========================================================================
    -- POSITIONS TABLE
    -- ========================================================================
    -- Identical to current live_positions table

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.positions (
            position_id TEXT PRIMARY KEY,
            strategy_name TEXT NOT NULL,
            spread_type TEXT NOT NULL,

            -- Entry
            entry_time TIMESTAMPTZ NOT NULL,
            entry_cost NUMERIC(15, 2) NOT NULL,
            underlying_price_at_entry NUMERIC(12, 4) NOT NULL,

            -- Current state
            status TEXT NOT NULL DEFAULT ''open'',
            current_value NUMERIC(15, 2),

            -- Exit
            exit_time TIMESTAMPTZ,
            exit_value NUMERIC(15, 2),
            exit_reason TEXT,

            -- Position details
            legs JSONB NOT NULL,
            metadata JSONB,

            -- Timestamps
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )', schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_positions_status
        ON %I.positions(status, strategy_name)',
        schema_name, schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_positions_entry_time
        ON %I.positions(entry_time DESC)',
        schema_name, schema_name);

    EXECUTE format('
        COMMENT ON TABLE %I.positions IS ''Trading positions for %I mode''',
        schema_name, schema_name);

    -- ========================================================================
    -- ORDERS TABLE
    -- ========================================================================
    -- Identical to current live_orders table

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.orders (
            order_id TEXT PRIMARY KEY,
            position_id TEXT REFERENCES %I.positions(position_id),
            strategy_name TEXT NOT NULL,

            -- Order details
            order_type TEXT NOT NULL,
            action_type TEXT,  -- ''opening'' or ''closing''
            side TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            symbol TEXT NOT NULL,

            -- Status tracking
            status TEXT NOT NULL DEFAULT ''pending'',
            submitted_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            filled_time TIMESTAMPTZ,

            -- Pricing
            expected_price NUMERIC(12, 4),
            filled_price NUMERIC(12, 4),
            filled_quantity INTEGER,

            -- Broker integration
            broker_order_id TEXT,
            error_message TEXT,

            -- Metadata
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )', schema_name, schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_orders_position
        ON %I.orders(position_id)',
        schema_name, schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_orders_status
        ON %I.orders(status)',
        schema_name, schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_orders_submitted
        ON %I.orders(submitted_time DESC)',
        schema_name, schema_name);

    EXECUTE format('
        COMMENT ON TABLE %I.orders IS ''Order tracking for %I mode''',
        schema_name, schema_name);

    -- ========================================================================
    -- STRATEGY STATE TABLE
    -- ========================================================================
    -- Based on current live_strategy_state with optional new fields

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.strategy_state (
            strategy_name TEXT PRIMARY KEY,

            -- Core state (existing)
            state JSONB NOT NULL,
            last_reset TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- NEW: Optional tracking fields (with defaults for backward compatibility)
            enabled BOOLEAN DEFAULT true,
            trades_today INTEGER DEFAULT 0,
            pnl_today NUMERIC(15, 2) DEFAULT 0
        )', schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_strategy_state_enabled
        ON %I.strategy_state(enabled)',
        schema_name, schema_name);

    EXECUTE format('
        COMMENT ON TABLE %I.strategy_state IS ''Strategy state for %I mode''',
        schema_name, schema_name);

    -- ========================================================================
    -- ENGINE STATE TABLE
    -- ========================================================================
    -- Historical log like current live_engine_state

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.engine_state (
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            id SERIAL,

            -- Core state (existing)
            state TEXT NOT NULL,
            metadata JSONB,

            -- NEW: Optional session tracking (with defaults for backward compatibility)
            session_start_time TIMESTAMPTZ,
            session_end_time TIMESTAMPTZ,
            config JSONB,
            last_heartbeat TIMESTAMPTZ,

            PRIMARY KEY (timestamp, id),
            UNIQUE(timestamp)
        )', schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_engine_state_time
        ON %I.engine_state(timestamp DESC)',
        schema_name, schema_name);

    EXECUTE format('
        COMMENT ON TABLE %I.engine_state IS ''Engine state log for %I mode (historical)''',
        schema_name, schema_name);

    -- ========================================================================
    -- EVENTS TABLE (HYPERTABLE)
    -- ========================================================================
    -- Identical to current live_events table

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.events (
            timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            id SERIAL,
            event_type TEXT NOT NULL,
            strategy_name TEXT,
            position_id TEXT,
            order_id TEXT,
            severity TEXT NOT NULL DEFAULT ''info'',
            message TEXT NOT NULL,
            details JSONB,
            PRIMARY KEY (timestamp, id)
        )', schema_name);

    -- Create indexes before hypertable conversion
    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_events_strategy
        ON %I.events(strategy_name, timestamp DESC)',
        schema_name, schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_events_severity
        ON %I.events(severity, timestamp DESC)',
        schema_name, schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_events_type
        ON %I.events(event_type, timestamp DESC)',
        schema_name, schema_name);

    EXECUTE format('
        CREATE INDEX IF NOT EXISTS idx_%I_events_position
        ON %I.events(position_id, timestamp DESC)',
        schema_name, schema_name);

    -- Convert to hypertable for time-series optimization
    BEGIN
        EXECUTE format('
            SELECT create_hypertable(''%I.events'', ''timestamp'',
                migrate_data => TRUE,
                if_not_exists => TRUE)', schema_name);
    EXCEPTION
        WHEN OTHERS THEN
            -- Hypertable creation failed (maybe extension not available)
            -- Table still works as regular table
            RAISE NOTICE 'Could not create hypertable for %.events (not critical)', schema_name;
    END;

    EXECUTE format('
        COMMENT ON TABLE %I.events IS ''Audit log for %I mode (hypertable)''',
        schema_name, schema_name);

    -- ========================================================================
    -- ACCOUNT BALANCE TABLE (NEW)
    -- ========================================================================
    -- NEW: Track account balance and P&L metrics per mode

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.account_balance (
            id INTEGER PRIMARY KEY DEFAULT 1,  -- Singleton: only one row

            -- Balance tracking
            cash NUMERIC(15, 2) NOT NULL DEFAULT 100000.00,
            portfolio_value NUMERIC(15, 2) NOT NULL DEFAULT 100000.00,
            total_pnl NUMERIC(15, 2) DEFAULT 0,

            -- Daily metrics
            daily_pnl NUMERIC(15, 2) DEFAULT 0,
            daily_return_pct NUMERIC(10, 4) DEFAULT 0,

            -- Lifetime metrics
            total_trades INTEGER DEFAULT 0,
            winning_trades INTEGER DEFAULT 0,
            losing_trades INTEGER DEFAULT 0,
            win_rate NUMERIC(10, 4) DEFAULT 0,

            -- Risk metrics
            max_drawdown NUMERIC(10, 4) DEFAULT 0,
            sharpe_ratio NUMERIC(10, 4) DEFAULT 0,

            -- Timestamps
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )', schema_name);

    EXECUTE format('
        CREATE UNIQUE INDEX IF NOT EXISTS idx_%I_account_balance_singleton
        ON %I.account_balance(id)',
        schema_name, schema_name);

    EXECUTE format('
        COMMENT ON TABLE %I.account_balance IS ''Account balance and metrics for %I mode (singleton)''',
        schema_name, schema_name);

    -- Initialize with default balance if not exists
    EXECUTE format('
        INSERT INTO %I.account_balance (id, cash, portfolio_value, total_pnl)
        VALUES (1, 100000.00, 100000.00, 0)
        ON CONFLICT (id) DO NOTHING', schema_name);

END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STEP 4: Create Tables in Both Schemas
-- ============================================================================

SELECT create_trading_mode_tables('real_trading');
SELECT create_trading_mode_tables('paper_trading');

-- ============================================================================
-- STEP 5: Grant Permissions on All Tables
-- ============================================================================

GRANT ALL ON ALL TABLES IN SCHEMA real_trading TO quantvibe;
GRANT ALL ON ALL SEQUENCES IN SCHEMA real_trading TO quantvibe;
GRANT ALL ON ALL TABLES IN SCHEMA paper_trading TO quantvibe;
GRANT ALL ON ALL SEQUENCES IN SCHEMA paper_trading TO quantvibe;

-- ============================================================================
-- STEP 6: Helper Functions
-- ============================================================================

-- Function to get account balance for a mode
CREATE OR REPLACE FUNCTION get_account_balance(p_mode TEXT)
RETURNS TABLE (
    cash NUMERIC,
    portfolio_value NUMERIC,
    total_pnl NUMERIC,
    daily_pnl NUMERIC,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY EXECUTE format('
        SELECT
            cash, portfolio_value, total_pnl, daily_pnl,
            total_trades, winning_trades, losing_trades, win_rate
        FROM %I.account_balance
        WHERE id = 1
    ', p_mode || '_trading');
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_account_balance(TEXT) IS
'Get account balance for a trading mode (real/paper/replay)';

-- Function to update account balance
CREATE OR REPLACE FUNCTION update_account_balance(
    p_mode TEXT,
    p_cash NUMERIC,
    p_portfolio_value NUMERIC,
    p_daily_pnl NUMERIC DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    EXECUTE format('
        UPDATE %I.account_balance
        SET
            cash = $1,
            portfolio_value = $2,
            total_pnl = $2 - (SELECT cash FROM %I.account_balance WHERE id = 1 LIMIT 1),
            daily_pnl = COALESCE($3, daily_pnl),
            updated_at = NOW()
        WHERE id = 1
    ', p_mode || '_trading', p_mode || '_trading')
    USING p_cash, p_portfolio_value, p_daily_pnl;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_account_balance IS
'Update account balance for a trading mode';

-- Function to get open positions count per mode
CREATE OR REPLACE FUNCTION get_open_positions_count(p_mode TEXT)
RETURNS INTEGER AS $$
DECLARE
    count INTEGER;
BEGIN
    EXECUTE format('
        SELECT COUNT(*) FROM %I.positions WHERE status = ''open''
    ', p_mode || '_trading') INTO count;

    RETURN count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_open_positions_count IS
'Get count of open positions for a trading mode';

-- Function to clear paper trading data (useful for replay testing)
CREATE OR REPLACE FUNCTION clear_paper_data()
RETURNS VOID AS $$
BEGIN
    TRUNCATE TABLE paper_trading.positions CASCADE;
    TRUNCATE TABLE paper_trading.orders CASCADE;
    TRUNCATE TABLE paper_trading.strategy_state CASCADE;
    TRUNCATE TABLE paper_trading.engine_state CASCADE;
    DELETE FROM paper_trading.events;
    DELETE FROM paper_trading.account_balance;

    -- Reinitialize account balance
    INSERT INTO paper_trading.account_balance (id, cash, portfolio_value, total_pnl)
    VALUES (1, 100000.00, 100000.00, 0)
    ON CONFLICT (id) DO NOTHING;

    RAISE NOTICE 'Paper trading data cleared and reset';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION clear_paper_data IS
'Clear all paper trading data (useful for replay testing or fresh start)';

-- Function to compare modes
CREATE OR REPLACE FUNCTION compare_trading_modes()
RETURNS TABLE (
    mode TEXT,
    cash NUMERIC,
    portfolio_value NUMERIC,
    total_pnl NUMERIC,
    total_trades INTEGER,
    open_positions INTEGER,
    win_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        'real'::TEXT,
        b.cash,
        b.portfolio_value,
        b.total_pnl,
        b.total_trades,
        (SELECT COUNT(*)::INTEGER FROM real_trading.positions WHERE status = 'open'),
        b.win_rate
    FROM real_trading.account_balance b
    WHERE b.id = 1

    UNION ALL

    SELECT
        'paper'::TEXT,
        b.cash,
        b.portfolio_value,
        b.total_pnl,
        b.total_trades,
        (SELECT COUNT(*)::INTEGER FROM paper_trading.positions WHERE status = 'open'),
        b.win_rate
    FROM paper_trading.account_balance b
    WHERE b.id = 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION compare_trading_modes IS
'Compare performance between real and paper trading modes';

-- ============================================================================
-- STEP 7: Migration from Current live_* Tables (Optional)
-- ============================================================================
-- If you want to migrate existing data from public.live_* to paper_trading schema
-- Uncomment and run this section

/*
DO $$
BEGIN
    -- Migrate positions
    INSERT INTO paper_trading.positions
    SELECT * FROM public.live_positions
    ON CONFLICT (position_id) DO NOTHING;

    -- Migrate orders (if position_id exists in paper_trading.positions)
    INSERT INTO paper_trading.orders
    SELECT o.* FROM public.live_orders o
    WHERE o.position_id IS NULL
       OR EXISTS (SELECT 1 FROM paper_trading.positions p WHERE p.position_id = o.position_id)
    ON CONFLICT (order_id) DO NOTHING;

    -- Migrate strategy state
    INSERT INTO paper_trading.strategy_state (strategy_name, state, last_reset, updated_at)
    SELECT strategy_name, state, last_reset, updated_at
    FROM public.live_strategy_state
    ON CONFLICT (strategy_name) DO NOTHING;

    -- Migrate engine state (last 100 records)
    INSERT INTO paper_trading.engine_state (timestamp, state, metadata)
    SELECT timestamp, state, metadata
    FROM public.live_engine_state
    ORDER BY timestamp DESC
    LIMIT 100
    ON CONFLICT DO NOTHING;

    -- Migrate events (last 1000 records)
    INSERT INTO paper_trading.events (timestamp, event_type, strategy_name, position_id, order_id, severity, message, details)
    SELECT timestamp, event_type, strategy_name, position_id, order_id, severity, message, details
    FROM public.live_events
    ORDER BY timestamp DESC
    LIMIT 1000
    ON CONFLICT DO NOTHING;

    RAISE NOTICE 'Migration from public.live_* to paper_trading.* completed';
END $$;
*/

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================================';
    RAISE NOTICE 'Migration 010: Trading Mode Schemas - COMPLETED';
    RAISE NOTICE '============================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Created Schemas:';
    RAISE NOTICE '  ✓ real_trading    - Real money trading (persistent)';
    RAISE NOTICE '  ✓ paper_trading   - Paper trading (persistent, also for replay testing)';
    RAISE NOTICE '';
    RAISE NOTICE 'Tables in Each Schema:';
    RAISE NOTICE '  ✓ positions       - Open and closed positions';
    RAISE NOTICE '  ✓ orders          - Order tracking';
    RAISE NOTICE '  ✓ strategy_state  - Strategy state and metrics';
    RAISE NOTICE '  ✓ engine_state    - Engine state log';
    RAISE NOTICE '  ✓ events          - Audit log (hypertable)';
    RAISE NOTICE '  ✓ account_balance - Account balance and P&L (NEW)';
    RAISE NOTICE '';
    RAISE NOTICE 'Helper Functions:';
    RAISE NOTICE '  ✓ get_account_balance(mode)';
    RAISE NOTICE '  ✓ update_account_balance(mode, cash, portfolio_value)';
    RAISE NOTICE '  ✓ get_open_positions_count(mode)';
    RAISE NOTICE '  ✓ clear_replay_data()';
    RAISE NOTICE '  ✓ compare_trading_modes()';
    RAISE NOTICE '';
    RAISE NOTICE 'Backward Compatibility:';
    RAISE NOTICE '  ✓ All existing live_* tables in public schema remain unchanged';
    RAISE NOTICE '  ✓ Existing code will continue to work without modifications';
    RAISE NOTICE '  ✓ New fields have default values for zero-impact migration';
    RAISE NOTICE '';
    RAISE NOTICE 'Next Steps:';
    RAISE NOTICE '  1. Update StateStore to accept trading_mode parameter';
    RAISE NOTICE '  2. Update LiveTradingEngine to determine mode from config';
    RAISE NOTICE '  3. Test each mode independently';
    RAISE NOTICE '  4. Optionally migrate existing data (see commented section)';
    RAISE NOTICE '';
    RAISE NOTICE 'Quick Test:';
    RAISE NOTICE '  SELECT * FROM compare_trading_modes();';
    RAISE NOTICE '';
    RAISE NOTICE '============================================================================';
END $$;
