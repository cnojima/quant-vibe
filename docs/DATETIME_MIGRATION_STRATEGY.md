# DateTime Migration Strategy

## Problem

Found 149 instances of naive datetime usage:
- `datetime.utcnow()`: 42 instances
- `datetime.now()`: 107 instances

## Critical vs Non-Critical Usage

### ✅ MUST Fix (Critical - Data Persistence)

**Criteria**: Datetimes that are:
1. Stored in database
2. Published to Redis
3. Used in DataFrame indexes
4. Compared across timezone boundaries
5. Used for business logic decisions

**Priority Files** (streaming, messaging, database):
- `src/streaming_service/` - All files (publishes to Redis/DB)
- `src/quant_vibe/messaging/` - All files (Redis pub/sub)
- `src/quant_vibe/data/timescale_store.py` - Database inserts
- `src/live_trading_service/` - All files (live trading state)
- `src/quant_vibe/backtesting/` - Backtest results storage

### ⚠️ Consider Fixing (Medium Priority)

**Criteria**: Datetimes used for:
1. Logging/monitoring (could cause confusion)
2. State tracking (uptime, heartbeats)
3. Cache expiration
4. Token refresh timing

**Files**:
- `src/watcher_service/` - Heartbeat/monitoring
- `src/token_service/` - Token refresh
- `src/admin_ui/backend/` - API responses

### ✋ Can Skip (Low Priority - Display Only)

**Criteria**: Datetimes used ONLY for:
1. Console print statements (display only)
2. Log message formatting (non-structured)
3. Temporary debug output

**Example**:
```python
# ✋ OK to keep (display only)
now = datetime.now()
print(f"Processing started at {now.strftime('%Y-%m-%d %H:%M:%S')}")

# ❌ MUST fix (stored to DB)
timestamp = datetime.now()
cursor.execute("INSERT INTO trades (timestamp, ...) VALUES (%s, ...)", (timestamp,))
```

## Migration Plan

### Phase 1: Critical Data Paths (Week 1)

**Target**: 100% fix rate for data persistence

1. **Streaming Service** (`src/streaming_service/`)
   - `aggregator.py` - Bar aggregation timestamps
   - `underlying_aggregator.py` - Bar aggregation timestamps
   - `service.py` - Heartbeat and state timestamps
   - `broker.py` - Redis message timestamps

2. **Messaging** (`src/quant_vibe/messaging/`)
   - `broker.py` - Message envelope timestamps

3. **Database** (`src/quant_vibe/data/`)
   - `timescale_store.py` - Insert timestamps
   - `live_market_data.py` - DataFrame indexes

4. **Live Trading** (`src/live_trading_service/`)
   - `engine.py` - State timestamps
   - `order_manager.py` - Order timestamps
   - `position_manager.py` - Position timestamps
   - `state_store.py` - Database persistence

**Deliverables**:
- All critical data paths use `now_utc()`
- Schema validation tests pass
- No naive timestamps in Redis messages
- No naive timestamps in database inserts

### Phase 2: Monitoring & Caching (Week 2)

**Target**: Consistent timezone handling for operational metrics

1. **Watcher Service** (`src/watcher_service/`)
   - Heartbeat timestamps
   - Alert timestamps
   - Monitoring metrics

2. **Token Service** (`src/token_service/`)
   - Token expiration tracking
   - Refresh timing

3. **Admin UI** (`src/admin_ui/backend/`)
   - API response timestamps
   - Status timestamps

### Phase 3: Logging & Display (Week 3)

**Target**: Full UTC consistency (optional)

1. Review all remaining `datetime.now()` for logging
2. Decide: UTC for consistency or keep local time for human readability?
3. Document decision in style guide

## Automated Migration Approach

### Step 1: Identify Usage Context

For each `datetime.now()` or `datetime.utcnow()`, categorize:

```python
# Category 1: Database insert (CRITICAL)
timestamp = datetime.now()
cursor.execute("INSERT INTO ... (timestamp) VALUES (%s)", (timestamp,))

# Category 2: Redis publish (CRITICAL)
data = {"timestamp": datetime.utcnow().isoformat()}
redis.publish("topic", json.dumps(data))

# Category 3: DataFrame index (CRITICAL)
df.loc[datetime.now()] = values

# Category 4: State tracking (MEDIUM)
self.last_heartbeat = datetime.utcnow()

# Category 5: Display only (LOW)
print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
```

### Step 2: Manual Review + Automated Fix

1. Run automated migration on **critical files only**
2. Manual review for **medium priority files**
3. Document exceptions for **low priority files**

### Step 3: Add Guards

1. Pre-commit hook to prevent new naive datetime usage in critical paths
2. Linter rule to warn on `datetime.utcnow()` usage
3. Type hints to enforce `datetime` with `tzinfo`

## Implementation Commands

### Dry Run (Preview Changes)
```bash
python scripts/migrate_to_utc_timestamps.py --dry-run
```

