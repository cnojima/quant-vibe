-- Migration: Add backtest_analysis table for storing analysis results
-- Created: 2026-01-03
-- Description: Stores structured analysis findings and narrative summaries for backtest results

-- Create backtest_analysis table
CREATE TABLE IF NOT EXISTS backtest_analysis (
    analysis_id SERIAL PRIMARY KEY,
    backtest_id TEXT NOT NULL REFERENCES backtest_runs(backtest_id) ON DELETE CASCADE,
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Analysis metadata
    total_trades INTEGER NOT NULL,
    outlier_threshold_pct NUMERIC(10,4) NOT NULL,  -- e.g., 2.0 for 2 standard deviations
    num_big_winners INTEGER NOT NULL,
    num_big_losers INTEGER NOT NULL,

    -- Structured findings (JSONB for queryability and filtering)
    -- Structure: {big_winners: [...], big_losers: [...], patterns: {...}}
    findings JSONB NOT NULL,

    -- Narrative summaries (markdown format)
    summary_markdown TEXT,
    recommendations_markdown TEXT,

    -- Version tracking for analyzer changes
    analyzer_version TEXT NOT NULL DEFAULT '1.0.0',

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_backtest_analysis_backtest_id ON backtest_analysis(backtest_id);
CREATE INDEX IF NOT EXISTS idx_backtest_analysis_analyzed_at ON backtest_analysis(analyzed_at DESC);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_backtest_analysis_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_backtest_analysis_updated_at
    BEFORE UPDATE ON backtest_analysis
    FOR EACH ROW
    EXECUTE FUNCTION update_backtest_analysis_updated_at();

-- Add comment for documentation
COMMENT ON TABLE backtest_analysis IS 'Stores detailed analysis results for backtests, including outlier trade insights, patterns, and narrative summaries';
COMMENT ON COLUMN backtest_analysis.findings IS 'JSONB structure containing big_winners, big_losers arrays and patterns object with detailed insights';
COMMENT ON COLUMN backtest_analysis.summary_markdown IS 'Human-readable markdown summary of analysis findings';
COMMENT ON COLUMN backtest_analysis.recommendations_markdown IS 'Markdown-formatted recommendations for strategy improvement';
