-- ============================================================================
-- Migration: Add notifications tracking table
-- ============================================================================
-- This migration adds a table to track all Pushover notifications sent by
-- the system for audit and historical analysis purposes.
--
-- Usage:
--   docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/001_add_notifications_table.sql
-- ============================================================================

-- ============================================================================
-- NOTIFICATIONS TABLE
-- ============================================================================
-- Stores all notifications sent via Pushover for audit and history
-- ============================================================================

CREATE TABLE IF NOT EXISTS notifications (
    notification_id SERIAL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Notification content
    title TEXT,
    message TEXT NOT NULL,

    -- Classification
    notification_type TEXT NOT NULL, -- 'order_filled', 'position_opened', 'position_closed',
                                     -- 'critical_alert', 'warning', 'info', 'engine_started',
                                     -- 'engine_stopped', 'daily_summary', 'optimization_complete',
                                     -- 'optimization_failed', 'backtest_complete', 'backtest_failed', 'custom'

    -- Pushover-specific fields
    priority INTEGER DEFAULT 0, -- -2 (lowest), -1 (low), 0 (normal), 1 (high), 2 (emergency)
    sound TEXT,
    device TEXT,

    -- Status tracking
    sent_successfully BOOLEAN NOT NULL DEFAULT false,
    error_message TEXT,

    -- Additional metadata (stored as JSONB for flexibility)
    metadata JSONB, -- Can include: strategy_name, backtest_id, optimization_id,
                    -- pnl, win_rate, symbols, prices, etc.

    -- URLs (for supplementary links)
    url TEXT,
    url_title TEXT,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Composite primary key including partitioning column
    PRIMARY KEY (sent_at, notification_id)
);

-- Convert to hypertable (partitioned by time for efficient queries)
-- Chunk interval: 7 days
SELECT create_hypertable('notifications', 'sent_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Enable compression to save storage
ALTER TABLE notifications SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'notification_type',
    timescaledb.compress_orderby = 'sent_at DESC'
);

-- Add compression policy (compress data older than 30 days)
SELECT add_compression_policy('notifications', INTERVAL '30 days', if_not_exists => TRUE);

-- ============================================================================
-- INDEXES FOR FAST QUERIES
-- ============================================================================

-- Index for querying by notification type and time
CREATE INDEX IF NOT EXISTS idx_notifications_type_time
    ON notifications (notification_type, sent_at DESC);

-- Index for querying recent notifications
CREATE INDEX IF NOT EXISTS idx_notifications_sent_at
    ON notifications (sent_at DESC);

-- Index for querying by success status
CREATE INDEX IF NOT EXISTS idx_notifications_status
    ON notifications (sent_successfully, sent_at DESC);

-- GIN index for JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_notifications_metadata
    ON notifications USING GIN (metadata);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to get recent notifications
CREATE OR REPLACE FUNCTION get_recent_notifications(
    limit_count INTEGER DEFAULT 100,
    notification_type_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    notification_id INTEGER,
    title TEXT,
    message TEXT,
    notification_type TEXT,
    priority INTEGER,
    sent_successfully BOOLEAN,
    metadata JSONB,
    sent_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        n.notification_id,
        n.title,
        n.message,
        n.notification_type,
        n.priority,
        n.sent_successfully,
        n.metadata,
        n.sent_at
    FROM notifications n
    WHERE notification_type_filter IS NULL OR n.notification_type = notification_type_filter
    ORDER BY n.sent_at DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- Function to get notification statistics
CREATE OR REPLACE FUNCTION get_notification_stats(
    start_time TIMESTAMPTZ DEFAULT NOW() - INTERVAL '30 days',
    end_time TIMESTAMPTZ DEFAULT NOW()
)
RETURNS TABLE (
    notification_type TEXT,
    total_count BIGINT,
    success_count BIGINT,
    failure_count BIGINT,
    success_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        n.notification_type,
        COUNT(*) AS total_count,
        SUM(CASE WHEN n.sent_successfully THEN 1 ELSE 0 END) AS success_count,
        SUM(CASE WHEN NOT n.sent_successfully THEN 1 ELSE 0 END) AS failure_count,
        ROUND(
            (SUM(CASE WHEN n.sent_successfully THEN 1 ELSE 0 END)::NUMERIC / COUNT(*)::NUMERIC) * 100,
            2
        ) AS success_rate
    FROM notifications n
    WHERE n.sent_at BETWEEN start_time AND end_time
    GROUP BY n.notification_type
    ORDER BY total_count DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to clean up old notifications (optional retention)
CREATE OR REPLACE FUNCTION cleanup_old_notifications(
    retention_days INTEGER DEFAULT 90
)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM notifications
    WHERE sent_at < NOW() - (retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- RETENTION POLICY (Optional - currently disabled)
-- ============================================================================
-- Uncomment to auto-delete notifications older than 90 days:
-- SELECT add_retention_policy('notifications', INTERVAL '90 days', if_not_exists => TRUE);

-- ============================================================================
-- GRANT PERMISSIONS
-- ============================================================================

GRANT ALL ON notifications TO quantvibe;
GRANT ALL ON SEQUENCE notifications_notification_id_seq TO quantvibe;

-- ============================================================================
-- SUCCESS MESSAGE
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================================================';
    RAISE NOTICE 'Notifications table created successfully!';
    RAISE NOTICE '============================================================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Table: notifications (hypertable)';
    RAISE NOTICE '  - Tracks all Pushover notifications sent by the system';
    RAISE NOTICE '  - Partitioned by time (7-day chunks)';
    RAISE NOTICE '  - Compression enabled (30-day policy)';
    RAISE NOTICE '';
    RAISE NOTICE 'Helper Functions:';
    RAISE NOTICE '  - get_recent_notifications(limit, type_filter)';
    RAISE NOTICE '  - get_notification_stats(start_time, end_time)';
    RAISE NOTICE '  - cleanup_old_notifications(retention_days)';
    RAISE NOTICE '';
    RAISE NOTICE '============================================================================';
END $$;
