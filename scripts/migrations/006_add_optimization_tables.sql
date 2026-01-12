-- ============================================================================
-- Optimization Tables
-- ============================================================================
-- This migration adds tables to persist optimization results in PostgreSQL
--
-- Usage:
--   PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data < scripts/migrations/006_add_optimization_tables.sql
-- ============================================================================

-- ============================================================================
-- OPTIMIZATION_RUNS TABLE
-- ============================================================================
-- Stores metadata about each optimization execution
-- ============================================================================

CREATE TABLE IF NOT EXISTS optimization_runs (
    optimization_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,

    -- Optimization configuration
    optimization_type TEXT NOT NULL, -- 'grid_search', 'walk_forward'
    train_start_date TIMESTAMPTZ NOT NULL,
    train_end_date TIMESTAMPTZ NOT NULL,
    test_start_date TIMESTAMPTZ,
    test_end_date TIMESTAMPTZ,
    initial_capital NUMERIC(15, 2) NOT NULL DEFAULT 100000.00,

    -- Parameter configuration
    param_grid JSONB NOT NULL, -- {spread_width: [10, 15, 20], profit_target: [0.3, 0.5]}
    fixed_params JSONB, -- {min_dte: 0, max_dte: 45, max_trades_daily: 5}
    total_combinations INTEGER NOT NULL,

    -- Data configuration
    underlying_ticker TEXT NOT NULL DEFAULT 'SPX',
    timeframe TEXT NOT NULL DEFAULT '5min', -- '1min', '5min', '15min', '1hour', 'daily'
    data_cache_key TEXT, -- Redis cache key used for data

    -- Execution metadata
    status TEXT NOT NULL, -- 'pending', 'running', 'completed', 'failed', 'cancelled'
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER,
    estimated_completion_time TIMESTAMPTZ,

    -- Best result summary
    best_params JSONB, -- Parameters of best-performing combination
    best_sharpe_ratio NUMERIC(10, 4),
    best_total_return NUMERIC(15, 2),
    best_win_rate NUMERIC(10, 4),

    -- Walk-forward specific
    walk_forward_results JSONB, -- Array of {train_period, test_period, best_params, metrics}

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- OPTIMIZATION_RESULTS TABLE
-- ============================================================================
-- Stores results for each parameter combination tested
-- ============================================================================

CREATE TABLE IF NOT EXISTS optimization_results (
    result_id SERIAL PRIMARY KEY,
    optimization_id TEXT NOT NULL REFERENCES optimization_runs(optimization_id) ON DELETE CASCADE,

    -- Parameter combination
    params JSONB NOT NULL, -- Full parameter set for this combination
    param_hash TEXT NOT NULL, -- Hash of params for deduplication

    -- Performance metrics
    sharpe_ratio NUMERIC(10, 4),
    total_return NUMERIC(15, 2),
    total_return_pct NUMERIC(10, 4),
    num_trades INTEGER,
    num_winning_trades INTEGER,
    num_losing_trades INTEGER,
    win_rate NUMERIC(10, 4),
    avg_win NUMERIC(15, 2),
    avg_loss NUMERIC(15, 2),
    profit_factor NUMERIC(10, 4),
    max_drawdown NUMERIC(10, 4),
    final_capital NUMERIC(15, 2),

    -- Execution details
    execution_time_seconds NUMERIC(10, 2),
    backtest_id TEXT, -- Reference to backtest_runs if saved

    -- Walk-forward specific
    is_train_result BOOLEAN DEFAULT TRUE, -- FALSE for test period results
    period_index INTEGER, -- For walk-forward: which fold/period this is

    -- Ranking (computed after all combinations run)
    rank_by_sharpe INTEGER,
    rank_by_return INTEGER,
    rank_by_win_rate INTEGER,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure unique parameter combinations per optimization
    UNIQUE (optimization_id, param_hash)
);

-- ============================================================================
-- OPTIMIZATION_CACHE_STATUS TABLE
-- ============================================================================
-- Tracks data cache usage and statistics
-- ============================================================================

CREATE TABLE IF NOT EXISTS optimization_cache_status (
    cache_key TEXT PRIMARY KEY,

    -- Cache configuration
    underlying_ticker TEXT NOT NULL,
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    min_dte INTEGER,
    max_dte INTEGER,
    timeframe TEXT NOT NULL,

    -- Cache statistics
    num_options_rows INTEGER,
    num_underlying_rows INTEGER,
    data_size_mb NUMERIC(10, 2),
    hit_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),

    -- TTL management
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,

    -- Metadata
    redis_stored BOOLEAN DEFAULT FALSE,
    memory_stored BOOLEAN DEFAULT FALSE
);

-- ============================================================================
-- INDEXES FOR FAST QUERIES
-- ============================================================================

