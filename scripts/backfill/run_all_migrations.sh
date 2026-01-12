#!/bin/bash
# Run all database migrations in order
# Usage: ./scripts/run_all_migrations.sh

set -e

MIGRATIONS_DIR="src/quant_vibe/data/schema/migrations"
CONTAINER="quant-vibe-timescaledb"
DB_USER="quantvibe"
DB_NAME="options_data"

echo "============================================================================"
echo "Running all database migrations"
echo "============================================================================"
echo ""

# Check if TimescaleDB container is running
if ! docker ps | grep -q "$CONTAINER"; then
    echo "Error: TimescaleDB container is not running"
    echo "Start it with: docker-compose up -d timescaledb"
    exit 1
fi

# List of migrations in order
MIGRATIONS=(
    "001_add_backtest_results.sql"
    "002_add_backtest_analysis.sql"
    "003_fix_live_events_hypertable.sql"
    "004_add_strategy_name_to_trades.sql"
)

# Run each migration
for migration in "${MIGRATIONS[@]}"; do
    migration_file="$MIGRATIONS_DIR/$migration"

    if [ -f "$migration_file" ]; then
        echo "Running: $migration"
        echo "----------------------------------------"
        docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$migration_file"
        echo ""
    else
        echo "Warning: Migration file not found: $migration_file"
        echo ""
    fi
done

echo "============================================================================"
echo "All migrations completed!"
echo "============================================================================"
echo ""
echo "Run this to verify:"
echo "  docker exec $CONTAINER psql -U $DB_USER -d $DB_NAME -c '\\dt'"