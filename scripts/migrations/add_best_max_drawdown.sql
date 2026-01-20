-- Migration: Add best_max_drawdown column to optimization_runs table
-- Purpose: Track the best maximum drawdown metric for optimization results
-- Date: 2026-01-20

BEGIN;

-- Add best_max_drawdown column to optimization_runs table
ALTER TABLE optimization_runs
ADD COLUMN IF NOT EXISTS best_max_drawdown NUMERIC(10,4);

-- Add comment to the column
COMMENT ON COLUMN optimization_runs.best_max_drawdown IS 'Best maximum drawdown percentage achieved during optimization';

-- Update existing rows with a default value (optional)
-- You may want to recalculate these from historical results
UPDATE optimization_runs
SET best_max_drawdown = 0
WHERE best_max_drawdown IS NULL
  AND status = 'completed';

COMMIT;

-- Rollback command (for reference):
-- ALTER TABLE optimization_runs DROP COLUMN IF EXISTS best_max_drawdown;