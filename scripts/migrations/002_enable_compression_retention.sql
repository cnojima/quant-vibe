-- ============================================================================
-- Enable Compression and Retention Policies for Backtest Data
-- ============================================================================
-- This migration adds compression and optional retention policies for
-- backtest data to optimize storage and manage data lifecycle.
--
-- Usage:
--   docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < scripts/migrations/002_enable_compression_retention.sql
-- ============================================================================

-- ============================================================================
-- COMPRESSION FOR EQUITY CURVE (TimescaleDB Hypertable)
-- ============================================================================
-- Compress backtest equity curve data older than 7 days to save storage space
-- Compression ratios typically 10-20x for time-series data
-- ============================================================================

-- Enable compression on backtest_equity_curve hypertable
ALTER TABLE backtest_equity_curve SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'backtest_id',
    timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add automatic compression policy
-- Compresses chunks older than 7 days
SELECT add_compression_policy('backtest_equity_curve', INTERVAL '7 days', if_not_exists => TRUE);

-- ============================================================================
-- DATA RETENTION POLICIES (OPTIONAL - COMMENTED OUT BY DEFAULT)
-- ============================================================================
-- Uncomment these to enable automatic data cleanup after specified periods
-- WARNING: This will permanently delete old backtest data!
-- ============================================================================

-- Option 1: Keep backtest results for 90 days (recommended for development)
-- SELECT add_retention_policy('backtest_equity_curve', INTERVAL '90 days', if_not_exists => TRUE);

-- Option 2: Keep backtest results for 180 days (6 months)
-- SELECT add_retention_policy('backtest_equity_curve', INTERVAL '180 days', if_not_exists => TRUE);

-- Option 3: Keep backtest results for 365 days (1 year)
-- SELECT add_retention_policy('backtest_equity_curve', INTERVAL '365 days', if_not_exists => TRUE);

-- NOTE: Retention policies only apply to hypertables (equity_curve)
-- For backtest_runs and backtest_trades, use manual cleanup:
--
-- DELETE FROM backtest_runs
-- WHERE created_at < NOW() - INTERVAL '90 days';
--
-- This will cascade delete to backtest_trades and backtest_equity_curve
-- due to foreign key constraints.

-- ============================================================================
-- VERIFY COMPRESSION SETTINGS
-- ============================================================================

-- Check compression settings
SELECT
    h.hypertable_name,
    c.segmentby_column_names,
    c.orderby_column_names,
    count(*) as num_chunks
FROM timescaledb_information.hypertables h
LEFT JOIN timescaledb_information.compression_settings c
    ON h.hypertable_schema = c.hypertable_schema
    AND h.hypertable_name = c.hypertable_name
LEFT JOIN timescaledb_information.chunks ch
    ON h.hypertable_schema = ch.hypertable_schema
    AND h.hypertable_name = ch.hypertable_name
WHERE h.hypertable_name = 'backtest_equity_curve'
GROUP BY h.hypertable_name, c.segmentby_column_names, c.orderby_column_names;

-- Check compression policies
SELECT
    application_name,
    hypertable_name,
    config
FROM timescaledb_information.jobs
WHERE application_name LIKE '%compression%';

-- Check current compression stats
SELECT
    h.hypertable_name,
    c.chunk_name,
    c.is_compressed,
    pg_size_pretty(c.before_compression_total_bytes) AS before_compression,
    pg_size_pretty(c.after_compression_total_bytes) AS after_compression,
    ROUND((1 - c.after_compression_total_bytes::NUMERIC / c.before_compression_total_bytes) * 100, 2) AS compression_ratio_pct
FROM timescaledb_information.hypertables h
JOIN timescaledb_information.chunks c
    ON h.hypertable_schema = c.hypertable_schema
    AND h.hypertable_name = c.hypertable_name
WHERE h.hypertable_name = 'backtest_equity_curve'
    AND c.is_compressed = TRUE
ORDER BY c.chunk_name DESC
LIMIT 10;

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================================';
    RAISE NOTICE 'Compression and retention policies configured!';
    RAISE NOTICE '============================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Compression:';
    RAISE NOTICE '  - Enabled on backtest_equity_curve hypertable';
    RAISE NOTICE '  - Automatically compresses data older than 7 days';
    RAISE NOTICE '  - Segmented by backtest_id for efficient queries';
    RAISE NOTICE '  - Ordered by timestamp DESC';
    RAISE NOTICE '';
    RAISE NOTICE 'Retention Policies:';
    RAISE NOTICE '  - NOT enabled by default (data kept indefinitely)';
    RAISE NOTICE '  - Uncomment SQL statements above to enable automatic cleanup';
    RAISE NOTICE '  - Options: 90 days, 180 days, or 365 days';
    RAISE NOTICE '';
    RAISE NOTICE 'To manually compress existing chunks immediately:';
    RAISE NOTICE '  SELECT compress_chunk(show_chunks(''backtest_equity_curve''));';
    RAISE NOTICE '';
    RAISE NOTICE 'To view compression stats:';
    RAISE NOTICE '  SELECT * FROM timescaledb_information.compressed_chunk_stats;';
    RAISE NOTICE '';
    RAISE NOTICE '============================================================================';
END $$;