-- Optimization runs indexes
CREATE INDEX IF NOT EXISTS idx_optimization_runs_created_at
    ON optimization_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_optimization_runs_strategy
    ON optimization_runs (strategy_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_optimization_runs_status
    ON optimization_runs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_optimization_runs_started
    ON optimization_runs (started_at DESC) WHERE started_at IS NOT NULL;

-- Optimization results indexes
CREATE INDEX IF NOT EXISTS idx_optimization_results_optimization_id
    ON optimization_results (optimization_id, sharpe_ratio DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_optimization_results_param_hash
    ON optimization_results (param_hash);

CREATE INDEX IF NOT EXISTS idx_optimization_results_sharpe
    ON optimization_results (optimization_id, sharpe_ratio DESC NULLS LAST)
    WHERE sharpe_ratio IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_optimization_results_return
    ON optimization_results (optimization_id, total_return DESC NULLS LAST)
    WHERE total_return IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_optimization_results_backtest
    ON optimization_results (backtest_id) WHERE backtest_id IS NOT NULL;

-- GIN index for fast JSONB queries on parameters
CREATE INDEX IF NOT EXISTS idx_optimization_results_params
    ON optimization_results USING gin (params);

-- Cache status indexes
CREATE INDEX IF NOT EXISTS idx_optimization_cache_ticker_dates
    ON optimization_cache_status (underlying_ticker, start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_optimization_cache_last_accessed
    ON optimization_cache_status (last_accessed_at DESC);

CREATE INDEX IF NOT EXISTS idx_optimization_cache_expires
    ON optimization_cache_status (expires_at) WHERE expires_at IS NOT NULL;

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to get top N results for an optimization
CREATE OR REPLACE FUNCTION get_top_optimization_results(
    opt_id TEXT,
    limit_count INTEGER DEFAULT 10,
    sort_by TEXT DEFAULT 'sharpe_ratio' -- 'sharpe_ratio', 'total_return', 'win_rate'
)
RETURNS TABLE (
    params JSONB,
    sharpe_ratio NUMERIC,
    total_return NUMERIC,
    win_rate NUMERIC,
    num_trades INTEGER,
    max_drawdown NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    EXECUTE format('
        SELECT
            r.params,
            r.sharpe_ratio,
            r.total_return,
            r.win_rate,
            r.num_trades,
            r.max_drawdown
        FROM optimization_results r
        WHERE r.optimization_id = $1
          AND r.%I IS NOT NULL
        ORDER BY r.%I DESC NULLS LAST
        LIMIT $2
    ', sort_by, sort_by)
    USING opt_id, limit_count;
END;
$$ LANGUAGE plpgsql;

-- Function to update optimization progress
CREATE OR REPLACE FUNCTION update_optimization_progress(
    opt_id TEXT,
    current_progress INTEGER,
    eta TIMESTAMPTZ DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    UPDATE optimization_runs
    SET
        progress_current = current_progress,
        estimated_completion_time = COALESCE(eta, estimated_completion_time),
        updated_at = NOW()
    WHERE optimization_id = opt_id;
END;
$$ LANGUAGE plpgsql;

-- Function to mark optimization as completed
CREATE OR REPLACE FUNCTION complete_optimization(
    opt_id TEXT,
    best_params_json JSONB,
    best_sharpe NUMERIC DEFAULT NULL,
    best_return NUMERIC DEFAULT NULL,
    best_wr NUMERIC DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    UPDATE optimization_runs
    SET
        status = 'completed',
        completed_at = NOW(),
        best_params = best_params_json,
        best_sharpe_ratio = best_sharpe,
        best_total_return = best_return,
        best_win_rate = best_wr,
        updated_at = NOW()
    WHERE optimization_id = opt_id;
END;
$$ LANGUAGE plpgsql;

-- Function to compute rankings for optimization results
CREATE OR REPLACE FUNCTION compute_optimization_rankings(opt_id TEXT)
RETURNS VOID AS $$
BEGIN
    -- Rank by Sharpe ratio
    WITH sharpe_ranks AS (
        SELECT
            result_id,
            ROW_NUMBER() OVER (ORDER BY sharpe_ratio DESC NULLS LAST) AS rank
        FROM optimization_results
        WHERE optimization_id = opt_id
          AND sharpe_ratio IS NOT NULL
    )
    UPDATE optimization_results r
    SET rank_by_sharpe = sr.rank
    FROM sharpe_ranks sr
    WHERE r.result_id = sr.result_id;

    -- Rank by total return
    WITH return_ranks AS (
        SELECT
            result_id,
            ROW_NUMBER() OVER (ORDER BY total_return DESC NULLS LAST) AS rank
        FROM optimization_results
        WHERE optimization_id = opt_id
          AND total_return IS NOT NULL
    )
    UPDATE optimization_results r
    SET rank_by_return = rr.rank
    FROM return_ranks rr
    WHERE r.result_id = rr.result_id;

    -- Rank by win rate
    WITH wr_ranks AS (
        SELECT
            result_id,
            ROW_NUMBER() OVER (ORDER BY win_rate DESC NULLS LAST) AS rank
        FROM optimization_results
        WHERE optimization_id = opt_id
          AND win_rate IS NOT NULL
    )
    UPDATE optimization_results r
    SET rank_by_win_rate = wr.rank
    FROM wr_ranks wr
    WHERE r.result_id = wr.result_id;
END;
$$ LANGUAGE plpgsql;

-- Function to clean expired cache entries
CREATE OR REPLACE FUNCTION clean_expired_cache_entries()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM optimization_cache_status
    WHERE expires_at IS NOT NULL
      AND expires_at < NOW();

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at timestamp on optimization_runs
CREATE OR REPLACE FUNCTION update_optimization_runs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_optimization_runs_updated_at
    BEFORE UPDATE ON optimization_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_optimization_runs_updated_at();

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
    RAISE NOTICE 'Optimization tables created successfully!';
    RAISE NOTICE '============================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - optimization_runs (metadata and summary)';
    RAISE NOTICE '  - optimization_results (individual combination results)';
    RAISE NOTICE '  - optimization_cache_status (data cache tracking)';
    RAISE NOTICE '';
    RAISE NOTICE 'Helper Functions:';
    RAISE NOTICE '  - get_top_optimization_results(opt_id, limit, sort_by)';
    RAISE NOTICE '  - update_optimization_progress(opt_id, current, eta)';
    RAISE NOTICE '  - complete_optimization(opt_id, best_params, metrics)';
    RAISE NOTICE '  - compute_optimization_rankings(opt_id)';
    RAISE NOTICE '  - clean_expired_cache_entries()';
    RAISE NOTICE '';
    RAISE NOTICE '============================================================================';
END $$;
