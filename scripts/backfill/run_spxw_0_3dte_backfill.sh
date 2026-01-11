#!/bin/bash
#
# One-Time SPXW 0-3 DTE Backfill Script
#
# This script performs a complete backfill of SPXW options data from 2023-02-01
# to 2025-11-30 with the following strategy:
#
# - DTE Range: 0-3 days (short-term options)
# - Strike Selection: Dynamic ATM ± 5% with 50-point steps
# - Sampling: Weekly (Mondays only) to reduce data volume
# - Greeks: Disabled for faster initial backfill (run separately)
#
# Data Estimate (Weekly Sampling):
# - ~145 weeks × 3 expirations × ~26 contracts × 1,000 bars ≈ 11.3M bars
# - Runtime: ~12-15 hours
# - Storage: ~5-6 GB uncompressed, ~1-1.5 GB compressed
#
# Usage:
#   ./run_spxw_0_3dte_backfill.sh [dry-run]
#
# Examples:
#   ./run_spxw_0_3dte_backfill.sh          # Run full backfill
#   ./run_spxw_0_3dte_backfill.sh dry-run  # Estimate only (no actual backfill)
#

set -e  # Exit on error

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration
START_DATE="2024-01-23"
END_DATE="2025-11-30"
MAX_DTE=3
STRIKE_MODE="dynamic"
STRIKE_RANGE_PCT=5.0
STRIKE_STEP=50
SAMPLE_WEEKDAY="monday"  # Process only Mondays

# Activate virtual environment
echo "Activating virtual environment..."
source "$PROJECT_ROOT/venv/bin/activate"

# Display configuration
echo ""
echo "========================================================================"
echo "SPXW 0-3 DTE BACKFILL - ONE-TIME HISTORICAL BACKFILL"
echo "========================================================================"
echo ""
echo "Configuration:"
echo "  Date Range: $START_DATE to $END_DATE"
echo "  DTE Range: 0-$MAX_DTE days"
echo "  Strike Mode: $STRIKE_MODE (ATM ± ${STRIKE_RANGE_PCT}%)"
echo "  Strike Step: $STRIKE_STEP points"
echo "  Sampling: Every $SAMPLE_WEEKDAY"
echo "  Greeks: Disabled (run backfill_stream_greeks.py separately)"
echo ""

# Check if dry run
DRY_RUN_FLAG=""
if [ "$1" == "dry-run" ]; then
    echo "⚠️  DRY RUN MODE - Estimating data volume only"
    echo ""
    DRY_RUN_FLAG="--dry-run"
fi

# Run backfill
echo "Starting backfill..."
echo ""

python "$SCRIPT_DIR/backfill_spx_options.py" \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --max-dte $MAX_DTE \
    --strike-mode "$STRIKE_MODE" \
    --strike-range-pct $STRIKE_RANGE_PCT \
    --strike-step $STRIKE_STEP \
    --sample-weekday "$SAMPLE_WEEKDAY" \
    --no-greeks \
    $DRY_RUN_FLAG

# Check exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "========================================================================"
    echo "BACKFILL COMPLETED SUCCESSFULLY"
    echo "========================================================================"
    echo ""
    echo "Next Steps:"
    echo ""
    echo "1. Verify data quality:"
    echo "   SELECT DATE(timestamp), COUNT(*) FROM options_bars"
    echo "   WHERE timestamp >= '$START_DATE' GROUP BY DATE(timestamp) ORDER BY 1;"
    echo ""
    echo "2. Enrich with Greeks (OPTIONAL - takes several hours):"
    echo "   python scripts/backfill/backfill_stream_greeks.py \\"
    echo "     --start $START_DATE --end $END_DATE"
    echo ""
    echo "3. Refresh continuous aggregates:"
    echo "   See scripts/backfill/refresh_continuous_aggregates.sh"
    echo ""
else
    echo ""
    echo "========================================================================"
    echo "BACKFILL FAILED WITH EXIT CODE: $EXIT_CODE"
    echo "========================================================================"
    echo ""
    echo "Check the error messages above and try again."
    echo ""
    exit $EXIT_CODE
fi
