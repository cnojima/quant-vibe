#!/bin/bash
# Test replay timing fixes
# This script runs a replay and checks if the timing issues are resolved

echo "========================================================================"
echo "Testing Replay Timing Fixes"
echo "========================================================================"
echo ""

# Clean up old logs
echo "1. Cleaning up old test logs..."
rm -f logs/live_trading_strategy_executor/live_trading_strategy_executor_$(date +%Y%m%d).log
rm -f logs/replay/replay_$(date +%Y%m%d).log

echo "   ✓ Old logs removed"
echo ""

# Start replay service in background
echo "2. Starting replay service (2025-12-04)..."
python scripts/run_replay.py --date 2025-12-04 --speed 0 > /tmp/replay_output.log 2>&1 &
REPLAY_PID=$!

# Wait for replay to start publishing
sleep 2

# Start live trading engine (will consume replay data)
echo "3. Starting live trading engine in replay mode..."
python scripts/run_live_trading.py > /tmp/live_trading_output.log 2>&1 &
LIVE_PID=$!

# Wait for processing
echo "4. Waiting for replay to complete (30 seconds)..."
sleep 30

# Stop services
echo "5. Stopping services..."
kill $LIVE_PID 2>/dev/null || true
kill $REPLAY_PID 2>/dev/null || true

sleep 2

echo "   ✓ Services stopped"
echo ""

# Analyze results
echo "6. Analyzing results..."
echo ""

# Check first timestamp processed
FIRST_BAR=$(grep "Processing timestamp 1:" logs/live_trading_strategy_executor/live_trading_strategy_executor_$(date +%Y%m%d).log | head -1)

if [ -z "$FIRST_BAR" ]; then
    echo "   ❌ ERROR: No timestamps processed in live trading logs"
    exit 1
fi

echo "   First timestamp processed:"
echo "   $FIRST_BAR"
echo ""

# Check if it's 14:30 (the correct start time)
if echo "$FIRST_BAR" | grep -q "14:30:00"; then
    echo "   ✅ SUCCESS: First bar is at 14:30 (correct!)"
elif echo "$FIRST_BAR" | grep -q "14:34:00"; then
    echo "   ❌ FAIL: First bar is at 14:34 (still has 4-minute delay)"
else
    echo "   ⚠️  WARNING: First bar is at unexpected time"
fi

echo ""

# Check batch flush logs
FIRST_FLUSH=$(grep "Flushing batch:" logs/live_trading_strategy_executor/live_trading_strategy_executor_$(date +%Y%m%d).log | head -1)

if [ -n "$FIRST_FLUSH" ]; then
    echo "   First batch flush:"
    echo "   $FIRST_FLUSH"
else
    echo "   ⚠️  No batch flush logs found"
fi

echo ""
echo "========================================================================"
echo "Test Complete"
echo "========================================================================"
echo ""
echo "To view detailed logs:"
echo "  Replay:       logs/replay/replay_$(date +%Y%m%d).log"
echo "  Live Trading: logs/live_trading_strategy_executor/live_trading_strategy_executor_$(date +%Y%m%d).log"
echo ""
echo "To run diagnostic:"
echo "  python scripts/diagnose_replay_vs_backtest.py"
