-- Migration: Add missing columns to optimization_runs table
-- Purpose: Add columns required by SQLAlchemy model that are missing from database
-- Date: 2026-01-20

BEGIN;

-- Add results_csv_path column for storing CSV file location
ALTER TABLE optimization_runs
ADD COLUMN IF NOT EXISTS results_csv_path TEXT;

-- Add results_json_path column for storing JSON file location
ALTER TABLE optimization_runs
ADD COLUMN IF NOT EXISTS results_json_path TEXT;

-- Add updated_at column for tracking last update time
ALTER TABLE optimization_runs
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Add error_traceback column for detailed error information
ALTER TABLE optimization_runs
ADD COLUMN IF NOT EXISTS error_traceback TEXT;

-- Add comments to columns
COMMENT ON COLUMN optimization_runs.results_csv_path IS 'Path to CSV file containing optimization results';
COMMENT ON COLUMN optimization_runs.results_json_path IS 'Path to JSON file containing optimization results';
COMMENT ON COLUMN optimization_runs.updated_at IS 'Timestamp of last update to this record';
COMMENT ON COLUMN optimization_runs.error_traceback IS 'Full error traceback if optimization failed';

-- Create or update trigger to automatically update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Drop trigger if exists and recreate
DROP TRIGGER IF EXISTS update_optimization_runs_updated_at ON optimization_runs;

CREATE TRIGGER update_optimization_runs_updated_at
BEFORE UPDATE ON optimization_runs
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;

-- Rollback commands (for reference):
-- ALTER TABLE optimization_runs DROP COLUMN IF EXISTS results_csv_path;
-- ALTER TABLE optimization_runs DROP COLUMN IF EXISTS results_json_path;
-- ALTER TABLE optimization_runs DROP COLUMN IF EXISTS updated_at;
-- ALTER TABLE optimization_runs DROP COLUMN IF EXISTS error_traceback;
-- DROP TRIGGER IF EXISTS update_optimization_runs_updated_at ON optimization_runs;
-- DROP FUNCTION IF EXISTS update_updated_at_column();