# Docker Setup Guide

This guide explains how to run the Quant-Vibe platform using Docker and Docker Compose.

## Overview

The Docker setup includes **6 services** running in a Docker network:

1. **Redis** - Message broker for pub/sub communication between services
2. **TimescaleDB** - PostgreSQL database with TimescaleDB extension for options data
3. **Token Service** - Centralized OAuth token management for Schwab API
4. **Streaming Service** - Websocket streaming for SPXW options data (publishes to Redis)
5. **Live Trading Engine** - Real-time trading engine (subscribes to Redis feed)
6. **Admin UI** - Web-based admin interface for service monitoring and control

All services are configured with `restart: unless-stopped`, meaning they will:
- ✅ Restart automatically on crash
- ✅ Start automatically when Docker daemon starts
- ✅ NOT restart if manually stopped
- ✅ Use your live code (volume-mounted repo for development)

## Service Architecture

### Dependency Graph
```
┌─────────────┐     ┌─────────────────┐
│    Redis    │     │  TimescaleDB    │
│ (Message    │     │  (Database)     │
│  Broker)    │     │                 │
└──────┬──────┘     └────────┬────────┘
       │                     │
       └──────────┬──────────┘
                  │
         ┌────────▼────────┐
         │  Token Service  │
         │  (OAuth Manager)│
         └────────┬────────┘
                  │
         ┌────────▼────────────┐
         │ Streaming Service   │
         │ (Schwab WS → Redis) │
         └──────┬──────────────┘
                │
                ├─────────────────────┐
                │                     │
       ┌────────▼─────────┐  ┌───────▼──────────┐
       │ Live Trading     │  │    Admin UI      │
       │ (Strategy        │  │  (Web Dashboard) │
       │  Execution)      │  │                  │
       └──────────────────┘  └──────────────────┘
```

### Service Dependencies
- **Redis** & **TimescaleDB**: No dependencies (base infrastructure)
- **Token Service**: Depends on Redis (healthy)
- **Streaming Service**: Depends on Redis (healthy), TimescaleDB (healthy), Token Service (healthy)
- **Live Trading**: Depends on Redis (healthy), TimescaleDB (healthy), Token Service (healthy), Streaming (started)
- **Admin UI**: Depends on Redis (healthy), TimescaleDB (healthy)

### Data Flow
1. **Token Management**: Token Service manages OAuth tokens, publishes refresh events to Redis
2. **Market Data Collection**: Streaming Service subscribes to Schwab websocket, publishes bars to Redis topics, stores in TimescaleDB
3. **Strategy Execution**: Live Trading subscribes to Redis topics, executes strategies, places orders via Schwab API
4. **Monitoring**: Admin UI monitors all services, provides web interface for control and viewing

## Quick Start

### 1. Ensure Docker is Running
```bash
# macOS: Open Docker Desktop or start daemon
open -a Docker

# Verify Docker is running
docker info
```

### 2. Build and Start Services
```bash
# Build all service images (first time only)
docker-compose build

# Start all services in background
docker-compose up -d

# View logs for all services
docker-compose logs -f

# View logs for specific service
docker-compose logs -f streaming
docker-compose logs -f token_service
docker-compose logs -f live_trading
```

### 3. Verify Services are Running
```bash
# Check status
docker-compose ps

# Should show all 6 services running:
# NAME                        STATUS
# quant-vibe-redis            Up X minutes (healthy)
# quant-vibe-timescaledb      Up X minutes (healthy)
# quant-vibe-token-service    Up X minutes (healthy)
# quant-vibe-streaming        Up X minutes
# quant-vibe-live-trading     Up X minutes
# quant-vibe-admin-ui         Up X minutes (healthy)
```

### 4. Access Admin UI
```bash
# Open browser to http://localhost:8000
# Default credentials: admin / changeme
# Set custom credentials in .env file (ADMIN_USERNAME, ADMIN_PASSWORD)
```

## Management Commands

### Start Services
```bash
# Start all services
docker-compose up -d

# Start specific service(s)
docker-compose up -d redis timescaledb
docker-compose up -d token_service
docker-compose up -d streaming
docker-compose up -d live_trading
docker-compose up -d admin_ui
```

### Stop Services
```bash
# Stop all services (won't auto-restart)
docker-compose stop

# Stop specific service
docker-compose stop streaming
docker-compose stop live_trading
docker-compose stop admin_ui
```

