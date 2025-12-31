#!/bin/bash
#
# Clean up old backtest results from PostgreSQL
#
# Usage:
#   ./scripts/cleanup_old_backtests.sh [days] [--dry-run]
#
# Examples:
#   ./scripts/cleanup_old_backtests.sh 90 --dry-run  # Preview deletion of backtests older than 90 days
#   ./scripts/cleanup_old_backtests.sh 90             # Delete backtests older than 90 days
#   ./scripts/cleanup_old_backtests.sh 180            # Delete backtests older than 180 days
#

set -e

# Default retention period
DAYS="${1:-90}"
DRY_RUN="${2}"

if [ "$DRY_RUN" == "--dry-run" ]; then
    DRY_RUN_MODE=true
    echo "🔍 DRY RUN MODE - No data will be deleted"
else
    DRY_RUN_MODE=false
fi

echo "========================================================================"
echo "BACKTEST CLEANUP UTILITY"
echo "========================================================================"
echo ""
echo "Retention period: $DAYS days"
echo "Cutoff date: $(date -v-${DAYS}d '+%Y-%m-%d' 2>/dev/null || date -d "$DAYS days ago" '+%Y-%m-%d')"
echo ""

# Check for local or remote database
if [ "$USE_REMOTE_TIMESCALE" == "true" ]; then
    DB_HOST="${REMOTE_TIMESCALE_HOST}"
    DB_PORT="${REMOTE_TIMESCALE_PORT:-5432}"
    DB_NAME="${REMOTE_TIMESCALE_DB:-options_data}"
    DB_USER="${REMOTE_TIMESCALE_USER:-quantvibe}"
    export PGPASSWORD="${REMOTE_TIMESCALE_PASSWORD}"
    echo "Database: Remote ($DB_HOST)"
else
    DB_HOST="localhost"
    DB_PORT="5432"
    DB_NAME="options_data"
    DB_USER="quantvibe"
    export PGPASSWORD="quantvibe_dev"
    echo "Database: Local (Docker)"
fi

echo ""

# Function to run psql command
run_psql() {
    if [ "$DB_HOST" == "localhost" ]; then
        docker exec -i quant-vibe-timescaledb psql -U "$DB_USER" -d "$DB_NAME" -t -c "$1"
    else
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "$1"
    fi
}

# Count backtests that would be deleted
echo "1. Checking for old backtests..."
OLD_COUNT=$(run_psql "
    SELECT COUNT(*)
    FROM backtest_runs
    WHERE created_at < NOW() - INTERVAL '$DAYS days';
" | tr -d ' ')

if [ "$OLD_COUNT" -eq 0 ]; then
    echo "✅ No backtests older than $DAYS days found"
    exit 0
fi

echo "⚠️  Found $OLD_COUNT backtest(s) older than $DAYS days"
echo ""

# Show details of backtests to be deleted
echo "2. Backtests that will be deleted:"
echo ""
run_psql "
    SELECT
        backtest_id,
        strategy_name,
        created_at::date as created_date,
        status,
        num_trades
    FROM backtest_runs
    WHERE created_at < NOW() - INTERVAL '$DAYS days'
    ORDER BY created_at DESC;
" | head -20

if [ "$OLD_COUNT" -gt 20 ]; then
    echo "... and $((OLD_COUNT - 20)) more"
fi

echo ""

# Count associated records
echo "3. Counting associated records..."

TRADES_COUNT=$(run_psql "
    SELECT COUNT(*)
    FROM backtest_trades bt
    JOIN backtest_runs br ON bt.backtest_id = br.backtest_id
    WHERE br.created_at < NOW() - INTERVAL '$DAYS days';
" | tr -d ' ')

EQUITY_COUNT=$(run_psql "
    SELECT COUNT(*)
    FROM backtest_equity_curve bec
    JOIN backtest_runs br ON bec.backtest_id = br.backtest_id
    WHERE br.created_at < NOW() - INTERVAL '$DAYS days';
" | tr -d ' ')

echo "   Backtest runs: $OLD_COUNT"
echo "   Trade records: $TRADES_COUNT"
echo "   Equity curve points: $EQUITY_COUNT"
echo ""

# Estimate space savings
EQUITY_SIZE=$(run_psql "
    SELECT pg_size_pretty(pg_total_relation_size('backtest_equity_curve'));
" | tr -d ' ')

echo "   Current equity_curve table size: $EQUITY_SIZE"
echo ""

if [ "$DRY_RUN_MODE" == true ]; then
    echo "========================================================================"
    echo "🔍 DRY RUN COMPLETE - No data was deleted"
    echo "========================================================================"
    echo ""
    echo "To actually delete these backtests, run:"
    echo "  ./scripts/cleanup_old_backtests.sh $DAYS"
    echo ""
    exit 0
fi

# Confirm deletion
echo "⚠️  WARNING: This will permanently delete $OLD_COUNT backtest(s) and all associated data!"
echo ""
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "❌ Cancelled"
    exit 1
fi

echo ""
echo "4. Deleting old backtests..."

# Delete backtests (cascades to trades and equity curve due to foreign keys)
run_psql "
    DELETE FROM backtest_runs
    WHERE created_at < NOW() - INTERVAL '$DAYS days';
"

echo "✅ Deleted $OLD_COUNT backtest(s) and all associated records"
echo ""

# Vacuum to reclaim space
echo "5. Reclaiming disk space (VACUUM)..."
run_psql "VACUUM ANALYZE backtest_runs;"
run_psql "VACUUM ANALYZE backtest_trades;"
run_psql "VACUUM ANALYZE backtest_equity_curve;"

echo "✅ Vacuum complete"
echo ""

# Show new table sizes
NEW_EQUITY_SIZE=$(run_psql "
    SELECT pg_size_pretty(pg_total_relation_size('backtest_equity_curve'));
" | tr -d ' ')

echo "========================================================================"
echo "✅ CLEANUP COMPLETE"
echo "========================================================================"
echo ""
echo "Deleted: $OLD_COUNT backtest(s)"
echo "Previous equity_curve size: $EQUITY_SIZE"
echo "Current equity_curve size: $NEW_EQUITY_SIZE"
echo ""
