-- Schema for underlying asset price data (SPX, SPY, etc.)
-- This stores actual index/stock prices to use for accurate intrinsic value calculations

-- ============================================================================
-- UNDERLYING BARS TABLE (1-minute resolution)
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
-- INDEXES FOR FAST QUERIES
-- ============================================================================

-- Index for querying by ticker and time range
CREATE INDEX IF NOT EXISTS idx_underlying_bars_ticker_time
    ON underlying_bars (ticker, timestamp DESC);

-- Index for querying recent data
CREATE INDEX IF NOT EXISTS idx_underlying_bars_recent
    ON underlying_bars (timestamp DESC);

-- ============================================================================
-- CONTINUOUS AGGREGATES (Pre-computed higher timeframes)
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

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

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

-- Grant permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO quantvibe;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO quantvibe;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO quantvibe;

-- Create indexes on continuous aggregates
CREATE INDEX IF NOT EXISTS idx_underlying_bars_5min_ticker
    ON underlying_bars_5min (ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_underlying_bars_15min_ticker
    ON underlying_bars_15min (ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_underlying_bars_1hour_ticker
    ON underlying_bars_1hour (ticker, bucket DESC);
CREATE INDEX IF NOT EXISTS idx_underlying_bars_daily_ticker
    ON underlying_bars_daily (ticker, bucket DESC);

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Underlying bars schema created successfully!';
    RAISE NOTICE 'Hypertable: underlying_bars';
    RAISE NOTICE 'Continuous Aggregates: 5min, 15min, 1hour, daily';
    RAISE NOTICE 'Compression: Enabled (7-day policy)';
END $$;