### Restart Services
```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart streaming
docker-compose restart live_trading
docker-compose restart token_service
```

### View Logs
```bash
# Follow logs for all services
docker-compose logs -f

# Follow logs for specific service
docker-compose logs -f streaming
docker-compose logs -f live_trading
docker-compose logs -f token_service
docker-compose logs -f admin_ui

# Last 100 lines from a service
docker-compose logs --tail=100 streaming

# Show logs with timestamps
docker-compose logs -t streaming
```

### Rebuild After Code Changes
```bash
# Code changes are live (volume-mounted), but if you change dependencies:
docker-compose build streaming

# Rebuild specific service and restart
docker-compose up -d --build streaming
docker-compose up -d --build live_trading

# Rebuild all services
docker-compose build
docker-compose up -d
```

### Clean Up
```bash
# Stop and remove containers (keeps volumes)
docker-compose down

# Stop, remove containers AND volumes (DELETES DATA!)
docker-compose down -v
```

## Auto-Restart Behavior

### When Services Restart Automatically:
- Python script crashes (exception, segfault, etc.)
- Database crashes
- Docker daemon restarts
- System reboots (if Docker is set to start on boot)

### When Services DON'T Restart:
- You manually stop them with `docker-compose stop`
- You use `docker stop quant-vibe-streaming`
- Exit code indicates intentional shutdown

### Testing Auto-Restart
```bash
# Kill a container (should auto-restart)
docker kill quant-vibe-streaming
docker kill quant-vibe-live-trading
docker kill quant-vibe-token-service

# Watch it restart
docker-compose logs -f streaming
docker-compose logs -f live_trading
docker-compose logs -f token_service

# Should see: container restarting within seconds
```

## Configuration

### Environment Variables
All configuration is in `.env` file:
```bash
# Schwab API credentials
SCHWAB_API_KEY=your_key
SCHWAB_API_SECRET=your_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
SCHWAB_ACCOUNT_NUMBER=your_account

# TimescaleDB password
TIMESCALE_PASSWORD=quantvibe_dev

# Admin UI credentials (IMPORTANT: change these!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
JWT_SECRET_KEY=change-this-secret-key
DEBUG=false
```

### Service Architecture & Communication
All services communicate via Docker network (`quant-vibe-network`):

**Redis** (Message Broker)
- Host: `redis` (Docker service name)
- Port: `6379`
- Purpose: Pub/sub messaging between services
- Topics: `streaming.options_bars`, `streaming.underlying_bars`

**TimescaleDB** (Database)
- Host: `timescaledb` (Docker service name)
- Port: `5432` (exposed to localhost)
- Database: `options_data`
- User: `quantvibe`

**Token Service** (OAuth Manager)
- Host: `token_service` (Docker service name)
- Port: `8100`
- Purpose: Centralized Schwab API token management
- API: `http://token_service:8100/token`

**Streaming Service** (Data Publisher)
- Depends on: Redis, TimescaleDB, Token Service
- Subscribes to: Schwab API websocket
- Publishes to: Redis topics
- Stores to: TimescaleDB

**Live Trading Engine** (Strategy Execution)
- Depends on: Redis, TimescaleDB, Token Service, Streaming
- Subscribes to: Redis topics (market data)
- Publishes to: Schwab API (orders)

**Admin UI** (Web Interface)
- Port: `8000` (exposed to localhost)
- Purpose: Monitor and control services
- Access: `http://localhost:8000`

### Volume Mounts
1. **Code (live, development):** `.:/app` - Your entire repo is mounted, code changes are immediate
2. **Tokens (shared):** `./tokens:/app/tokens` - Shared across all services
3. **Config (shared):** `./config:/app/config` - Shared configuration
4. **Logs (shared):** `./logs:/app/logs` - Shared log directory
5. **Database (persistent):** `timescaledb_data:/var/lib/postgresql/data` - Persisted database
6. **Redis (persistent):** `redis_data:/data` - Persisted Redis data
7. **Live trading state:** `live_trading_state:/app/state` - Persisted trading state
8. **Docker socket (admin UI):** `/var/run/docker.sock:/var/run/docker.sock` - Service control

## Troubleshooting

