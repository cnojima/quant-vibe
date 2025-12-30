-- ============================================================================
-- TimescaleDB Initialization Script for Quant-Vibe
-- ============================================================================
-- This script initializes the TimescaleDB database for options trading data
-- It creates hypertables, indexes, continuous aggregates, and helper functions
--
-- Usage:
--   docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < scripts/init_timescale.sql
--
-- Or automatically executed via docker-compose on first run:
--   Volume mount: ./scripts/init_timescale.sql:/docker-entrypoint-initdb.d/init.sql
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
    LAST(rho, timestamp) AS rho
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
    LAST(rho, timestamp) AS rho
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
    LAST(rho, timestamp) AS rho
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
    LAST(rho, timestamp) AS rho
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
-- HELPER FUNCTIONS
-- ============================================================================

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
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - options_bars (hypertable, 1-minute resolution)';
    RAISE NOTICE '  - underlying_bars (hypertable, 1-minute resolution)';
    RAISE NOTICE '';
    RAISE NOTICE 'Continuous Aggregates:';
    RAISE NOTICE '  - 5min, 15min, 1hour, daily (for both options and underlying)';
    RAISE NOTICE '';
    RAISE NOTICE 'Compression:';
    RAISE NOTICE '  - Enabled (7-day policy for both tables)';
    RAISE NOTICE '';
    RAISE NOTICE 'Indexes:';
    RAISE NOTICE '  - Ticker, time range, expiration, strike price, contract type';
    RAISE NOTICE '';
    RAISE NOTICE 'Helper Functions:';
    RAISE NOTICE '  - get_latest_option_data(ticker)';
    RAISE NOTICE '  - get_latest_underlying_price(symbol)';
    RAISE NOTICE '';
    RAISE NOTICE '============================================================================';
END $$;
