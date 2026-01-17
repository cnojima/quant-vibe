-- Migration 009_2: Add ID column to continuous aggregates (OPTIMIZED - NO REFRESH)
-- This version skips the expensive refresh operations for development environments
-- Run refresh manually later if needed with: CALL refresh_continuous_aggregate('options_bars_5min', NULL, NULL);

-- Drop and recreate the 5-minute continuous aggregate with ID column
DROP MATERIALIZED VIEW IF EXISTS options_bars_5min CASCADE;

CREATE MATERIALIZED VIEW options_bars_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', timestamp) AS bucket,
    option_ticker,
    MIN(id) as id,  -- Include the ID column
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    AVG(implied_volatility) AS implied_volatility,
    AVG(delta) AS delta,
    AVG(gamma) AS gamma,
    AVG(theta) AS theta,
    AVG(vega) AS vega,
    AVG(rho) AS rho,
    FIRST(underlying_ticker, timestamp) AS underlying_ticker,
    BOOL_OR(expired) AS expired
FROM options_bars
GROUP BY bucket, option_ticker
WITH NO DATA;  -- Create without data initially

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_options_bars_5min_ticker
ON options_bars_5min (option_ticker, bucket DESC);

CREATE INDEX IF NOT EXISTS idx_options_bars_5min_bucket
ON options_bars_5min (bucket DESC);

-- Note: Skipping refresh operations for performance in development
-- To manually refresh all data later, run:
-- CALL refresh_continuous_aggregate('options_bars_5min', NULL, NULL);
--
-- Or refresh specific time ranges:
-- CALL refresh_continuous_aggregate('options_bars_5min', '2024-01-01', '2024-02-01');