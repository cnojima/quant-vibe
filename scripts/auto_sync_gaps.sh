#!/bin/bash
# Auto-sync data gaps between remote and local TimescaleDB
#
# This script:
# 1. Analyzes data gaps
# 2. Generates sync commands
# 3. Optionally executes them automatically
#
# Usage:
#   ./scripts/auto_sync_gaps.sh                 # Interactive mode (shows commands, asks for confirmation)
#   ./scripts/auto_sync_gaps.sh --auto          # Automatic mode (runs all sync commands)
#   ./scripts/auto_sync_gaps.sh --quick         # Quick scan (last 30 days only)
#   ./scripts/auto_sync_gaps.sh --since 2025-12-01 --until 2025-12-31

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse arguments
AUTO_MODE=false
ANALYZE_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --auto)
            AUTO_MODE=true
            shift
            ;;
        *)
            ANALYZE_ARGS+=("$1")
            shift
            ;;
    esac
done

echo "========================================================================"
echo "AUTOMATIC GAP SYNC WORKFLOW"
echo "========================================================================"
echo ""

# Step 1: Analyze gaps and generate sync commands
echo -e "${YELLOW}Step 1: Analyzing data gaps...${NC}"
SYNC_SCRIPT="/tmp/sync_gaps_$(date +%s).sh"
python scripts/analyze_data_gaps.py "${ANALYZE_ARGS[@]}" --generate-sync-commands --output "$SYNC_SCRIPT"

# Check if sync script was created and has commands
if [ ! -f "$SYNC_SCRIPT" ] || [ ! -s "$SYNC_SCRIPT" ]; then
    echo -e "${GREEN}✅ No gaps found! Local database is up to date.${NC}"
    exit 0
fi

# Count number of sync commands (excluding comments and shebang)
NUM_COMMANDS=$(grep -c "^python scripts/sync_moirae.py" "$SYNC_SCRIPT" || true)

if [ "$NUM_COMMANDS" -eq 0 ]; then
    echo -e "${GREEN}✅ No gaps found! Local database is up to date.${NC}"
    rm "$SYNC_SCRIPT"
    exit 0
fi

echo ""
echo -e "${YELLOW}Step 2: Found $NUM_COMMANDS sync operations${NC}"
echo ""

# Show generated commands
echo "Generated sync commands:"
echo "----------------------------------------"
grep "^python scripts/sync_moirae.py" "$SYNC_SCRIPT" || true
echo "----------------------------------------"
echo ""

# Step 3: Execute or prompt
if [ "$AUTO_MODE" = true ]; then
    echo -e "${YELLOW}Step 3: Executing sync commands (auto mode)...${NC}"
    chmod +x "$SYNC_SCRIPT"
    "$SYNC_SCRIPT"
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ All sync operations completed successfully!${NC}"
    else
        echo ""
        echo -e "${RED}❌ Sync failed with exit code $EXIT_CODE${NC}"
        exit $EXIT_CODE
    fi
else
    echo -e "${YELLOW}Step 3: Ready to execute sync commands${NC}"
    echo ""
    read -p "Execute these sync commands? (y/n): " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        chmod +x "$SYNC_SCRIPT"
        "$SYNC_SCRIPT"
        EXIT_CODE=$?

        if [ $EXIT_CODE -eq 0 ]; then
            echo ""
            echo -e "${GREEN}✅ All sync operations completed successfully!${NC}"
        else
            echo ""
            echo -e "${RED}❌ Sync failed with exit code $EXIT_CODE${NC}"
            exit $EXIT_CODE
        fi
    else
        echo ""
        echo "Sync cancelled. Commands saved to: $SYNC_SCRIPT"
        echo "You can run them manually with: $SYNC_SCRIPT"
        exit 0
    fi
fi

# Cleanup
rm "$SYNC_SCRIPT"

echo ""
echo "========================================================================"
echo "SYNC COMPLETE"
echo "========================================================================"
