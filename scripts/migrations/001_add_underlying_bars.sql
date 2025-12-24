-- Migration: Add underlying_bars table for real SPX/SPY price data
-- Run this on existing databases to add the new table
--
-- Usage:
--   psql -U quantvibe -d options_data -f scripts/migrations/001_add_underlying_bars.sql

\echo 'Starting migration: Add underlying_bars table'
\echo ''

-- Import the underlying_bars schema
\i src/quant_vibe/data/schema/underlying_bars.sql

\echo ''
\echo 'Migration complete!'
\echo 'Next steps:'
\echo '  1. Run backfill script to populate historical data'
\echo '  2. Update streaming scripts to collect real-time data'