### Services Won't Start
```bash
# Check logs for specific service
docker-compose logs streaming
docker-compose logs live_trading
docker-compose logs token_service
docker-compose logs admin_ui

# Check all service health status
docker-compose ps

# Common issues:
# 1. Missing .env file
# 2. Services not healthy yet (wait for health checks)
# 3. Invalid Schwab credentials
# 4. Port conflicts (5432, 6379, 8000, 8100 already in use)
```

### Database Connection Failed
```bash
# Verify TimescaleDB is healthy
docker-compose ps

# Should show "healthy" status
# If unhealthy, check database logs:
docker-compose logs timescaledb

# Test connection manually
docker exec quant-vibe-timescaledb pg_isready -U quantvibe -d options_data
```

### Redis Connection Failed
```bash
# Verify Redis is healthy
docker-compose ps

# Check Redis logs
docker-compose logs redis

# Test connection manually
docker exec quant-vibe-redis redis-cli ping
```

### Token Service Issues
```bash
# Check token service health
curl http://localhost:8100/health

# View token service logs
docker-compose logs -f token_service

# Get current token status
curl http://localhost:8100/token
```

### Code Changes Not Reflected
```bash
# Code is volume-mounted, changes should be immediate
# Restart service to reload Python modules:
docker-compose restart streaming
docker-compose restart live_trading

# If dependencies changed, rebuild:
docker-compose build streaming
docker-compose up -d streaming
```

### Token Authentication Issues
```bash
# Tokens are stored in ./tokens directory (bind mount)
# To reset tokens (force re-authentication):
rm -rf ./tokens/*
docker-compose restart token_service
docker-compose restart streaming
docker-compose restart live_trading
```

### Admin UI Access Issues
```bash
# Verify admin UI is running
curl http://localhost:8000/health

# Check admin UI logs
docker-compose logs -f admin_ui

# Verify Docker socket permission (macOS/Linux)
ls -la /var/run/docker.sock

# Restart admin UI
docker-compose restart admin_ui
```

### Port Conflicts
```bash
# Check which process is using a port
lsof -i :5432  # TimescaleDB
lsof -i :6379  # Redis
lsof -i :8000  # Admin UI
lsof -i :8100  # Token Service

# Stop conflicting service or change port in docker-compose.yml
```

## Development Workflow

### Typical Development Flow:
1. Edit code in your repo (IDE, editor, etc.)
2. Code changes are immediately available in all containers (volume mount)
3. Containers auto-restart on crash
4. View logs: `docker-compose logs -f <service_name>`
5. Monitor via Admin UI: `http://localhost:8000`

### After Changing Dependencies (pyproject.toml):
```bash
# Rebuild affected service with new dependencies
docker-compose build streaming
docker-compose build live_trading
docker-compose build admin_ui

# Or rebuild all services
docker-compose build

# Restart with new images
docker-compose up -d
```

### After Changing Database Schema:
```bash
# Stop services
docker-compose down

# Remove database volume (DELETES DATA!)
docker volume rm quant-vibe_timescaledb_data

# Restart (will re-initialize schema from init_timescale.sql)
docker-compose up -d
```

### Testing Individual Services:
```bash
# Start only infrastructure (DB + Redis)
docker-compose up -d redis timescaledb

# Start token service
docker-compose up -d token_service

# Test streaming service
docker-compose up -d streaming
docker-compose logs -f streaming

# Test live trading
docker-compose up -d live_trading
docker-compose logs -f live_trading
```

## Production Deployment

### Enable Docker to Start on Boot (macOS):
1. Open Docker Desktop
2. Preferences → General
3. Check "Start Docker Desktop when you log in"

### Enable Docker to Start on Boot (Linux):
```bash
# Enable Docker service
sudo systemctl enable docker

# Start services on boot
docker-compose up -d
```

### Monitor Services:
```bash
# Check if containers are running
docker-compose ps

# View resource usage for all services
docker stats quant-vibe-redis quant-vibe-timescaledb quant-vibe-token-service quant-vibe-streaming quant-vibe-live-trading quant-vibe-admin-ui

# Health check for specific services
docker inspect quant-vibe-redis --format='{{.State.Health.Status}}'
docker inspect quant-vibe-timescaledb --format='{{.State.Health.Status}}'
docker inspect quant-vibe-token-service --format='{{.State.Health.Status}}'
docker inspect quant-vibe-admin-ui --format='{{.State.Health.Status}}'

# Or use the Admin UI
open http://localhost:8000
```

## Comparison: Docker vs Other Methods

