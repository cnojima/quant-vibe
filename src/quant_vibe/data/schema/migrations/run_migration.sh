#!/bin/bash

# Migration runner script for all database migrations
# Usage: ./run_migration.sh [local|remote] [--force]
#
# Options:
#   local|remote  - Database profile to use (default: local)
#   --force       - Re-run all migrations, even if already applied

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load environment variables from multiple possible locations
for env_file in "$SCRIPT_DIR/../../../../.env" "$SCRIPT_DIR/../../../.env" "$SCRIPT_DIR/../../.env" "$SCRIPT_DIR/../.env" "$SCRIPT_DIR/.env"; do
    if [ -f "$env_file" ]; then
        echo -e "${BLUE}Loading environment from: $env_file${NC}"
        export $(grep -v '^#' "$env_file" | xargs)
        break
    fi
done

# Parse arguments
DB_PROFILE="${1:-local}"
FORCE_RUN=false

for arg in "$@"; do
    if [ "$arg" = "--force" ]; then
        FORCE_RUN=true
    fi
done

# Configure database connection
if [ "$DB_PROFILE" = "remote" ]; then
    echo -e "${YELLOW}Using REMOTE database...${NC}"
    DB_HOST="${REMOTE_TIMESCALE_HOST:-localhost}"
    DB_PORT="${REMOTE_TIMESCALE_PORT:-5432}"
    DB_NAME="${REMOTE_TIMESCALE_DB:-options_data}"
    DB_USER="${REMOTE_TIMESCALE_USER:-quantvibe}"
    DB_PASSWORD="${REMOTE_TIMESCALE_PASSWORD:-quantvibe_dev}"
else
    echo -e "${YELLOW}Using LOCAL database...${NC}"
    DB_HOST="${TIMESCALE_HOST:-localhost}"
    DB_PORT="${TIMESCALE_PORT:-5432}"
    DB_NAME="${TIMESCALE_DB:-options_data}"
    DB_USER="${TIMESCALE_USER:-quantvibe}"
    DB_PASSWORD="${TIMESCALE_PASSWORD:-quantvibe_dev}"
fi

echo -e "${BLUE}Database: $DB_HOST:$DB_PORT/$DB_NAME${NC}"
echo -e "${BLUE}User: $DB_USER${NC}"
echo ""

# Function to run SQL command
run_sql() {
    PGPASSWORD="$DB_PASSWORD" psql \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -t \
        -A \
        -c "$1"
}

# Function to run SQL file
run_sql_file() {
    PGPASSWORD="$DB_PASSWORD" psql \
        -h "$DB_HOST" \
        -p "$DB_PORT" \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -f "$1"
}

# Create migrations tracking table if it doesn't exist
echo -e "${BLUE}Setting up migrations tracking table...${NC}"
run_sql "
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name VARCHAR(255) PRIMARY KEY,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    success BOOLEAN DEFAULT true,
    error_message TEXT
);"

# Get list of already applied migrations
if [ "$FORCE_RUN" = true ]; then
    echo -e "${YELLOW}Force mode enabled - all migrations will be re-run${NC}"
    APPLIED_MIGRATIONS=""
else
    APPLIED_MIGRATIONS=$(run_sql "SELECT migration_name FROM schema_migrations WHERE success = true;" 2>/dev/null || echo "")
fi

# Count migrations
TOTAL_MIGRATIONS=$(ls "$SCRIPT_DIR"/*.sql 2>/dev/null | wc -l)
APPLIED_COUNT=0
SKIPPED_COUNT=0
ERROR_COUNT=0

echo -e "${BLUE}Found $TOTAL_MIGRATIONS migration files${NC}"
echo ""
echo "================================================"

# Run each migration in order
for migration_file in $(ls "$SCRIPT_DIR"/*.sql 2>/dev/null | sort); do
    migration_name=$(basename "$migration_file")

    # Check if migration was already applied
    if echo "$APPLIED_MIGRATIONS" | grep -q "^$migration_name$"; then
        echo -e "${YELLOW}[SKIP]${NC} $migration_name (already applied)"
        ((SKIPPED_COUNT++))
        continue
    fi

    echo -e "${BLUE}[RUN]${NC} $migration_name"
    echo "  Executing migration..."

    # Begin transaction and run migration
    if run_sql_file "$migration_file" 2>/tmp/migration_error.log; then
        # Record successful migration
        run_sql "INSERT INTO schema_migrations (migration_name) VALUES ('$migration_name') ON CONFLICT (migration_name) DO UPDATE SET executed_at = NOW(), success = true, error_message = NULL;"
        echo -e "  ${GREEN}✓ Success${NC}"
        ((APPLIED_COUNT++))
    else
        # Record failed migration
        ERROR_MSG=$(cat /tmp/migration_error.log | tr '\n' ' ' | cut -c 1-500)
        run_sql "INSERT INTO schema_migrations (migration_name, success, error_message) VALUES ('$migration_name', false, E'$ERROR_MSG') ON CONFLICT (migration_name) DO UPDATE SET executed_at = NOW(), success = false, error_message = E'$ERROR_MSG';"
        echo -e "  ${RED}✗ Failed${NC}"
        echo -e "  ${RED}Error: $(cat /tmp/migration_error.log | head -5)${NC}"
        ((ERROR_COUNT++))

        # Exit on first error unless forced
        if [ "$FORCE_RUN" != true ]; then
            echo ""
            echo -e "${RED}Migration failed. Stopping execution.${NC}"
            echo -e "${RED}Use --force to continue despite errors${NC}"
            exit 1
        fi
    fi
    echo ""
done

# Cleanup
rm -f /tmp/migration_error.log

# Summary
echo "================================================"
echo -e "${GREEN}Migration Summary${NC}"
echo "  Total migrations: $TOTAL_MIGRATIONS"
echo -e "  ${GREEN}Applied: $APPLIED_COUNT${NC}"
echo -e "  ${YELLOW}Skipped: $SKIPPED_COUNT${NC}"
if [ $ERROR_COUNT -gt 0 ]; then
    echo -e "  ${RED}Failed: $ERROR_COUNT${NC}"
fi
echo ""

# Show migration status
echo -e "${BLUE}Current migration status:${NC}"
run_sql "SELECT
    migration_name,
    TO_CHAR(executed_at, 'YYYY-MM-DD HH24:MI:SS') as executed,
    CASE WHEN success THEN 'SUCCESS' ELSE 'FAILED' END as status
FROM schema_migrations
ORDER BY executed_at DESC
LIMIT 10;" | column -t -s '|'

echo ""
if [ $ERROR_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ All migrations completed successfully!${NC}"
else
    echo -e "${RED}⚠ Some migrations failed. Check the logs above for details.${NC}"
    exit 1
fi