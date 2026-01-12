#!/bin/bash

# Migration runner script for live_orders table
# Usage: ./run_migration.sh [local|remote]

set -e  # Exit on error

# Load environment variables
if [ -f "../../.env" ]; then
    export $(grep -v '^#' ../../.env | xargs)
fi

# Determine which database to use
DB_PROFILE="${1:-local}"

if [ "$DB_PROFILE" = "remote" ]; then
    echo "Using REMOTE database..."
    DB_HOST="${REMOTE_TIMESCALE_HOST:-localhost}"
    DB_PORT="${REMOTE_TIMESCALE_PORT:-5432}"
    DB_NAME="${REMOTE_TIMESCALE_DB:-options_data}"
    DB_USER="${REMOTE_TIMESCALE_USER:-quantvibe}"
    DB_PASSWORD="${REMOTE_TIMESCALE_PASSWORD:-quantvibe_dev}"
else
    echo "Using LOCAL database..."
    DB_HOST="${TIMESCALE_HOST:-localhost}"
    DB_PORT="${TIMESCALE_PORT:-5432}"
    DB_NAME="${TIMESCALE_DB:-options_data}"
    DB_USER="${TIMESCALE_USER:-quantvibe}"
    DB_PASSWORD="${TIMESCALE_PASSWORD:-quantvibe_dev}"
fi

echo "Database: $DB_HOST:$DB_PORT/$DB_NAME"
echo "User: $DB_USER"
echo ""
echo "Running migration: add_action_type_to_orders.sql"
echo "================================================"
echo ""

# Run the migration
PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -f add_action_type_to_orders.sql

echo ""
echo "Migration completed successfully!"
echo ""
echo "Verifying column exists..."
PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -c "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'live_orders' AND column_name = 'action_type';"

echo ""
echo "Done!"
