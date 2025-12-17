-- Verify Schwab enrichment data in TimescaleDB
-- Run this to check if enrichment fields are populated

-- 1. Check data sources
SELECT
    data_source,
    COUNT(*) as row_count,
    COUNT(bid) as bid_count,
    COUNT(delta) as delta_count
FROM options_bars
GROUP BY data_source;

-- 2. Sample enriched data (if any)
SELECT
    timestamp,
    option_ticker,
    close,
    bid,
    ask,
    delta,
    gamma,
    theta,
    vega,
    implied_volatility,
    data_source
FROM options_bars
WHERE data_source = 'schwab'
    AND bid IS NOT NULL
LIMIT 10;

-- 3. Check for NULL enrichment fields
SELECT
    COUNT(*) as total_schwab_rows,
    COUNT(bid) as has_bid,
    COUNT(ask) as has_ask,
    COUNT(delta) as has_delta,
    COUNT(gamma) as has_gamma,
    COUNT(theta) as has_theta,
    COUNT(vega) as has_vega,
    COUNT(rho) as has_rho,
    COUNT(implied_volatility) as has_iv
FROM options_bars
WHERE data_source = 'schwab';

-- 4. Show recent enriched data with all fields
SELECT
    timestamp,
    option_ticker,
    -- OHLCV
    open, high, low, close, volume,
    -- Quote data
    bid, ask, bid_size, ask_size,
    -- Greeks
    delta, gamma, theta, vega, rho,
    implied_volatility
FROM options_bars
WHERE data_source = 'schwab'
ORDER BY timestamp DESC
LIMIT 5;