### Migrate Critical Files Only
```bash
# Edit migration script to target only critical files
python scripts/migrate_to_utc_timestamps.py --critical-only
```

### Check for Remaining Issues
```bash
python scripts/migrate_to_utc_timestamps.py --check
```

### Run Tests
```bash
pytest tests/integration/test_schema_consistency.py -v
pytest tests/ -v
```

## Manual Migration Pattern

For files requiring manual review:

**Before**:
```python
from datetime import datetime

class BarAggregator:
    def __init__(self):
        self.last_flush_time = datetime.now()  # ❌ Naive

    def flush(self):
        elapsed = (datetime.now() - self.last_flush_time).total_seconds()

        # Timestamp stored to Redis/DB
        bar_data = {
            'timestamp': datetime.utcnow().isoformat(),  # ❌ Naive UTC
            'close': self.close,
        }
```

**After**:
```python
from datetime import datetime
from quant_vibe.utils import now_utc  # ✅ Import utility

class BarAggregator:
    def __init__(self):
        self.last_flush_time = now_utc()  # ✅ UTC-aware

    def flush(self):
        elapsed = (now_utc() - self.last_flush_time).total_seconds()

        # Timestamp stored to Redis/DB
        bar_data = {
            'timestamp': now_utc().isoformat(),  # ✅ UTC-aware
            'close': self.close,
        }
```

## Pre-Commit Hook

Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: no-naive-datetimes
        name: Prevent naive datetime usage in critical paths
        entry: hooks/check_naive_datetimes.sh
        language: script
        files: ^src/(streaming_service|quant_vibe/messaging|quant_vibe/data|live_trading_service)/.*\.py$
```

Script: `hooks/check_naive_datetimes.sh`:
```bash
#!/bin/bash
# Check for naive datetime usage in critical files

if grep -n "datetime\.utcnow()" "$@"; then
    echo "ERROR: Found datetime.utcnow() - use now_utc() instead"
    exit 1
fi

if grep -n "datetime\.now()" "$@" | grep -v "strftime\|# display"; then
    echo "WARNING: Found datetime.now() - verify it's not used for data persistence"
    echo "Use now_utc() for timestamps stored in DB/Redis"
    exit 1
fi

exit 0
```

## Success Criteria

### Phase 1 Complete
- [ ] Zero `datetime.utcnow()` in streaming service
- [ ] Zero `datetime.now()` in Redis message publishing
- [ ] Zero `datetime.now()` in database inserts
- [ ] Zero `datetime.now()` in DataFrame indexes
- [ ] Schema validation tests pass
- [ ] Integration tests pass

### Phase 2 Complete
- [ ] Zero `datetime.utcnow()` in watcher service
- [ ] Zero `datetime.utcnow()` in token service
- [ ] Monitoring timestamps consistent (all UTC)

### Phase 3 Complete
- [ ] Pre-commit hook installed
- [ ] Documentation updated
- [ ] All developers aware of `now_utc()` utility

## Rollback Plan

If issues arise after migration:

1. **Revert commits**: `git revert <commit-hash>`
2. **Check database** for timezone issues:
   ```sql
   SELECT * FROM options_bars WHERE timestamp::text LIKE '%+%' LIMIT 10;
   ```
3. **Verify Redis messages**:
   ```bash
   redis-cli SUBSCRIBE "streaming.options_bars"
   # Check timestamp format
   ```
4. **Run backtest** on known-good data to verify results unchanged

## Testing Strategy

### Unit Tests
```python
def test_aggregator_uses_utc_aware_timestamps():
    """Verify BarAggregator uses UTC-aware timestamps"""
    from quant_vibe.utils import is_utc_aware
    from streaming_service.aggregator import BarAggregator

    agg = BarAggregator(...)

    # Verify last_flush_time is UTC-aware
    assert is_utc_aware(agg.last_flush_time)
```

### Integration Tests
```python
def test_redis_messages_have_utc_timestamps():
    """Verify Redis messages contain UTC-aware timestamps"""
    from quant_vibe.messaging import RedisMessageBroker
    from quant_vibe.utils import is_utc_aware
    import json

    # Subscribe to topic
    messages = []
    def callback(topic, data):
        messages.append(json.loads(data))

    broker = RedisMessageBroker()
    broker.subscribe(["streaming.options_bars"], callback)

    # Wait for message
    time.sleep(1)

    # Verify timestamp
    if messages:
        timestamp_str = messages[0]['timestamp']
        timestamp = datetime.fromisoformat(timestamp_str)
        assert is_utc_aware(timestamp)
```

## References

- Timestamp Utilities: `src/quant_vibe/utils/timestamp_utils.py`
- Schema Mapping: `docs/SCHEMA_MAPPING.md`
- UTC Verification: `docs/UTC_VERIFICATION_REPORT.md`
- Simplification Plan: `docs/SIMPLIFICATION_PLAN.md`

---

**Last Updated**: 2026-01-02
**Status**: Phase 1 Planning
**Next Action**: Run automated migration on critical files
