#!/bin/bash
# Run database migration
# Usage: ./scripts/run_migration.sh <migration_file>

set -e

MIGRATION_FILE=$1

if [ -z "$MIGRATION_FILE" ]; then
    echo "Usage: $0 <migration_file>"
    echo "Example: $0 scripts/migrations/004_add_strategy_name_to_trades.sql"
    exit 1
fi

if [ ! -f "$MIGRATION_FILE" ]; then
    echo "Error: Migration file not found: $MIGRATION_FILE"
    exit 1
fi

echo "============================================================================"
echo "Running migration: $MIGRATION_FILE"
echo "============================================================================"
echo ""

# Run migration
docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < "$MIGRATION_FILE"

echo ""
echo "============================================================================"
echo "Migration completed!"
echo "============================================================================"
