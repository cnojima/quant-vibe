#!/bin/bash
#
# Apply database migration to remote TimescaleDB
#
# Usage:
#   ./scripts/apply_migration_remote.sh
#
# Requirements:
#   - REMOTE_TIMESCALE_* environment variables set in .env
#   - Remote database accessible from this machine
#   - psql client installed
#

set -e

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check required environment variables
if [ -z "$REMOTE_TIMESCALE_HOST" ] || [ -z "$REMOTE_TIMESCALE_PASSWORD" ]; then
    echo "❌ Error: Remote database credentials not set in .env"
    echo ""
    echo "Required environment variables:"
    echo "  REMOTE_TIMESCALE_HOST"
    echo "  REMOTE_TIMESCALE_PORT (default: 5432)"
    echo "  REMOTE_TIMESCALE_DB (default: options_data)"
    echo "  REMOTE_TIMESCALE_USER (default: quantvibe)"
    echo "  REMOTE_TIMESCALE_PASSWORD"
    exit 1
fi

# Set defaults
REMOTE_HOST="${REMOTE_TIMESCALE_HOST}"
REMOTE_PORT="${REMOTE_TIMESCALE_PORT:-5432}"
REMOTE_DB="${REMOTE_TIMESCALE_DB:-options_data}"
REMOTE_USER="${REMOTE_TIMESCALE_USER:-quantvibe}"

echo "========================================================================"
echo "APPLYING MIGRATION TO REMOTE DATABASE"
echo "========================================================================"
echo ""
echo "Host: $REMOTE_HOST"
echo "Port: $REMOTE_PORT"
echo "Database: $REMOTE_DB"
echo "User: $REMOTE_USER"
echo ""

# Test connection
echo "1. Testing connection..."
export PGPASSWORD="$REMOTE_TIMESCALE_PASSWORD"

if ! psql -h "$REMOTE_HOST" -p "$REMOTE_PORT" -U "$REMOTE_USER" -d "$REMOTE_DB" -c "SELECT 1;" > /dev/null 2>&1; then
    echo "❌ Connection failed!"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check if remote server is running"
    echo "  2. Verify firewall allows connections on port $REMOTE_PORT"
    echo "  3. Check PostgreSQL pg_hba.conf allows remote connections"
    echo "  4. Verify credentials in .env are correct"
    exit 1
fi

echo "✅ Connection successful"
echo ""

# Check if tables already exist
echo "2. Checking for existing backtest tables..."
EXISTING_TABLES=$(psql -h "$REMOTE_HOST" -p "$REMOTE_PORT" -U "$REMOTE_USER" -d "$REMOTE_DB" -t -c "
    SELECT COUNT(*)
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name LIKE 'backtest%';
")

if [ "$EXISTING_TABLES" -gt 0 ]; then
    echo "⚠️  Found $EXISTING_TABLES existing backtest table(s)"
    echo ""
    echo "Options:"
    echo "  1. Skip migration (tables already exist)"
    echo "  2. Drop existing tables and re-run migration"
    echo "  3. Cancel"
    echo ""
    read -p "Enter choice [1-3]: " choice

    case $choice in
        1)
            echo "✅ Skipping migration - tables already exist"
            exit 0
            ;;
        2)
            echo "⚠️  Dropping existing backtest tables..."
            psql -h "$REMOTE_HOST" -p "$REMOTE_PORT" -U "$REMOTE_USER" -d "$REMOTE_DB" << 'SQL'
DROP TABLE IF EXISTS backtest_equity_curve CASCADE;
DROP TABLE IF EXISTS backtest_trades CASCADE;
DROP TABLE IF EXISTS backtest_runs CASCADE;
DROP FUNCTION IF EXISTS get_latest_backtest(TEXT);
DROP FUNCTION IF EXISTS get_backtest_summary(TEXT);
SQL
            echo "✅ Tables dropped"
            ;;
        *)
            echo "❌ Cancelled"
            exit 1
            ;;
    esac
fi

# Apply migration
echo ""
echo "3. Applying migration 001_add_backtest_results.sql..."

if psql -h "$REMOTE_HOST" -p "$REMOTE_PORT" -U "$REMOTE_USER" -d "$REMOTE_DB" < src/quant_vibe/data/schema/migrations/001_add_backtest_results.sql; then
    echo ""
    echo "✅ Migration applied successfully!"
    echo ""

    # Verify tables were created
    echo "4. Verifying migration..."
    psql -h "$REMOTE_HOST" -p "$REMOTE_PORT" -U "$REMOTE_USER" -d "$REMOTE_DB" << 'SQL'
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'backtest%'
ORDER BY table_name;
SQL

    echo ""
    echo "========================================================================"
    echo "✅ REMOTE DATABASE MIGRATION COMPLETE"
    echo "========================================================================"
else
    echo ""
    echo "❌ Migration failed!"
    exit 1
fi
