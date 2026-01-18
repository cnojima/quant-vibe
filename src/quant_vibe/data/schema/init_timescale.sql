-- ============================================================================
-- TimescaleDB Initialization Script for Quant-Vibe
-- ============================================================================
-- This script initializes the TimescaleDB database for options trading data
-- It creates hypertables, indexes, continuous aggregates, and helper functions
--
-- Usage:
--   docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < src/quant_vibe/data/schema/init_timescale.sql
--
-- Or automatically executed via docker-compose on first run:
--   Volume mount: ./src/quant_vibe/data/schema/init_timescale.sql:/docker-entrypoint-initdb.d/init.sql
-- ============================================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- OPTIONS BARS TABLE (1-minute resolution)
-- ============================================================================
-- Stores options OHLCV data, quotes, Greeks, and contract details
-- Data sources: Massive API (historical), Schwab API (real-time)
-- ============================================================================

CREATE TABLE IF NOT EXISTS options_bars (
    timestamp TIMESTAMPTZ NOT NULL,
    option_ticker TEXT NOT NULL,
    underlying_ticker TEXT NOT NULL,

    -- OHLCV data from Massive or Schwab
    open NUMERIC(12, 4),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    close NUMERIC(12, 4),
    volume BIGINT,
    vwap NUMERIC(12, 4),
    transactions INTEGER,

    -- Quote data from Schwab (bid/ask spreads)
    bid NUMERIC(12, 4),
    ask NUMERIC(12, 4),
    bid_size INTEGER,
    ask_size INTEGER,

    -- Contract details (denormalized for query performance)
    strike_price NUMERIC(12, 4),
    contract_type TEXT, -- 'call' or 'put'
    expiration_date DATE,
    expired BOOLEAN DEFAULT false,

    -- Greeks (if available)
    -- NOTE: Using NUMERIC(10,6) instead of NUMERIC(8,6) to support IV > 100%
    -- This allows values up to 9999.999999 (sufficient for IV expressed as percentage)
    implied_volatility NUMERIC(10, 6),
    delta NUMERIC(10, 6),
    gamma NUMERIC(10, 6),
    theta NUMERIC(10, 6),
    vega NUMERIC(10, 6),
    rho NUMERIC(10, 6),

    -- Metadata
    data_source TEXT, -- 'massive', 'schwab_realtime', 'schwab_poll', 'combined'
    created_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (timestamp, option_ticker)
);

