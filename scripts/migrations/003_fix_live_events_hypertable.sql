-- Migration: Fix live_events table to support TimescaleDB hypertable
-- Created: 2026-01-04
-- Description: Recreates live_events table with timestamp as first column in PRIMARY KEY
--              to satisfy TimescaleDB hypertable requirements

-- Drop existing table and recreate with correct column order
DROP TABLE IF EXISTS live_events CASCADE;

CREATE TABLE live_events (
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

-- Create hypertable for time-series optimization
-- This requires the TimescaleDB extension to be enabled
SELECT create_hypertable('live_events', 'timestamp',
    migrate_data => TRUE,
    if_not_exists => TRUE
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_live_events_strategy ON live_events(strategy_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_live_events_position ON live_events(position_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_live_events_severity ON live_events(severity, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_live_events_type ON live_events(event_type, timestamp DESC);

-- Add comment for documentation
COMMENT ON TABLE live_events IS 'Audit log for live trading events, partitioned by time using TimescaleDB hypertables';
COMMENT ON COLUMN live_events.timestamp IS 'Event timestamp - used as partitioning column for hypertable';
COMMENT ON COLUMN live_events.details IS 'JSONB structure containing additional event-specific details';
