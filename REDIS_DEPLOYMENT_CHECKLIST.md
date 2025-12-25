# Redis Refactoring - Deployment Checklist

## Pre-Deployment Checks

### 1. Dependencies Installed ✓
```bash
# Verify Redis is installed in Python environment
python -c "import redis; print(f'Redis version: {redis.__version__}')"
# Expected: Redis version: 7.1.0 (or higher)

# Verify messaging module
python -c "from quant_vibe.messaging import RedisMessageBroker, Topic; print('✓ Messaging module OK')"
```

### 2. Docker Services Running ✓
```bash
# Start services
docker compose up -d redis timescaledb

# Verify status
docker compose ps
# Expected: Both containers "running"

# Test Redis
docker exec quant-vibe-redis redis-cli ping
# Expected: PONG

# Check Redis info
docker exec quant-vibe-redis redis-cli INFO server | grep redis_version
# Expected: redis_version:7.x.x
```

### 3. Environment Variables ✓
Ensure `.env` contains:
```bash
# Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Schwab API (for StreamingService)
SCHWAB_API_KEY=your_key
SCHWAB_API_SECRET=your_secret
SCHWAB_CALLBACK_URL=your_callback
SCHWAB_ACCOUNT_NUMBER=your_account

# TimescaleDB
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DB=options_data
TIMESCALE_USER=quantvibe
TIMESCALE_PASSWORD=quantvibe_dev
```

### 4. Configuration Files ✓
Verify configuration files are correct:

**config/live_trading.yaml:**
```yaml
engine:
  use_redis_feed: true  # ✓ Should be true
  paper_trading: true   # ✓ Start with paper trading

redis:
  host: null  # ✓ Will use REDIS_HOST env var
  port: null  # ✓ Will use REDIS_PORT env var
  db: null    # ✓ Will use REDIS_DB env var
```

## Deployment Steps

### Step 1: Test Redis Messaging ✓
```bash
python scripts/test_redis_messaging.py
```

**Expected Output:**
```
✅ SUCCESS: All messages received!
✅ SUCCESS: Correct topics received!
```

**If this fails:**
- Check Redis is running: `docker compose ps`
- Check Redis logs: `docker logs quant-vibe-redis`
- Verify environment variables in `.env`

### Step 2: Start StreamingService ✓
```bash
# Option 1: Run locally (development)
python scripts/stream_spxw_schwabdev.py

# Option 2: Run in Docker (production)
docker compose up streaming
```

**Expected Output:**
```
✓ Redis message broker connected
✓ Schwabdev client initialized
✓ Token manager initialized
✓ Bar aggregator initialized
SPXW OPTIONS STREAMING SERVICE
Started: 2025-12-25 ...
```

**Watch for:**
- ✅ "Redis message broker connected"
- ✅ "Schwabdev client initialized"
- ✅ No connection errors

**Monitor Redis activity:**
```bash
# In another terminal
docker exec quant-vibe-redis redis-cli monitor
# Should see PUBLISH commands when bars are created
```

### Step 3: Start LiveTradingEngine ✓
```bash
python scripts/run_live_trading.py
```

**Expected Output:**
```
Initializing Redis data feed...
✓ Redis data feed ready
ℹ️  Using StreamingService for market data
✓ Schwab client ready (order execution only)
✅ Engine is RUNNING
```

**Watch for:**
- ✅ "Redis data feed ready"
- ✅ "Using StreamingService for market data"
- ✅ NO "Starting schwabdev stream" (that should only be in StreamingService)

**Verify data reception:**
```bash
# Check logs for incoming bars
tail -f logs/live_trading/live_trading_*.log
# Should see "Received X new bars" messages
```

## Monitoring

### Check Service Health

