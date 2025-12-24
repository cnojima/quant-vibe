# Docker Auto-Restart Setup Guide

This guide explains how to run the SPXW streaming service and TimescaleDB with automatic restarts using Docker.

## Overview

The Docker setup includes:
1. **TimescaleDB** - PostgreSQL database with TimescaleDB extension for options data
2. **Streaming Service** - Python script that streams SPXW options data from Schwab

Both services are configured with `restart: unless-stopped`, meaning they will:
- ✅ Restart automatically on crash
- ✅ Start automatically when Docker daemon starts
- ✅ NOT restart if manually stopped
- ✅ Use your live code (volume-mounted repo)

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
# Build the streaming service image (first time only)
docker-compose build

# Start both services in background
docker-compose up -d

# View logs
docker-compose logs -f streaming
```

### 3. Verify Services are Running
```bash
# Check status
docker-compose ps

# Should show:
# NAME                        STATUS
# quant-vibe-streaming        Up X minutes
# quant-vibe-timescaledb      Up X minutes (healthy)
```

## Management Commands

### Start Services
```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d streaming
docker-compose up -d timescaledb
```

### Stop Services
```bash
# Stop all services (won't auto-restart)
docker-compose stop

# Stop specific service
docker-compose stop streaming
```

### Restart Services
```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart streaming
```

### View Logs
```bash
# Follow logs for all services
docker-compose logs -f

# Follow logs for streaming service only
docker-compose logs -f streaming

# Last 100 lines
docker-compose logs --tail=100 streaming
```

### Rebuild After Code Changes
```bash
# Code changes are live (volume-mounted), but if you change dependencies:
docker-compose build streaming

# Rebuild and restart
docker-compose up -d --build streaming
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
# Kill the streaming container (should auto-restart)
docker kill quant-vibe-streaming

# Watch it restart
docker-compose logs -f streaming

# Should see: container restarting within seconds
```

## Configuration

### Environment Variables
All configuration is in `.env` file:
```bash
# Schwab API
SCHWAB_API_KEY=your_key
SCHWAB_API_SECRET=your_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
SCHWAB_ACCOUNT_NUMBER=your_account

# TimescaleDB
TIMESCALE_PASSWORD=quantvibe_dev
```

### Database Connection
The streaming service connects to TimescaleDB using:
- Host: `timescaledb` (Docker service name)
- Port: `5432`
- Database: `options_data`
- User: `quantvibe`

### Volume Mounts
1. **Code (live):** `.:/app` - Your entire repo is mounted, code changes are immediate
2. **Tokens:** `schwab_tokens:/app/tokens` - Persisted across container restarts
3. **Database:** `timescaledb_data:/var/lib/postgresql/data` - Persisted database

## Troubleshooting

### Streaming Service Won't Start
```bash
# Check logs
docker-compose logs streaming

# Common issues:
# 1. Missing .env file
# 2. TimescaleDB not healthy yet (wait for health check)
# 3. Invalid Schwab credentials
```

### Database Connection Failed
```bash
# Verify TimescaleDB is healthy
docker-compose ps

# Should show "healthy" status
# If unhealthy, check database logs:
docker-compose logs timescaledb
```

### Code Changes Not Reflected
```bash
# Code is volume-mounted, changes should be immediate
# If using a compiled extension, rebuild:
docker-compose restart streaming
```

### Token Authentication Issues
```bash
# Tokens are persisted in named volume
# To reset tokens (force re-authentication):
docker-compose down
docker volume rm quant-vibe_schwab_tokens
docker-compose up -d
```

## Development Workflow

### Typical Development Flow:
1. Edit code in your repo (IDE, editor, etc.)
2. Code changes are immediately available in container (volume mount)
3. Container auto-restarts on crash
4. View logs: `docker-compose logs -f streaming`

### After Changing Dependencies (pyproject.toml):
```bash
# Rebuild image with new dependencies
docker-compose build streaming

# Restart with new image
docker-compose up -d streaming
```

### After Changing Database Schema:
```bash
# Stop services
docker-compose down

# Remove database volume (DELETES DATA!)
docker volume rm quant-vibe_timescaledb_data

# Restart (will re-initialize schema)
docker-compose up -d
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

# View resource usage
docker stats quant-vibe-streaming quant-vibe-timescaledb

# Health check
docker inspect quant-vibe-streaming --format='{{.State.Health.Status}}'
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

### Custom Streaming Parameters
Edit `docker-compose.yml`:
```yaml
streaming:
  command: ["python", "scripts/stream_spxw_schwabdev.py", "--max-dte", "7", "--strike-range-pct", "0.20"]
```

### Multiple Streaming Services
Add to `docker-compose.yml`:
```yaml
  streaming-0dte:
    build: .
    command: ["python", "scripts/stream_spxw_schwabdev.py", "--max-dte", "0"]
    # ... same config as streaming service
```

### Resource Limits
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
```

## Monitoring

### Check Service Health
```bash
# Streaming service health check (custom)
docker exec quant-vibe-streaming python -c "from quant_vibe.data.timescale_store import TimescaleStore; print('OK')"

# Database health check (built-in)
docker exec quant-vibe-timescaledb pg_isready -U quantvibe -d options_data
```

### View Resource Usage
```bash
# Real-time stats
docker stats quant-vibe-streaming quant-vibe-timescaledb

# Disk usage
docker system df
```

### Export Logs
```bash
# Save logs to file
docker-compose logs --no-color > logs.txt

# Save with timestamps
docker-compose logs -t --no-color > logs.txt
```