| Method | Auto-Restart | Code Updates | Platform | Complexity |
|--------|--------------|--------------|----------|------------|
| **Docker (this setup)** | ✅ Yes | ✅ Live | All | Low |
| systemd (Linux) | ✅ Yes | ✅ Live | Linux only | Medium |
| launchd (macOS) | ✅ Yes | ✅ Live | macOS only | Medium |
| supervisord | ✅ Yes | ✅ Live | All | Medium |
| Manual (screen/tmux) | ❌ No | ✅ Live | All | Low |

## Advanced Configuration

### Custom Service Parameters
Edit `docker-compose.yml` to customize service startup:
```yaml
# Custom streaming parameters
streaming:
  command: ["python", "scripts/stream_spxw_schwabdev.py", "--max-dte", "7", "--strike-range-pct", "0.20"]

# Custom live trading config
live_trading:
  command: ["python", "scripts/run_live_trading.py", "--config", "config/custom_live_trading.yaml"]

# Custom token service refresh interval
token_service:
  environment:
    TOKEN_REFRESH_INTERVAL_MINUTES: 10  # Default is 14
```

### Multiple Service Instances
Add additional instances to `docker-compose.yml`:
```yaml
  streaming-0dte:
    build:
      context: .
      dockerfile: docker/Dockerfile.streaming
    container_name: quant-vibe-streaming-0dte
    restart: unless-stopped
    command: ["python", "scripts/stream_spxw_schwabdev.py", "--max-dte", "0"]
    # ... same dependencies, environment, volumes, and network as streaming service

  live_trading-conservative:
    build:
      context: .
      dockerfile: docker/Dockerfile.streaming
    container_name: quant-vibe-live-trading-conservative
    restart: unless-stopped
    command: ["python", "scripts/run_live_trading.py", "--config", "config/conservative.yaml"]
    # ... same dependencies, environment, volumes, and network as live_trading service
```

### Resource Limits
Add resource constraints to services:
```yaml
  streaming:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 512M

  timescaledb:
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 4G
        reservations:
          cpus: '2.0'
          memory: 2G
```

## Monitoring

### Check Service Health
```bash
# Redis health check
docker exec quant-vibe-redis redis-cli ping

# Database health check
docker exec quant-vibe-timescaledb pg_isready -U quantvibe -d options_data

# Token service health check
curl http://localhost:8100/health

# Admin UI health check
curl http://localhost:8000/health

# Python service health check
docker exec quant-vibe-streaming python -c "from quant_vibe.data.timescale_store import TimescaleStore; print('OK')"
```

### View Resource Usage
```bash
# Real-time stats for all services
docker stats

# Real-time stats for specific services
docker stats quant-vibe-streaming quant-vibe-live-trading quant-vibe-timescaledb

# Disk usage
docker system df

# Volume usage
docker volume ls
docker system df -v
```

### Export Logs
```bash
# Save all logs to file
docker-compose logs --no-color > all-services-logs.txt

# Save specific service logs with timestamps
docker-compose logs -t --no-color streaming > streaming-logs.txt
docker-compose logs -t --no-color live_trading > live-trading-logs.txt
docker-compose logs -t --no-color token_service > token-service-logs.txt

# Save logs since a specific time
docker-compose logs --since="1h" streaming > streaming-last-hour.txt
```

### Admin UI Monitoring
The Admin UI provides a web-based dashboard for monitoring all services:
```bash
# Open Admin UI
open http://localhost:8000

# Features:
# - Service status and health checks
# - Real-time logs viewer
# - Start/stop/restart services
# - Resource usage metrics
# - Token status
# - Database queries
```

## Common Use Cases

### Use Case 1: Development with Live Code Changes
```bash
# Start all services
docker-compose up -d

# Edit code in your IDE (e.g., strategy logic)
# Changes are immediately available in containers

# Restart service to reload Python modules
docker-compose restart live_trading

# Monitor logs
docker-compose logs -f live_trading
```

### Use Case 2: Testing Streaming Service Only
```bash
# Start infrastructure only
docker-compose up -d redis timescaledb token_service

# Start streaming service
docker-compose up -d streaming

# Monitor streaming logs
docker-compose logs -f streaming

# Stop streaming when done
docker-compose stop streaming
```

### Use Case 3: Running Live Trading in Paper Mode
```bash
# Ensure config/live_trading.yaml has paper_mode: true

# Start all required services
docker-compose up -d redis timescaledb token_service streaming live_trading

# Monitor live trading execution
docker-compose logs -f live_trading

# Check Admin UI for position tracking
open http://localhost:8000
```

