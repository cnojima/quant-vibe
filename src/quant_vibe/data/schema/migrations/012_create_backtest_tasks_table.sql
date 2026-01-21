-- Migration: Create backtest_tasks table
-- Description: Creates table for tracking backtest tasks and their status
-- Date: 2024-01-20
-- Usage:
--   PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/012_create_backtest_tasks_table.sql
-- Create enum type for backtest status
DO $$ BEGIN
    CREATE TYPE backtest_status AS ENUM (
        'pending',
        'running',
        'completed',
        'failed',
        'cancelled'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create backtest_tasks table
CREATE TABLE IF NOT EXISTS backtest_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_name VARCHAR(100) NOT NULL,
    params JSONB NOT NULL,
    status backtest_status NOT NULL DEFAULT 'pending',
    progress FLOAT DEFAULT 0.0 CHECK (progress >= 0 AND progress <= 100),
    ticker VARCHAR(20) NOT NULL DEFAULT '$SPX',
    timeframe VARCHAR(10) NOT NULL DEFAULT '5min',
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    end_date TIMESTAMP WITH TIME ZONE NOT NULL,
    initial_capital FLOAT NOT NULL CHECK (initial_capital > 0),
    description VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    result_id UUID,

    -- Performance metrics (populated after completion)
    total_return FLOAT,
    sharpe_ratio FLOAT,
    max_drawdown FLOAT,
    win_rate FLOAT CHECK (win_rate IS NULL OR (win_rate >= 0 AND win_rate <= 100)),
    total_trades INTEGER CHECK (total_trades IS NULL OR total_trades >= 0),
    profit_factor FLOAT,

    -- Constraints
    CONSTRAINT valid_date_range CHECK (end_date > start_date),
    CONSTRAINT valid_started_at CHECK (started_at IS NULL OR started_at >= created_at),
    CONSTRAINT valid_completed_at CHECK (completed_at IS NULL OR completed_at >= started_at)
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_status ON backtest_tasks(status);
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_strategy ON backtest_tasks(strategy_name);
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_created_at ON backtest_tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_ticker ON backtest_tasks(ticker);
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_date_range ON backtest_tasks(start_date, end_date);

-- Create index on JSONB params for efficient querying
CREATE INDEX IF NOT EXISTS idx_backtest_tasks_params ON backtest_tasks USING GIN (params);

-- Add comment to table
COMMENT ON TABLE backtest_tasks IS 'Tracks backtest tasks with their status, parameters, and results';

-- Add comments to columns
COMMENT ON COLUMN backtest_tasks.id IS 'Unique identifier for the backtest task';
COMMENT ON COLUMN backtest_tasks.strategy_name IS 'Name of the strategy being backtested';
COMMENT ON COLUMN backtest_tasks.params IS 'Strategy parameters as JSON';
COMMENT ON COLUMN backtest_tasks.status IS 'Current status of the backtest';
COMMENT ON COLUMN backtest_tasks.progress IS 'Progress percentage (0-100)';
COMMENT ON COLUMN backtest_tasks.ticker IS 'Ticker symbol being traded';
COMMENT ON COLUMN backtest_tasks.timeframe IS 'Data timeframe (1min, 5min, etc.)';
COMMENT ON COLUMN backtest_tasks.start_date IS 'Backtest start date';
COMMENT ON COLUMN backtest_tasks.end_date IS 'Backtest end date';
COMMENT ON COLUMN backtest_tasks.initial_capital IS 'Starting capital for the backtest';
COMMENT ON COLUMN backtest_tasks.description IS 'Optional description of the backtest';
COMMENT ON COLUMN backtest_tasks.created_at IS 'When the backtest was created';
COMMENT ON COLUMN backtest_tasks.started_at IS 'When the backtest started processing';
COMMENT ON COLUMN backtest_tasks.completed_at IS 'When the backtest completed';
COMMENT ON COLUMN backtest_tasks.error_message IS 'Error message if the backtest failed';
COMMENT ON COLUMN backtest_tasks.result_id IS 'Reference to detailed results (if stored separately)';
COMMENT ON COLUMN backtest_tasks.total_return IS 'Total return percentage';
COMMENT ON COLUMN backtest_tasks.sharpe_ratio IS 'Sharpe ratio of the strategy';
COMMENT ON COLUMN backtest_tasks.max_drawdown IS 'Maximum drawdown percentage';
COMMENT ON COLUMN backtest_tasks.win_rate IS 'Percentage of winning trades';
COMMENT ON COLUMN backtest_tasks.total_trades IS 'Total number of trades executed';
COMMENT ON COLUMN backtest_tasks.profit_factor IS 'Ratio of gross profit to gross loss';