**1. Redis Health:**
```bash
# Connection count
docker exec quant-vibe-redis redis-cli CLIENT LIST

# Memory usage
docker exec quant-vibe-redis redis-cli INFO memory | grep used_memory_human

# Pub/sub channels
docker exec quant-vibe-redis redis-cli PUBSUB CHANNELS
# Expected: streaming.options_bars, streaming.underlying_bars
```

**2. Service Logs:**
```bash
# StreamingService logs
tail -f logs/streaming/streaming_*.log

# LiveTradingEngine logs
tail -f logs/live_trading/live_trading_*.log
```

**3. Message Flow:**
```bash
# Monitor messages in real-time
docker exec quant-vibe-redis redis-cli MONITOR | grep PUBLISH
```

### Performance Metrics

**Message Latency:**
- StreamingService publishes every 60 seconds (1-minute bars)
- LiveTradingEngine should receive within 100ms
- Check logs for timestamp differences

**API Call Reduction:**
- Before: 2 Schwab websocket connections (StreamingService + LiveTradingEngine)
- After: 1 Schwab websocket connection (StreamingService only)
- **Reduction: 50% fewer API connections** ✅

**Memory Usage:**
- Redis: ~512MB max (configured in docker-compose)
- Check: `docker stats quant-vibe-redis`

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'redis'"
**Solution:**
```bash
# Rebuild Docker image
docker compose build streaming

# Or install locally
pip install -e .
```

### Issue: "Connection refused" to Redis
**Solution:**
```bash
# Check Redis is running
docker compose ps redis

# Restart if needed
docker compose restart redis

# Check logs
docker logs quant-vibe-redis
```

### Issue: LiveTradingEngine not receiving messages
**Solution:**
```bash
# 1. Verify StreamingService is publishing
docker exec quant-vibe-redis redis-cli MONITOR | grep PUBLISH

# 2. Check topic subscription
# In logs, look for: "Subscribed to streaming.options_bars"

# 3. Test messaging independently
python scripts/test_redis_messaging.py
```

### Issue: Duplicate Schwab connections
**Solution:**
```bash
# Verify live_trading.yaml has:
# engine:
#   use_redis_feed: true  # <-- Must be true

# Check logs for:
# "Using StreamingService for market data" ✅
# NOT: "Starting schwabdev stream" ❌
```

## Rollback Plan

If issues arise, rollback to direct streaming:

**1. Update config/live_trading.yaml:**
```yaml
engine:
  use_redis_feed: false  # <-- Set to false
```

**2. Restart LiveTradingEngine:**
```bash
# Stop current instance (Ctrl+C)
python scripts/run_live_trading.py
# Will now use direct Schwab connection (legacy mode)
```

**3. Verify:**
```bash
# Check logs for:
# "Starting schwabdev stream"  ✅ (in legacy mode)
# "Redis data feed ready" should NOT appear
```

## Success Criteria

✅ All tests passing:
- `python scripts/test_redis_messaging.py` → SUCCESS

✅ Services communicating:
- StreamingService publishes to Redis
- LiveTradingEngine receives from Redis
- No duplicate Schwab connections

✅ Performance improvements:
- 50% reduction in Schwab API connections
- Lower API rate limit usage
- Faster startup (no duplicate contract discovery)

✅ Monitoring working:
- Redis pub/sub channels visible
- Message flow observable via MONITOR
- Service logs show data flow

## Next Steps After Deployment

1. **Monitor for 24 hours** in paper trading mode
2. **Verify data integrity** (compare Redis data vs TimescaleDB)
3. **Load test** with multiple LiveTradingEngine instances
4. **Document metrics** (latency, throughput, error rates)
5. **Gradually migrate** production instances

## Support

- **Architecture docs**: See `REDIS_REFACTORING_SUMMARY.md`
- **Development guide**: See `CLAUDE.md`
- **Installation help**: See `INSTALLATION.md`
- **Test suite**: `scripts/test_redis_messaging.py`

---

**Last Updated**: December 25, 2025
**Status**: READY FOR DEPLOYMENT ✅