### Use Case 4: Debugging a Specific Service
```bash
# Stop the service you want to debug
docker-compose stop live_trading

# Run it interactively with live logs
docker-compose run --rm live_trading python scripts/run_live_trading.py

# Or attach to running container
docker exec -it quant-vibe-live-trading bash
python scripts/run_live_trading.py --verbose
```

### Use Case 5: Production Deployment
```bash
# Set production credentials in .env
# ADMIN_USERNAME=your_admin
# ADMIN_PASSWORD=your_secure_password
# JWT_SECRET_KEY=your_secret_key

# Start all services
docker-compose up -d

# Verify all services are healthy
docker-compose ps

# Enable Docker to start on boot (see Production Deployment section)

# Monitor via Admin UI
open http://localhost:8000
```

### Use Case 6: Cleaning Up and Starting Fresh
```bash
# Stop all services
docker-compose down

# Remove all volumes (DELETES ALL DATA!)
docker-compose down -v

# Remove all tokens
rm -rf ./tokens/*

# Rebuild images
docker-compose build

# Start fresh
docker-compose up -d
```

## Security Considerations

### Environment Variables
```bash
# NEVER commit .env file to version control
# Add to .gitignore (already done)

# Use strong credentials in production
ADMIN_PASSWORD=use-a-strong-password-here
JWT_SECRET_KEY=use-a-long-random-secret-key

# Rotate secrets regularly
# Update .env and restart services:
docker-compose restart admin_ui
```

### Network Security
```bash
# By default, services are only accessible on localhost
# TimescaleDB: localhost:5432
# Redis: localhost:6379
# Admin UI: localhost:8000
# Token Service: localhost:8100

# To restrict access further, remove port mappings from docker-compose.yml
# and access services only via Docker network

# For production, use a reverse proxy (nginx, traefik) with TLS
```

### Token Storage
```bash
# Tokens are stored in ./tokens directory (bind mount)
# Ensure this directory has proper permissions:
chmod 700 ./tokens

# In production, consider using a secrets management system
# (e.g., Docker secrets, HashiCorp Vault)
```

### Admin UI Access
```bash
# Change default credentials immediately
# Set in .env file:
ADMIN_USERNAME=your_admin_username
ADMIN_PASSWORD=your_secure_password
JWT_SECRET_KEY=your_long_random_secret_key

# Restart admin UI to apply changes
docker-compose restart admin_ui
```

### Docker Socket Access
```bash
# Admin UI has access to Docker socket for service control
# This is required for start/stop/restart functionality
# In production, consider restricting socket access or using
# a dedicated service manager instead
```

## Performance Tuning

### TimescaleDB Optimization
The docker-compose.yml includes optimized PostgreSQL settings:
- `shared_buffers=512MB` - Memory for caching data
- `effective_cache_size=1GB` - Total memory available for caching
- `work_mem=4MB` - Memory for sort/hash operations
- `max_connections=200` - Maximum concurrent connections

Adjust based on your system resources in docker-compose.yml.

### Redis Configuration
Redis is configured with:
- `maxmemory 512mb` - Maximum memory usage
- `maxmemory-policy allkeys-lru` - Eviction policy
- `appendonly yes` - Persistence enabled

Adjust in docker-compose.yml command section.

### Container Resources
Add resource limits to prevent any single service from consuming all system resources:
```yaml
services:
  streaming:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
```

## Backup and Recovery

### Database Backup
```bash
# Create database backup
docker exec quant-vibe-timescaledb pg_dump -U quantvibe options_data > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore from backup
docker exec -i quant-vibe-timescaledb psql -U quantvibe options_data < backup_20251230_120000.sql
```

### Volume Backup
```bash
# Create volume backup (database data)
docker run --rm \
  -v quant-vibe_timescaledb_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/timescaledb_backup_$(date +%Y%m%d).tar.gz /data

# Restore volume
docker run --rm \
  -v quant-vibe_timescaledb_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/timescaledb_backup_20251230.tar.gz -C /
```

### Configuration Backup
```bash
# Backup configuration and tokens
tar czf config_backup_$(date +%Y%m%d).tar.gz config/ tokens/ .env

# Restore
tar xzf config_backup_20251230.tar.gz
```
