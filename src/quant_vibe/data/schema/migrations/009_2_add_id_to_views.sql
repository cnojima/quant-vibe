-- Usage:
-- PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data \
--    -f /Users/curisu/dev/quant-vibe/src/quant_vibe/data/schema/migrations/009_2_add_id_to_views.sql
-- 5-minute bars
DROP MATERIALIZED VIEW IF EXISTS options_bars_5min;
CREATE MATERIALIZED VIEW IF NOT EXISTS options_bars_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', timestamp) AS bucket,
    id,
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
    LAST(expired, timestamp) AS expired
FROM options_bars
GROUP BY bucket, id, option_ticker, underlying_ticker, strike_price, contract_type, expiration_date
WITH NO DATA;

CALL refresh_continuous_aggregate('options_bars_5min', '2024-02-14 00:00:00', '2024-03-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-03-01 00:05:00', '2024-04-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-04-01 00:05:00', '2024-05-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-05-01 00:05:00', '2024-06-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-06-01 00:05:00', '2024-07-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-07-01 00:05:00', '2024-08-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-08-01 00:05:00', '2024-09-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-09-01 00:05:00', '2024-10-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-10-01 00:05:00', '2024-11-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-11-01 00:05:00', '2024-12-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2024-12-01 00:05:00', '2025-01-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-01-01 00:05:00', '2025-02-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-02-01 00:05:00', '2025-03-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-03-01 00:05:00', '2025-04-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-04-01 00:05:00', '2025-05-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-05-01 00:05:00', '2025-06-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-06-01 00:05:00', '2025-07-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-07-01 00:05:00', '2025-08-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-08-01 00:05:00', '2025-09-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-09-01 00:05:00', '2025-10-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-10-01 00:05:00', '2025-11-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-11-01 00:05:00', '2025-12-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2025-12-01 00:05:00', '2026-01-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_5min', '2026-01-01 00:05:00', now());

-- Refresh policy for 5-minute aggregates
SELECT add_continuous_aggregate_policy('options_bars_5min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

-- 15-minute bars
DROP MATERIALIZED VIEW IF EXISTS options_bars_15min;
CREATE MATERIALIZED VIEW IF NOT EXISTS options_bars_15min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('15 minutes', timestamp) AS bucket,
    id,
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
    LAST(expired, timestamp) AS expired
FROM options_bars
GROUP BY bucket, id, option_ticker, underlying_ticker, strike_price, contract_type, expiration_date
WITH NO DATA;

SELECT add_continuous_aggregate_policy('options_bars_15min',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '15 minutes',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists => TRUE
);

CALL refresh_continuous_aggregate('options_bars_15min', '2024-02-14 00:00:00', '2024-03-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-03-01 00:05:00', '2024-04-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-04-01 00:05:00', '2024-05-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-05-01 00:05:00', '2024-06-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-06-01 00:05:00', '2024-07-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-07-01 00:05:00', '2024-08-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-08-01 00:05:00', '2024-09-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-09-01 00:05:00', '2024-10-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-10-01 00:05:00', '2024-11-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-11-01 00:05:00', '2024-12-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2024-12-01 00:05:00', '2025-01-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-01-01 00:05:00', '2025-02-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-02-01 00:05:00', '2025-03-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-03-01 00:05:00', '2025-04-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-04-01 00:05:00', '2025-05-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-05-01 00:05:00', '2025-06-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-06-01 00:05:00', '2025-07-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-07-01 00:05:00', '2025-08-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-08-01 00:05:00', '2025-09-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-09-01 00:05:00', '2025-10-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-10-01 00:05:00', '2025-11-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-11-01 00:05:00', '2025-12-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2025-12-01 00:05:00', '2026-01-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_15min', '2026-01-01 00:05:00', now());

-- 1-hour bars
DROP MATERIALIZED VIEW IF EXISTS options_bars_1hour;
CREATE MATERIALIZED VIEW IF NOT EXISTS options_bars_1hour
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS bucket,
    id,
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
    LAST(expired, timestamp) AS expired
FROM options_bars
GROUP BY bucket, id, option_ticker, underlying_ticker, strike_price, contract_type, expiration_date
WITH NO DATA;

SELECT add_continuous_aggregate_policy('options_bars_1hour',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

CALL refresh_continuous_aggregate('options_bars_1hour', '2024-02-14 00:00:00', '2024-03-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-03-01 00:05:00', '2024-04-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-04-01 00:05:00', '2024-05-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-05-01 00:05:00', '2024-06-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-06-01 00:05:00', '2024-07-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-07-01 00:05:00', '2024-08-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-08-01 00:05:00', '2024-09-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-09-01 00:05:00', '2024-10-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-10-01 00:05:00', '2024-11-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-11-01 00:05:00', '2024-12-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2024-12-01 00:05:00', '2025-01-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-01-01 00:05:00', '2025-02-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-02-01 00:05:00', '2025-03-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-03-01 00:05:00', '2025-04-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-04-01 00:05:00', '2025-05-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-05-01 00:05:00', '2025-06-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-06-01 00:05:00', '2025-07-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-07-01 00:05:00', '2025-08-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-08-01 00:05:00', '2025-09-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-09-01 00:05:00', '2025-10-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-10-01 00:05:00', '2025-11-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-11-01 00:05:00', '2025-12-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2025-12-01 00:05:00', '2026-01-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_1hour', '2026-01-01 00:05:00', now());

-- Daily bars
DROP MATERIALIZED VIEW IF EXISTS options_bars_daily;
CREATE MATERIALIZED VIEW IF NOT EXISTS options_bars_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', timestamp) AS bucket,
    id,
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
    LAST(expired, timestamp) AS expired
FROM options_bars
GROUP BY bucket, id, option_ticker, underlying_ticker, strike_price, contract_type, expiration_date
WITH NO DATA;

SELECT add_continuous_aggregate_policy('options_bars_daily',
    start_offset => INTERVAL '30 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CALL refresh_continuous_aggregate('options_bars_daily', '2024-02-14 00:00:00', '2024-03-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-03-01 00:05:00', '2024-04-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-04-01 00:05:00', '2024-05-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-05-01 00:05:00', '2024-06-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-06-01 00:05:00', '2024-07-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-07-01 00:05:00', '2024-08-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-08-01 00:05:00', '2024-09-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-09-01 00:05:00', '2024-10-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-10-01 00:05:00', '2024-11-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-11-01 00:05:00', '2024-12-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2024-12-01 00:05:00', '2025-01-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-01-01 00:05:00', '2025-02-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-02-01 00:05:00', '2025-03-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-03-01 00:05:00', '2025-04-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-04-01 00:05:00', '2025-05-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-05-01 00:05:00', '2025-06-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-06-01 00:05:00', '2025-07-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-07-01 00:05:00', '2025-08-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-08-01 00:05:00', '2025-09-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-09-01 00:05:00', '2025-10-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-10-01 00:05:00', '2025-11-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-11-01 00:05:00', '2025-12-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2025-12-01 00:05:00', '2026-01-01 00:00:00');
CALL refresh_continuous_aggregate('options_bars_daily', '2026-01-01 00:05:00', now());

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
    ask NUMERIC,
    expired BOOLEAN,
    id NUMERIC
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
        o.ask,
        o.expired,
        o.id
    FROM options_bars o
    WHERE o.option_ticker = ticker
    ORDER BY o.timestamp DESC
    LIMIT 1;
END;