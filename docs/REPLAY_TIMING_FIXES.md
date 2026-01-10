# Replay vs Backtest Timing Fixes

## Problem Summary

When running the same strategy (coin_toss) on the same data (2025-12-04), backtest and replay produced very different results:

- **Backtest**: 5 trades, first entry at 14:30
- **Replay**: 1 trade, first entry at 14:35

**Root Cause**: Replay was missing the first 4 minutes of data (14:30-14:34), causing different entry times, different contracts, and different market conditions.

## Changes Made

> **Note**: A critical double-processing bug was also discovered and fixed during this work. See [REDIS_DOUBLE_PROCESSING_BUG.md](REDIS_DOUBLE_PROCESSING_BUG.md) for details.

### 1. Reduced Batching Delay in RedisDataFeed

**File**: `src/live_trading_service/redis_data_feed.py:79-82`

**Change**: Reduced batch size and interval to process bars faster

```python
# BEFORE
self._callback_batch_size = 50  # Flush after this many bars
self._callback_batch_interval_ms = 500  # Or after this many ms

# AFTER
self._callback_batch_size = 5  # Flush after this many bars (reduced from 50)
self._callback_batch_interval_ms = 100  # Or after this many ms (reduced from 500)
```

**Impact**: Callbacks are triggered 10x faster, reducing initial delay from 500ms+ to 100ms max.

### 2. Added Debugging Logs to Engine Deduplication Logic

**File**: `src/live_trading_service/engine.py:452-506`

**Changes**:
- Log first 5 unique timestamps processed
- Track and log duplicate bars skipped
- Add batch summary with counts

**Example Output**:
```
Processing timestamp 1: 2025-12-04 14:30:00+00:00
Processing timestamp 2: 2025-12-04 14:31:00+00:00
Batch processed: 2 unique timestamps, 398 duplicates skipped, 400 total bars
```

**Impact**: Makes it easy to see exactly when bars are being processed and if any are being skipped.

### 3. Enhanced Batch Flush Logging

**File**: `src/live_trading_service/redis_data_feed.py:323-350`

**Changes**:
- Log batch size and first timestamp when flushing
- Show unique timestamp count

**Example Output**:
```
Flushing batch: 400 bars, 1 unique timestamps (first: 2025-12-04 14:30:00+00:00)
```

**Impact**: Confirms when Redis feed sends bars to the engine and what timestamps are included.

### 4. More Verbose Replay Publisher Logging

**File**: `src/replay_service/publisher.py:139-147`

**Changes**:
- Log first 10 timestamps (instead of first 1)
- Shows exactly when replay service publishes each timestamp

**Example Output**:
```
[1/391] 2025-12-04 14:30:00+00:00 | Published 400 bars | Total: 400 | Elapsed: 0.1s
[2/391] 2025-12-04 14:31:00+00:00 | Published 400 bars | Total: 800 | Elapsed: 0.2s
```

**Impact**: Confirms replay service is publishing 14:30 data immediately.

## Testing

### Diagnostic Script

**File**: `scripts/diagnose_replay_vs_backtest.py`

Compares backtest trades CSV with replay logs to identify:
- Timing differences
- Trade count mismatches
- Missing data windows
- Batching delays

**Usage**:
```bash
python scripts/diagnose_replay_vs_backtest.py \
  --backtest-csv reports/backtests/coin_toss_trades_20260109_181246.csv \
  --replay-log logs/live_trading_strategy_executor/live_trading_strategy_executor_20260109.log
```

### Test Script

**File**: `scripts/test_replay_timing.sh`

Automated test that:
1. Runs replay service for 2025-12-04
2. Starts live trading engine in replay mode
3. Waits 30 seconds for processing
4. Analyzes logs to verify 14:30 start time

**Usage**:
```bash
bash scripts/test_replay_timing.sh
```

## Expected Results

After these fixes:

1. **First bar processed**: Should be `2025-12-04 14:30:00` (not 14:34)
2. **Batch flush delay**: Should be < 100ms (not 500ms+)
3. **Trade count**: Should match backtest (5 trades)
4. **Entry times**: Should match backtest entry times

## Verification Steps

1. Run backtest:
   ```bash
   python scripts/run_backtest.py --strategy coin_toss --start-date 2025-12-04 --end-date 2025-12-04
   ```

2. Run replay:
   ```bash
   python scripts/run_replay.py --date 2025-12-04 --speed 0
   python scripts/run_live_trading.py
   ```

3. Compare results:
   ```bash
   python scripts/diagnose_replay_vs_backtest.py
   ```

4. Check logs for:
   - First timestamp processed: `grep "Processing timestamp 1:" logs/live_trading_strategy_executor/*.log`
   - Batch flushes: `grep "Flushing batch:" logs/live_trading_strategy_executor/*.log`
   - Replay publishing: `grep "\[1/391\]" logs/replay/*.log`

## Performance Considerations

**Batch Size Reduction**:
- **Before**: 50 bars = ~1 second worth of data at 1-min bars
- **After**: 5 bars = ~5 seconds worth of data

The reduced batch size increases callback frequency but ensures faster initial processing. For live trading:
- Still batches to avoid overwhelming the system
- 100ms interval is fast enough for 1-minute bars
- Can be tuned if needed (increase for slower strategies)

**Memory Impact**: Minimal - still using bounded deques for storage

**CPU Impact**: Slight increase in callback frequency, but negligible for 1-min bars

## Troubleshooting

### If first bar is still at 14:34:

1. Check Redis is receiving 14:30 data:
   ```bash
   grep "14:30" logs/replay/*.log
   ```

2. Check batch flush happens immediately:
   ```bash
   grep "Flushing batch" logs/live_trading_strategy_executor/*.log | head -1
   ```

3. Verify batch settings:
   ```bash
   grep "_callback_batch" src/live_trading_service/redis_data_feed.py
   ```

### If trade count doesn't match:

1. Check if all timestamps are processed:
   ```bash
   grep "Processing timestamp" logs/live_trading_strategy_executor/*.log | wc -l
   ```

2. Look for errors:
   ```bash
   grep "ERROR\|WARNING" logs/live_trading_strategy_executor/*.log
   ```

3. Run diagnostic for detailed analysis:
   ```bash
   python scripts/diagnose_replay_vs_backtest.py
   ```

## Future Improvements

1. **Dynamic batching**: Adjust batch size based on bar arrival rate
2. **Timestamp alignment**: Ensure engine always starts at first available timestamp
3. **State validation**: Add checks to verify replay state matches backtest state
4. **Automated tests**: Add unit tests for timing behavior
5. **Configuration**: Make batch settings configurable via config file

## Related Files

- `src/live_trading_service/redis_data_feed.py` - Data feed batching logic
- `src/live_trading_service/engine.py` - Strategy execution and deduplication
- `src/replay_service/publisher.py` - Replay data publishing
- `scripts/diagnose_replay_vs_backtest.py` - Diagnostic tool
- `scripts/test_replay_timing.sh` - Automated testing

## References

- Original issue identified: 2026-01-09
- Diagnostic script created: 2026-01-09
- Fixes implemented: 2026-01-09
