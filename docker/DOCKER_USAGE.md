# Docker Usage Guide

Quick reference for running quant-vibe services with Docker.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Infrastructure Layer                                       │
│  ├─ Redis (message broker)                                  │
│  └─ TimescaleDB (time-series data storage)                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  StreamingService                                           │
│  - Schwab API websocket (single connection)                 │
│  - Publishes to Redis topics                                │
│  - Persists to TimescaleDB                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓ Redis Pub/Sub
┌─────────────────────────────────────────────────────────────┐
│  LiveTradingService(s)                                      │
│  - Subscribes to Redis for market data                      │
│  - Executes trading strategies                              │
│  - Places orders via Schwab REST API                        │
│  - Multiple instances supported                             │
└─────────────────────────────────────────────────────────────┘
```

## Services

| Service | Container Name | Purpose | Dependencies |
|---------|---------------|---------|--------------|
| `redis` | quant-vibe-redis | Message broker for pub/sub | None |
| `timescaledb` | quant-vibe-timescaledb | Time-series database | None |
| `streaming` | quant-vibe-streaming | Market data streaming | redis, timescaledb |
| `live_trading` | quant-vibe-live-trading | Live trading engine | redis, timescaledb, streaming |

## Common Operations

### Start All Services

```bash
# Start infrastructure + streaming + live trading
docker compose up -d

# Start only infrastructure (for local development)
docker compose up -d redis timescaledb

# Start infrastructure + streaming only
docker compose up -d redis timescaledb streaming
```

### View Logs

```bash
# Follow all logs
docker compose logs -f

# Follow specific service
docker compose logs -f streaming
docker compose logs -f live_trading

# View last 100 lines
docker compose logs --tail 100 streaming
```

### Service Control

```bash
# Stop services
docker compose stop

# Stop specific service
docker compose stop live_trading

# Restart service
docker compose restart streaming

# Rebuild and restart (after code changes)
docker compose up -d --build streaming
docker compose up -d --build live_trading
```

### Check Status

```bash
# List running containers
docker compose ps

# Check service health
docker compose ps --format json | jq '.[].Health'

# Inspect service
docker inspect quant-vibe-streaming
```

### Clean Up

```bash
# Stop and remove containers
docker compose down

# Remove containers + volumes (WARNING: deletes data)
docker compose down -v

# Remove containers + volumes + images
docker compose down -v --rmi all
```

## Volume Management

### Volumes

| Volume | Purpose | Data |
|--------|---------|------|
| `redis_data` | Redis persistence | Pub/sub messages, cache |
| `timescaledb_data` | TimescaleDB storage | Options bars, historical data |
| `live_trading_state` | Live trading state | Position tracking, orders |
| `./tokens` (bind mount) | Schwab OAuth tokens | Shared across services |

### Inspect Volumes

```bash
# List volumes
docker volume ls | grep quant-vibe

# Inspect volume
docker volume inspect quant-vibe_timescaledb_data

# View disk usage
docker system df -v
```

### Backup/Restore

```bash
# Backup TimescaleDB volume
docker run --rm -v quant-vibe_timescaledb_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/timescaledb-backup-$(date +%Y%m%d).tar.gz /data

# Backup live trading state
docker run --rm -v quant-vibe_live_trading_state:/data -v $(pwd):/backup \
  alpine tar czf /backup/live-trading-state-$(date +%Y%m%d).tar.gz /data

# Restore (example)
docker run --rm -v quant-vibe_timescaledb_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/timescaledb-backup-20251225.tar.gz -C /
```

## Shared Tokens

All services share the same Schwab OAuth tokens via bind mount:

```yaml
volumes:
  - ./tokens:/app/tokens  # ← Local ./tokens/ directory mounted
```

**Benefits:**
- ✅ Single token refresh benefits all services
- ✅ Easy to inspect/debug locally
- ✅ No manual token copying needed

**Important:**
- Keep `./tokens/` in `.gitignore` (already configured)
- Tokens are shared read/write (first service to refresh updates for all)

## Troubleshooting

### Service won't start

```bash
# Check service logs
docker compose logs streaming

# Check dependencies
docker compose ps

# Verify environment variables
docker compose config | grep -A 20 streaming

# Restart dependencies first
docker compose restart redis timescaledb
docker compose up -d streaming
```

### Token errors

```bash
# Verify tokens exist locally
ls -la tokens/

