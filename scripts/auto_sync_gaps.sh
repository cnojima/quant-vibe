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
TIMESTAMP=$(date +%s)
SYNC_SCRIPT_BASE="/tmp/sync_gaps_${TIMESTAMP}"
python scripts/analyze_data_gaps.py "${ANALYZE_ARGS[@]}" --generate-sync-commands --output "${SYNC_SCRIPT_BASE}.sh"

# Check for generated sync scripts (both options and underlying)
OPTIONS_SYNC="${SYNC_SCRIPT_BASE}_options.sh"
UNDERLYING_SYNC="${SYNC_SCRIPT_BASE}_underlying.sh"
COMBINED_SYNC="${SYNC_SCRIPT_BASE}.sh"

# Determine which sync scripts exist
HAS_OPTIONS=false
HAS_UNDERLYING=false
TOTAL_COMMANDS=0

if [ -f "$OPTIONS_SYNC" ] && [ -s "$OPTIONS_SYNC" ]; then
    HAS_OPTIONS=true
    OPTIONS_COUNT=$(grep -c "^python scripts/sync_moirae.py" "$OPTIONS_SYNC" || true)
    TOTAL_COMMANDS=$((TOTAL_COMMANDS + OPTIONS_COUNT))
fi

if [ -f "$UNDERLYING_SYNC" ] && [ -s "$UNDERLYING_SYNC" ]; then
    HAS_UNDERLYING=true
    UNDERLYING_COUNT=$(grep -c "^python scripts/sync_underlying.py" "$UNDERLYING_SYNC" || true)
    TOTAL_COMMANDS=$((TOTAL_COMMANDS + UNDERLYING_COUNT))
fi

# Fallback to combined script if separate scripts don't exist
if [ "$HAS_OPTIONS" = false ] && [ "$HAS_UNDERLYING" = false ] && [ -f "$COMBINED_SYNC" ] && [ -s "$COMBINED_SYNC" ]; then
    COMBINED_COUNT=$(grep -c "^python scripts/sync" "$COMBINED_SYNC" || true)
    TOTAL_COMMANDS=$COMBINED_COUNT
fi

# Check if any gaps found
if [ $TOTAL_COMMANDS -eq 0 ]; then
    echo -e "${GREEN}✅ No gaps found! Local database is up to date.${NC}"
    # Clean up any generated files
    rm -f "$OPTIONS_SYNC" "$UNDERLYING_SYNC" "$COMBINED_SYNC"
    exit 0
fi

echo ""
echo -e "${YELLOW}Step 2: Found $TOTAL_COMMANDS sync operations${NC}"
echo ""

# Show generated commands
echo "Generated sync commands:"
echo "----------------------------------------"
if [ "$HAS_OPTIONS" = true ]; then
    echo "# OPTIONS_BARS:"
    grep "^python scripts/sync_moirae.py" "$OPTIONS_SYNC" || true
fi
if [ "$HAS_UNDERLYING" = true ]; then
    echo "# UNDERLYING_BARS:"
    grep "^python scripts/sync_underlying.py" "$UNDERLYING_SYNC" || true
fi
if [ "$HAS_OPTIONS" = false ] && [ "$HAS_UNDERLYING" = false ]; then
    grep "^python scripts/sync" "$COMBINED_SYNC" || true
fi
echo "----------------------------------------"
echo ""

# Step 3: Execute or prompt
execute_sync_scripts() {
    local failed=false

    # Execute options sync if exists
    if [ "$HAS_OPTIONS" = true ]; then
        echo -e "${YELLOW}Syncing options_bars...${NC}"
        chmod +x "$OPTIONS_SYNC"
        "$OPTIONS_SYNC"
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Options sync failed${NC}"
            failed=true
        else
            echo -e "${GREEN}✅ Options sync completed${NC}"
        fi
        echo ""
    fi

    # Execute underlying sync if exists
    if [ "$HAS_UNDERLYING" = true ]; then
        echo -e "${YELLOW}Syncing underlying_bars...${NC}"
        chmod +x "$UNDERLYING_SYNC"
        "$UNDERLYING_SYNC"
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Underlying sync failed${NC}"
            failed=true
        else
            echo -e "${GREEN}✅ Underlying sync completed${NC}"
        fi
        echo ""
    fi

    # Execute combined script if no separate scripts
    if [ "$HAS_OPTIONS" = false ] && [ "$HAS_UNDERLYING" = false ] && [ -f "$COMBINED_SYNC" ]; then
        chmod +x "$COMBINED_SYNC"
        "$COMBINED_SYNC"
        if [ $? -ne 0 ]; then
            failed=true
        fi
    fi

    if [ "$failed" = true ]; then
        return 1
    fi
    return 0
}

if [ "$AUTO_MODE" = true ]; then
    echo -e "${YELLOW}Step 3: Executing sync commands (auto mode)...${NC}"
    execute_sync_scripts
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ All sync operations completed successfully!${NC}"
    else
        echo ""
        echo -e "${RED}❌ Some sync operations failed${NC}"
        exit $EXIT_CODE
    fi
else
    echo -e "${YELLOW}Step 3: Ready to execute sync commands${NC}"
    echo ""
    read -p "Execute these sync commands? (y/n): " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        execute_sync_scripts
        EXIT_CODE=$?

        if [ $EXIT_CODE -eq 0 ]; then
            echo ""
            echo -e "${GREEN}✅ All sync operations completed successfully!${NC}"
        else
            echo ""
            echo -e "${RED}❌ Some sync operations failed${NC}"
            exit $EXIT_CODE
        fi
    else
        echo ""
        echo "Sync cancelled. Commands saved to:"
        [ "$HAS_OPTIONS" = true ] && echo "  Options: $OPTIONS_SYNC"
        [ "$HAS_UNDERLYING" = true ] && echo "  Underlying: $UNDERLYING_SYNC"
        exit 0
    fi
fi

# Cleanup
rm -f "$OPTIONS_SYNC" "$UNDERLYING_SYNC" "$COMBINED_SYNC"

echo ""
echo "========================================================================"
echo "SYNC COMPLETE"
echo "========================================================================"
