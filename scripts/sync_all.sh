#!/bin/bash
#
# Sync all data from remote to local and refresh continuous aggregates
#
# Usage: ./scripts/sync_all.sh [--since 2026-01-01]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Load .env file (handle inline comments)
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source <(grep -v '^#' "$PROJECT_DIR/.env" | sed 's/#.*//' | sed 's/[[:space:]]*$//')
    set +a
fi

# DB connection settings
PGHOST="${TIMESCALE_HOST:-localhost}"
PGPORT="${TIMESCALE_PORT:-5432}"
PGDATABASE="${TIMESCALE_DB:-options_data}"
PGUSER="${TIMESCALE_USER:-quantvibe}"
export PGPASSWORD="${TIMESCALE_PASSWORD:-quantvibe_dev}"

# Parse arguments
SINCE_DATE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --since)
            SINCE_DATE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--since YYYY-MM-DD]"
            echo ""
            echo "Syncs options and underlying data from remote, then refreshes continuous aggregates."
            echo ""
            echo "Options:"
            echo "  --since YYYY-MM-DD    Start date for sync (auto-detected if not provided)"
            echo "  -h, --help            Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Auto-detect since date if not provided
if [ -z "$SINCE_DATE" ]; then
    echo "Auto-detecting sync start date from local database..."

    # Get max timestamp from underlying_bars
    UNDERLYING_MAX=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -A -c \
        "SELECT COALESCE(MAX(timestamp)::date, CURRENT_DATE - INTERVAL '7 days')::date FROM underlying_bars;")

    # Get max timestamp from options_bars
    OPTIONS_MAX=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -A -c \
        "SELECT COALESCE(MAX(timestamp)::date, CURRENT_DATE - INTERVAL '7 days')::date FROM options_bars;")

    echo "  Last underlying_bars: $UNDERLYING_MAX"
    echo "  Last options_bars:    $OPTIONS_MAX"

    # Use the earlier of the two dates
    SINCE_DATE=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -A -c \
        "SELECT LEAST('$UNDERLYING_MAX'::date, '$OPTIONS_MAX'::date);")

    echo "  Using earlier date:   $SINCE_DATE"
    echo ""
fi

# Get today's date
TODAY=$(date +%Y-%m-%d)

echo "========================================================================"
echo "FULL DATA SYNC"
echo "========================================================================"
echo "Since: $SINCE_DATE"
echo "Until: $TODAY"
echo ""

# Activate virtual environment
cd "$PROJECT_DIR"
source venv/bin/activate

# Step 1: Sync options data
echo ""
echo "Step 1: Syncing options data (moirae)..."
echo "------------------------------------------------------------------------"
python scripts/sync_moirae.py --since "$SINCE_DATE"

# Step 2: Sync underlying data
echo ""
echo "Step 2: Syncing underlying data..."
echo "------------------------------------------------------------------------"
python scripts/sync_underlying.py --since "$SINCE_DATE"

# Step 3: Refresh continuous aggregates
echo ""
echo "Step 3: Refreshing continuous aggregates..."
echo "------------------------------------------------------------------------"

echo "Connecting to $PGUSER@$PGHOST:$PGPORT/$PGDATABASE"
echo ""

# Refresh all continuous aggregates
psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" <<EOF
-- Refresh underlying continuous aggregates
CALL refresh_continuous_aggregate('underlying_bars_5min', '$SINCE_DATE', '$TODAY');
CALL refresh_continuous_aggregate('underlying_bars_15min', '$SINCE_DATE', '$TODAY');
CALL refresh_continuous_aggregate('underlying_bars_1hour', '$SINCE_DATE', '$TODAY');
CALL refresh_continuous_aggregate('underlying_bars_daily', '$SINCE_DATE', '$TODAY');

-- Refresh options continuous aggregates
CALL refresh_continuous_aggregate('options_bars_5min', '$SINCE_DATE', '$TODAY');
CALL refresh_continuous_aggregate('options_bars_15min', '$SINCE_DATE', '$TODAY');
CALL refresh_continuous_aggregate('options_bars_1hour', '$SINCE_DATE', '$TODAY');
CALL refresh_continuous_aggregate('options_bars_daily', '$SINCE_DATE', '$TODAY');
EOF

echo ""
echo "========================================================================"
echo "SYNC COMPLETE"
echo "========================================================================"