-- Convert to hypertable (partitioned by time)
-- Chunk interval: 1 day (optimal for intraday options data)
SELECT create_hypertable('options_bars', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Enable compression to save storage
-- Compress by option ticker and underlying ticker for better compression ratio
ALTER TABLE options_bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'option_ticker, underlying_ticker',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add compression policy (compress data older than 7 days)
SELECT add_compression_policy('options_bars', INTERVAL '7 days', if_not_exists => TRUE);

-- ============================================================================
-- INDEXES FOR FAST QUERIES (OPTIONS)
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_options_bars_expired
ON options_bars(expired)
WHERE expired = true;

COMMENT ON COLUMN options_bars.expired IS
'Flag indicating if contract has expired (true) or is still valid (false). Replaces -9.0 sentinel value.';

-- Index for querying by option ticker and time range
CREATE INDEX IF NOT EXISTS idx_options_bars_ticker_time
    ON options_bars (option_ticker, timestamp DESC);

-- Index for querying by underlying ticker (for entire chain queries)
CREATE INDEX IF NOT EXISTS idx_options_bars_underlying_time
    ON options_bars (underlying_ticker, timestamp DESC);

-- Index for querying by expiration date (for DTE-based queries)
CREATE INDEX IF NOT EXISTS idx_options_bars_expiration
    ON options_bars (expiration_date, timestamp DESC);

-- Index for querying by contract type (calls vs puts)
CREATE INDEX IF NOT EXISTS idx_options_bars_type
    ON options_bars (underlying_ticker, contract_type, timestamp DESC);

-- Composite index for strike price queries (option chain queries)
CREATE INDEX IF NOT EXISTS idx_options_bars_strike
    ON options_bars (underlying_ticker, expiration_date, strike_price, timestamp DESC);

-- ============================================================================
-- CONTINUOUS AGGREGATES FOR OPTIONS (Pre-computed higher timeframes)
-- ============================================================================
-- These materialized views automatically aggregate 1-minute data into
-- 5-minute, 15-minute, 1-hour, and daily bars for faster queries
-- ============================================================================

-- 5-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS options_bars_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', timestamp) AS bucket,
    option_ticker,
    underlying_ticker,
    strike_price,
    contract_type,
    expiration_date,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(vwap) AS vwap,
    SUM(transactions) AS transactions,
    LAST(bid, timestamp) AS bid,
    LAST(ask, timestamp) AS ask,
    LAST(bid_size, timestamp) AS bid_size,
    LAST(ask_size, timestamp) AS ask_size,
    AVG(implied_volatility) AS implied_volatility,
    LAST(delta, timestamp) AS delta,
    LAST(gamma, timestamp) AS gamma,
    LAST(theta, timestamp) AS theta,
    LAST(vega, timestamp) AS vega,
    LAST(rho, timestamp) AS rho,
    MAX(expired) AS expired
FROM options_bars
GROUP BY bucket, option_ticker, underlying_ticker, strike_price, contract_type, expiration_date;

-- Refresh policy for 5-minute aggregates
SELECT add_continuous_aggregate_policy('options_bars_5min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

-- 15-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS options_bars_15min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', timestamp) AS bucket,
    option_ticker,
    underlying_ticker,
    strike_price,
    contract_type,
    expiration_date,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(vwap) AS vwap,
    SUM(transactions) AS transactions,
    LAST(bid, timestamp) AS bid,
    LAST(ask, timestamp) AS ask,
    LAST(bid_size, timestamp) AS bid_size,
    LAST(ask_size, timestamp) AS ask_size,
    AVG(implied_volatility) AS implied_volatility,
    LAST(delta, timestamp) AS delta,
    LAST(gamma, timestamp) AS gamma,
    LAST(theta, timestamp) AS theta,
    LAST(vega, timestamp) AS vega,
    LAST(rho, timestamp) AS rho,
    MAX(expired) AS expired
FROM options_bars
GROUP BY bucket, option_ticker, underlying_ticker, strike_price, contract_type, expiration_date;

SELECT add_continuous_aggregate_policy('options_bars_15min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

-- 1-hour bars
CREATE MATERIALIZED VIEW IF NOT EXISTS options_bars_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    option_ticker,
    underlying_ticker,
    strike_price,
    contract_type,
    expiration_date,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(vwap) AS vwap,
    SUM(transactions) AS transactions,
    LAST(bid, timestamp) AS bid,
    LAST(ask, timestamp) AS ask,
    LAST(bid_size, timestamp) AS bid_size,
    LAST(ask_size, timestamp) AS ask_size,
    AVG(implied_volatility) AS implied_volatility,
    LAST(delta, timestamp) AS delta,
    LAST(gamma, timestamp) AS gamma,
    LAST(theta, timestamp) AS theta,
    LAST(vega, timestamp) AS vega,
    LAST(rho, timestamp) AS rho,
    MAX(expired) AS expired
FROM options_bars
GROUP BY bucket, option_ticker, underlying_ticker, strike_price, contract_type, expiration_date;

SELECT add_continuous_aggregate_policy('options_bars_1hour',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Daily bars
CREATE MATERIALIZED VIEW IF NOT EXISTS options_bars_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS bucket,
    option_ticker,
    underlying_ticker,
    strike_price,
    contract_type,
    expiration_date,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(vwap) AS vwap,
    SUM(transactions) AS transactions,
    LAST(bid, timestamp) AS bid,
    LAST(ask, timestamp) AS ask,
    LAST(bid_size, timestamp) AS bid_size,
    LAST(ask_size, timestamp) AS ask_size,
    AVG(implied_volatility) AS implied_volatility,
    LAST(delta, timestamp) AS delta,
    LAST(gamma, timestamp) AS gamma,
    LAST(theta, timestamp) AS theta,
    LAST(vega, timestamp) AS vega,
    LAST(rho, timestamp) AS rho,
    MAX(expired) AS expired
FROM options_bars
GROUP BY bucket, option_ticker, underlying_ticker, strike_price, contract_type, expiration_date;

SELECT add_continuous_aggregate_policy('options_bars_daily',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create indexes on continuous aggregates for faster queries
CREATE INDEX IF NOT EXISTS idx_options_bars_5min_ticker
    ON options_bars_5min (option_ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_options_bars_15min_ticker
    ON options_bars_15min (option_ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_options_bars_1hour_ticker
    ON options_bars_1hour (option_ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_options_bars_daily_ticker
    ON options_bars_daily (option_ticker, bucket DESC);

-- ============================================================================
-- UNDERLYING BARS TABLE (1-minute resolution)
-- ============================================================================
-- Stores underlying asset price data (SPX, SPY, etc.)
-- Used for accurate intrinsic value calculations and strategy signals
-- ============================================================================

CREATE TABLE IF NOT EXISTS underlying_bars (
    timestamp TIMESTAMPTZ NOT NULL,
    ticker TEXT NOT NULL,  -- 'SPX', 'SPY', 'QQQ', etc.

    -- OHLCV data
    open NUMERIC(12, 4),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    close NUMERIC(12, 4),
    volume BIGINT,
    vwap NUMERIC(12, 4),
    transactions INTEGER,

    -- Metadata
    data_source TEXT, -- 'massive', 'schwab', 'polygon', 'yahoo', etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (timestamp, ticker)
);

-- Convert to hypertable (partitioned by time)
-- Chunk interval: 7 days (less frequent than options data)
SELECT create_hypertable('underlying_bars', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Enable compression
ALTER TABLE underlying_bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ticker',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add compression policy (compress data older than 7 days)
SELECT add_compression_policy('underlying_bars', INTERVAL '7 days', if_not_exists => TRUE);

-- ============================================================================
-- INDEXES FOR FAST QUERIES (UNDERLYING)
-- ============================================================================

-- Index for querying by ticker and time range
CREATE INDEX IF NOT EXISTS idx_underlying_bars_ticker_time
    ON underlying_bars (ticker, timestamp DESC);

-- Index for querying recent data
CREATE INDEX IF NOT EXISTS idx_underlying_bars_recent
    ON underlying_bars (timestamp DESC);

-- ============================================================================
-- CONTINUOUS AGGREGATES FOR UNDERLYING (Pre-computed higher timeframes)
-- ============================================================================

-- 5-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS underlying_bars_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', timestamp) AS bucket,
    ticker,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(vwap) AS vwap,
    SUM(transactions) AS transactions,
    LAST(data_source, timestamp) AS data_source
FROM underlying_bars
GROUP BY bucket, ticker;

SELECT add_continuous_aggregate_policy('underlying_bars_5min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

-- 15-minute bars
CREATE MATERIALIZED VIEW IF NOT EXISTS underlying_bars_15min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', timestamp) AS bucket,
    ticker,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(vwap) AS vwap,
    SUM(transactions) AS transactions,
    LAST(data_source, timestamp) AS data_source
FROM underlying_bars
GROUP BY bucket, ticker;

SELECT add_continuous_aggregate_policy('underlying_bars_15min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

-- 1-hour bars
CREATE MATERIALIZED VIEW IF NOT EXISTS underlying_bars_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    ticker,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(vwap) AS vwap,
    SUM(transactions) AS transactions,
    LAST(data_source, timestamp) AS data_source
FROM underlying_bars
GROUP BY bucket, ticker;

SELECT add_continuous_aggregate_policy('underlying_bars_1hour',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Daily bars
CREATE MATERIALIZED VIEW IF NOT EXISTS underlying_bars_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS bucket,
    ticker,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(vwap) AS vwap,
    SUM(transactions) AS transactions,
    LAST(data_source, timestamp) AS data_source
FROM underlying_bars
GROUP BY bucket, ticker;

SELECT add_continuous_aggregate_policy('underlying_bars_daily',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create indexes on continuous aggregates
CREATE INDEX IF NOT EXISTS idx_underlying_bars_5min_ticker
    ON underlying_bars_5min (ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_underlying_bars_15min_ticker
    ON underlying_bars_15min (ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_underlying_bars_1hour_ticker
    ON underlying_bars_1hour (ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_underlying_bars_daily_ticker
    ON underlying_bars_daily (ticker, bucket DESC);

-- ============================================================================
-- BACKTEST RESULTS TABLES
-- ============================================================================
-- Stores backtest execution results, trades, and equity curves
-- ============================================================================

-- ============================================================================
-- BACKTEST_RUNS TABLE
-- ============================================================================
-- Stores metadata about each backtest execution
-- ============================================================================

CREATE TABLE IF NOT EXISTS backtest_runs (
    backtest_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,

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
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate NUMERIC(10, 4),
    avg_win NUMERIC(15, 2),
    avg_loss NUMERIC(15, 2),
    profit_factor NUMERIC(10, 4),
    max_drawdown NUMERIC(10, 4),
    sharpe_ratio NUMERIC(10, 4),

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
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

-- Convert equity curve to hypertable for efficient time-series queries
SELECT create_hypertable('backtest_equity_curve', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Enable compression on backtest_equity_curve hypertable
ALTER TABLE backtest_equity_curve SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'backtest_id',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add automatic compression policy (compress data older than 7 days)
SELECT add_compression_policy('backtest_equity_curve', INTERVAL '7 days', if_not_exists => TRUE);

-- ============================================================================
-- INDEXES FOR BACKTEST TABLES
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
    total_trades INTEGER,
    win_rate NUMERIC,
    profit_factor NUMERIC,
    max_drawdown NUMERIC,
    sharpe_ratio NUMERIC,
    avg_duration_minutes NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        br.total_trades,
        br.win_rate,
        br.profit_factor,
        br.max_drawdown,
        br.sharpe_ratio,
        AVG(bt.duration_minutes) AS avg_duration_minutes
    FROM backtest_runs br
    LEFT JOIN backtest_trades bt ON br.backtest_id = bt.backtest_id
    WHERE br.backtest_id = bid
    GROUP BY br.backtest_id, br.total_trades, br.win_rate, br.profit_factor, br.max_drawdown, br.sharpe_ratio;
END;
$$ LANGUAGE plpgsql;

-- Function to get latest data for an option
CREATE OR REPLACE FUNCTION get_latest_option_data(ticker TEXT)
RETURNS TABLE (
    timestamp TIMESTAMPTZ,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT,
    bid NUMERIC,
    ask NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        o.timestamp,
        o.open,
        o.high,
        o.low,
        o.close,
        o.volume,
        o.bid,
        o.ask
    FROM options_bars o
    WHERE o.option_ticker = ticker
    ORDER BY o.timestamp DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Function to get latest price for a ticker
CREATE OR REPLACE FUNCTION get_latest_underlying_price(symbol TEXT)
RETURNS TABLE (
    timestamp TIMESTAMPTZ,
    close NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.timestamp,
        u.close
    FROM underlying_bars u
    WHERE u.ticker = symbol
    ORDER BY u.timestamp DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- RETENTION POLICY (Optional - currently disabled)
-- ============================================================================
-- Uncomment to auto-delete old data after a specified period
-- Keep raw 1-minute data for 90 days, then delete:
-- SELECT add_retention_policy('options_bars', INTERVAL '90 days', if_not_exists => TRUE);
-- SELECT add_retention_policy('underlying_bars', INTERVAL '90 days', if_not_exists => TRUE);

-- ============================================================================
-- LIVE TRADING TABLES
-- ============================================================================
-- Stores state and audit logs for live trading engine
-- ============================================================================

-- Live engine state
CREATE TABLE IF NOT EXISTS live_engine_state (
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    id SERIAL PRIMARY KEY,
    state TEXT NOT NULL,
    metadata JSONB,
    UNIQUE(timestamp)
);

-- Active positions
CREATE TABLE IF NOT EXISTS live_positions (
    position_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    spread_type TEXT NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    entry_cost NUMERIC NOT NULL,
    underlying_price_at_entry NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    current_value NUMERIC,
    exit_time TIMESTAMPTZ,
    exit_value NUMERIC,
    exit_reason TEXT,
    legs JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_positions_status
    ON live_positions(status, strategy_name);

-- Orders
CREATE TABLE IF NOT EXISTS live_orders (
    order_id TEXT PRIMARY KEY,
    position_id TEXT REFERENCES live_positions(position_id),
    strategy_name TEXT NOT NULL,
    order_type TEXT NOT NULL,
    action_type TEXT,  -- 'opening' or 'closing'
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    submitted_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filled_time TIMESTAMPTZ,
    expected_price NUMERIC,
    filled_price NUMERIC,
    filled_quantity INTEGER,
    broker_order_id TEXT,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Strategy state (daily resets, etc.)
CREATE TABLE IF NOT EXISTS live_strategy_state (
    strategy_name TEXT PRIMARY KEY,
    state JSONB NOT NULL,
    last_reset TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Events/audit log (hypertable)
-- Note: timestamp must be first column in PRIMARY KEY for TimescaleDB
CREATE TABLE IF NOT EXISTS live_events (
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    id SERIAL,
    event_type TEXT NOT NULL,
    strategy_name TEXT,
    position_id TEXT,
    order_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    details JSONB,
    PRIMARY KEY (timestamp, id)
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('live_events', 'timestamp',
    migrate_data => TRUE,
    if_not_exists => TRUE
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_live_events_strategy
    ON live_events(strategy_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_live_events_position
    ON live_events(position_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_live_events_severity
    ON live_events(severity, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_live_events_type
    ON live_events(event_type, timestamp DESC);

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
    RAISE NOTICE 'TimescaleDB schema initialized successfully!';
    RAISE NOTICE '============================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Market Data Tables:';
    RAISE NOTICE '  - options_bars (hypertable, 1-minute resolution)';
    RAISE NOTICE '  - underlying_bars (hypertable, 1-minute resolution)';
    RAISE NOTICE '';
    RAISE NOTICE 'Backtest Tables:';
    RAISE NOTICE '  - backtest_runs (metadata and summary metrics)';
    RAISE NOTICE '  - backtest_trades (individual trade records)';
    RAISE NOTICE '  - backtest_equity_curve (hypertable, portfolio value over time)';
    RAISE NOTICE '';
    RAISE NOTICE 'Live Trading Tables:';
    RAISE NOTICE '  - live_engine_state (engine state tracking)';
    RAISE NOTICE '  - live_positions (active positions)';
    RAISE NOTICE '  - live_orders (order tracking)';
    RAISE NOTICE '  - live_strategy_state (strategy state)';
    RAISE NOTICE '  - live_events (hypertable, audit log)';
    RAISE NOTICE '';
    RAISE NOTICE 'Continuous Aggregates:';
    RAISE NOTICE '  - 5min, 15min, 1hour, daily (for both options and underlying)';
    RAISE NOTICE '';
    RAISE NOTICE 'Compression:';
    RAISE NOTICE '  - Enabled (7-day policy for all hypertables)';
    RAISE NOTICE '';
    RAISE NOTICE 'Indexes:';
    RAISE NOTICE '  - Ticker, time range, expiration, strike price, contract type';
    RAISE NOTICE '  - Backtest runs, trades, and equity curve indexes';
    RAISE NOTICE '  - Live events by strategy, position, severity, and type';
    RAISE NOTICE '';
    RAISE NOTICE 'Helper Functions:';
    RAISE NOTICE '  - get_latest_option_data(ticker)';
    RAISE NOTICE '  - get_latest_underlying_price(symbol)';
    RAISE NOTICE '  - get_latest_backtest(strategy)';
    RAISE NOTICE '  - get_backtest_summary(backtest_id)';
    RAISE NOTICE '';
    RAISE NOTICE '============================================================================';
END $$;
