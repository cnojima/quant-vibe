-- TimescaleDB initialization script for options trading data
-- This script sets up the schema, hypertables, and continuous aggregates

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- OPTIONS BARS TABLE (1-minute resolution)
-- ============================================================================
CREATE TABLE IF NOT EXISTS options_bars (
    timestamp TIMESTAMPTZ NOT NULL,
    option_ticker TEXT NOT NULL,
    underlying_ticker TEXT NOT NULL,

    -- OHLCV data from Massive
    open NUMERIC(12, 4),
    high NUMERIC(12, 4),
    low NUMERIC(12, 4),
    close NUMERIC(12, 4),
    volume BIGINT,
    vwap NUMERIC(12, 4),
    transactions INTEGER,

    -- Quote data from Schwab
    bid NUMERIC(12, 4),
    ask NUMERIC(12, 4),
    bid_size INTEGER,
    ask_size INTEGER,

    -- Contract details (denormalized for query performance)
    strike_price NUMERIC(12, 4),
    contract_type TEXT, -- 'call' or 'put'
    expiration_date DATE,

    -- Greeks (if available)
    implied_volatility NUMERIC(8, 6),
    delta NUMERIC(8, 6),
    gamma NUMERIC(8, 6),
    theta NUMERIC(8, 6),
    vega NUMERIC(8, 6),
    rho NUMERIC(8, 6),

    -- Metadata
    data_source TEXT, -- 'massive', 'schwab', 'combined'
    created_at TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (timestamp, option_ticker)
);

-- Convert to hypertable (partitioned by time)
SELECT create_hypertable('options_bars', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Enable compression
ALTER TABLE options_bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'option_ticker, underlying_ticker',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add compression policy (compress data older than 7 days)
SELECT add_compression_policy('options_bars', INTERVAL '7 days', if_not_exists => TRUE);

-- ============================================================================
-- INDEXES FOR FAST QUERIES
-- ============================================================================

-- Index for querying by option ticker and time range
CREATE INDEX IF NOT EXISTS idx_options_bars_ticker_time
    ON options_bars (option_ticker, timestamp DESC);

-- Index for querying by underlying ticker (for entire chain queries)
CREATE INDEX IF NOT EXISTS idx_options_bars_underlying_time
    ON options_bars (underlying_ticker, timestamp DESC);

-- Index for querying by expiration date
CREATE INDEX IF NOT EXISTS idx_options_bars_expiration
    ON options_bars (expiration_date, timestamp DESC);

-- Index for querying by contract type
CREATE INDEX IF NOT EXISTS idx_options_bars_type
    ON options_bars (underlying_ticker, contract_type, timestamp DESC);

-- Composite index for strike price queries
CREATE INDEX IF NOT EXISTS idx_options_bars_strike
    ON options_bars (underlying_ticker, expiration_date, strike_price, timestamp DESC);

-- ============================================================================
-- CONTINUOUS AGGREGATES (Pre-computed higher timeframes)
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

-- ============================================================================
-- RETENTION POLICY (Optional - uncomment to auto-delete old data)
-- ============================================================================
-- Keep raw 1-minute data for 90 days, then delete
-- SELECT add_retention_policy('options_bars', INTERVAL '90 days', if_not_exists => TRUE);

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

-- Grant permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO quantvibe;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO quantvibe;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO quantvibe;

-- Create indexes on continuous aggregates for faster queries
CREATE INDEX IF NOT EXISTS idx_options_bars_5min_ticker
    ON options_bars_5min (option_ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_options_bars_15min_ticker
    ON options_bars_15min (option_ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_options_bars_1hour_ticker
    ON options_bars_1hour (option_ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_options_bars_daily_ticker
    ON options_bars_daily (option_ticker, bucket DESC);

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'TimescaleDB schema initialized successfully!';
    RAISE NOTICE 'Hypertable: options_bars';
    RAISE NOTICE 'Continuous Aggregates: 5min, 15min, 1hour, daily';
    RAISE NOTICE 'Compression: Enabled (7-day policy)';
END $$;