# Check token permissions
chmod 644 tokens/*.json

# Verify tokens are mounted in container
docker exec quant-vibe-streaming ls -la /app/tokens/
```

### Redis connection issues

```bash
# Test Redis connectivity
docker exec quant-vibe-redis redis-cli ping
# Expected: PONG

# Check Redis logs
docker logs quant-vibe-redis

# Test pub/sub
docker exec quant-vibe-redis redis-cli PUBSUB CHANNELS
# Should show: streaming.options_bars, streaming.underlying_bars
```

### TimescaleDB connection issues

```bash
# Test database connection
docker exec quant-vibe-timescaledb psql -U quantvibe -d options_data -c "SELECT 1"
# Expected: 1 row returned

# Check database logs
docker logs quant-vibe-timescaledb

# Verify schema
docker exec quant-vibe-timescaledb psql -U quantvibe -d options_data -c "\dt"
```

### Port conflicts

```bash
# Check if ports are already in use
lsof -i :6379  # Redis
lsof -i :5432  # TimescaleDB

# Change ports in docker-compose.yml if needed
# Example: "6380:6379" for Redis (host:container)
```

## Development Workflow

### 1. Local Development (Python)

```bash
# Start infrastructure only
docker compose up -d redis timescaledb

# Run services locally
source venv/bin/activate
python scripts/stream_spxw_schwabdev.py      # Terminal 1
python scripts/run_live_trading.py           # Terminal 2
```

**Benefits:**
- Fast iteration (no image rebuilds)
- Direct access to debugger
- Immediate code changes

### 2. Hybrid Mode (Docker + Local)

```bash
# Run streaming in Docker
docker compose up -d redis timescaledb streaming

# Run live trading locally
python scripts/run_live_trading.py
```

**Benefits:**
- Streaming service isolated
- Live trading easy to debug

### 3. Full Docker Mode

```bash
# Run everything in Docker
docker compose up -d

# View logs
docker compose logs -f
```

**Benefits:**
- Production-like environment
- Easy multi-service management

### Code Updates

**Option A: Bind Mount (Current Setup)**
- Code changes reflected immediately (no rebuild)
- Restart service: `docker compose restart streaming`

**Option B: Image Rebuild**
```bash
# After code changes
docker compose up -d --build streaming
```

## Production Considerations

### Before Deploying to Production

1. **Change bind mounts to volumes**
   ```yaml
   # Development (current)
   - ./tokens:/app/tokens

   # Production
   - schwab_tokens:/app/tokens  # Named volume
   ```

2. **Use Docker secrets for credentials**
   ```yaml
   secrets:
     - schwab_api_key
     - schwab_api_secret
   ```

3. **Set resource limits**
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '1.0'
         memory: 2G
   ```

4. **Use health checks**
   ```yaml
   healthcheck:
     test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8080/health')"]
     interval: 30s
     timeout: 10s
     retries: 3
   ```

5. **Configure logging**
   ```yaml
   logging:
     driver: "json-file"
     options:
       max-size: "10m"
       max-file: "3"
   ```

## Environment Variables

Required environment variables in `.env`:

```bash
# Schwab API
SCHWAB_API_KEY=your_key
SCHWAB_API_SECRET=your_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182
SCHWAB_ACCOUNT_NUMBER=your_account

# TimescaleDB
TIMESCALE_PASSWORD=quantvibe_dev

# Redis (optional, defaults provided)
REDIS_HOST=localhost  # Use 'redis' in Docker
REDIS_PORT=6379
REDIS_DB=0
```

**Docker automatically overrides** host values:
- `REDIS_HOST=redis` (uses service name)
- `TIMESCALE_HOST=timescaledb` (uses service name)

## Quick Reference

```bash
# Start everything
docker compose up -d

# View streaming logs
docker compose logs -f streaming

# View live trading logs
docker compose logs -f live_trading

# Restart service after code change
docker compose restart streaming

# Stop everything
docker compose down

# Full cleanup (WARNING: deletes data)
docker compose down -v
```

## Getting Help

- Check service logs: `docker compose logs [service]`
- Verify configuration: `docker compose config`
- Check service health: `docker compose ps`
- Test Redis: See REDIS_DEPLOYMENT_CHECKLIST.md
- Test messaging: `python scripts/test_redis_messaging.py`
