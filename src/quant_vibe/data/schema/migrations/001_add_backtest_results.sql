-- ============================================================================
-- Backtest Results Tables
-- ============================================================================
-- This migration adds tables to persist backtest results in PostgreSQL
--
-- Usage:
--   docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/001_add_backtest_results.sql
-- ============================================================================

-- ============================================================================
-- BACKTEST_RUNS TABLE
-- ============================================================================
-- Stores metadata about each backtest execution
-- ============================================================================

CREATE TABLE IF NOT EXISTS backtest_runs (
    backtest_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    ticker TEXT NOT NULL,

    -- Backtest configuration
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    initial_capital NUMERIC(15, 2) NOT NULL,
    max_positions INTEGER DEFAULT 1,

    -- Strategy parameters (JSON format)
    parameters JSONB,

    -- Execution metadata
    status TEXT NOT NULL, -- 'pending', 'running', 'completed', 'failed'
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,

    -- Summary metrics
    final_capital NUMERIC(15, 2),
    total_return NUMERIC(10, 4),
    total_return_pct NUMERIC(10, 4),
    num_trades INTEGER,
    num_winning_trades INTEGER,
    num_losing_trades INTEGER,
    win_rate NUMERIC(10, 4),
    avg_win NUMERIC(15, 2),
    avg_loss NUMERIC(15, 2),
    profit_factor NUMERIC(10, 4),
    max_drawdown NUMERIC(10, 4),
    sharpe_ratio NUMERIC(10, 4),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT
);

-- ============================================================================
-- BACKTEST_TRADES TABLE
-- ============================================================================
-- Stores individual trade records from backtests
-- ============================================================================

CREATE TABLE IF NOT EXISTS backtest_trades (
    trade_id SERIAL PRIMARY KEY,
    backtest_id TEXT NOT NULL REFERENCES backtest_runs(backtest_id) ON DELETE CASCADE,

    -- Position identification
    position_id TEXT NOT NULL,
    spread_type TEXT NOT NULL, -- 'vertical_call', 'vertical_put', 'iron_condor', etc.

    -- Timing
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ NOT NULL,
    duration_minutes NUMERIC(10, 2),

    -- Trade economics
    entry_cost NUMERIC(15, 2) NOT NULL,
    exit_value NUMERIC(15, 2) NOT NULL,
    pnl NUMERIC(15, 2) NOT NULL,
    pnl_percent NUMERIC(10, 4),

    -- Entry/Exit context
    entry_trigger TEXT,
    exit_reason TEXT,
    underlying_entry NUMERIC(12, 4),
    underlying_exit NUMERIC(12, 4),

    -- Position tracking
    max_profit NUMERIC(15, 2),
    peak_value NUMERIC(15, 2),

    -- Legs (stored as JSONB array)
    legs JSONB NOT NULL,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- BACKTEST_EQUITY_CURVE TABLE
-- ============================================================================
-- Stores equity curve snapshots (portfolio value over time)
-- ============================================================================

CREATE TABLE IF NOT EXISTS backtest_equity_curve (
    backtest_id TEXT NOT NULL REFERENCES backtest_runs(backtest_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,

    -- Snapshot data
    cash NUMERIC(15, 2) NOT NULL,
    portfolio_value NUMERIC(15, 2) NOT NULL,
    active_position BOOLEAN DEFAULT FALSE,

    -- Computed metrics
    returns NUMERIC(10, 6),
    cummax NUMERIC(15, 2),
    drawdown NUMERIC(10, 4),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Composite primary key including timestamp for hypertable
    PRIMARY KEY (timestamp, backtest_id)
);

-- ============================================================================
-- INDEXES FOR FAST QUERIES
-- ============================================================================

-- Backtest runs indexes
CREATE INDEX IF NOT EXISTS idx_backtest_runs_created_at ON backtest_runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy ON backtest_runs (strategy_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_status ON backtest_runs (status, created_at DESC);

-- Backtest trades indexes
CREATE INDEX IF NOT EXISTS idx_backtest_trades_backtest_id ON backtest_trades (backtest_id, entry_time);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_position_id ON backtest_trades (position_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_entry_time ON backtest_trades (entry_time DESC);

-- Backtest equity curve indexes
CREATE INDEX IF NOT EXISTS idx_backtest_equity_backtest_id ON backtest_equity_curve (backtest_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_backtest_equity_timestamp ON backtest_equity_curve (timestamp DESC);

-- Convert equity curve to hypertable for efficient time-series queries
-- Only if not already a hypertable
SELECT create_hypertable('backtest_equity_curve', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to get latest backtest for a strategy
CREATE OR REPLACE FUNCTION get_latest_backtest(strategy TEXT)
RETURNS TABLE (
    backtest_id TEXT,
    started_at TIMESTAMPTZ,
    status TEXT,
    total_return NUMERIC,
    win_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        br.backtest_id,
        br.started_at,
        br.status,
        br.total_return,
        br.win_rate
    FROM backtest_runs br
    WHERE br.strategy_name = strategy
    ORDER BY br.created_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to get backtest summary statistics
CREATE OR REPLACE FUNCTION get_backtest_summary(bid TEXT)
RETURNS TABLE (
    num_trades INTEGER,
    win_rate NUMERIC,
    profit_factor NUMERIC,
    max_drawdown NUMERIC,
    sharpe_ratio NUMERIC,
    avg_duration_minutes NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        br.num_trades,
        br.win_rate,
        br.profit_factor,
        br.max_drawdown,
        br.sharpe_ratio,
        AVG(bt.duration_minutes) AS avg_duration_minutes
    FROM backtest_runs br
    LEFT JOIN backtest_trades bt ON br.backtest_id = bt.backtest_id
    WHERE br.backtest_id = bid
    GROUP BY br.backtest_id, br.num_trades, br.win_rate, br.profit_factor, br.max_drawdown, br.sharpe_ratio;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================

GRANT ALL ON ALL TABLES IN SCHEMA public TO quantvibe;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO quantvibe;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO quantvibe;

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================================';
    RAISE NOTICE 'Backtest results tables created successfully!';
    RAISE NOTICE '============================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - backtest_runs (metadata and summary metrics)';
    RAISE NOTICE '  - backtest_trades (individual trade records)';
    RAISE NOTICE '  - backtest_equity_curve (hypertable, portfolio value over time)';
    RAISE NOTICE '';
    RAISE NOTICE 'Helper Functions:';
    RAISE NOTICE '  - get_latest_backtest(strategy)';
    RAISE NOTICE '  - get_backtest_summary(backtest_id)';
    RAISE NOTICE '';
    RAISE NOTICE '============================================================================';
END $$;
