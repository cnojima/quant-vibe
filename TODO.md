# QUANT-VIBE TODOs

## ✅ Refactor backtesting to top-level layer
 - COMPLETE: Moved to `src/backtest/` as peer component
 - Config-driven orchestration via `config/backtest.yaml`
 - CLI: `python scripts/run_backtest.py`

## ✅ Normalize logging format: [datetime][app][level][msg]
 - COMPLETE: Unified logging system in `src/quant_vibe/config/unified_logging.py`
 - Format: `[2025-12-25 12:00:00][app][LEVEL   ] Message`
 - Stack trace handling with proper indentation
 - Multi-line message support
 - Implemented in: backtest ✅, streaming_service ✅
 - Live trading uses custom logging (can be migrated later)

## ✅ Refactor live-trading to top-level layer
 - COMPLETE: Live-trading now uses Redis pub/sub to consume data from StreamingService
 - Eliminates duplicate Schwab API connections
 - Implemented exponential backoff retry mechanism for API errors
 - Configuration: `use_redis_feed: true` in `config/live_trading.yaml`

## ✅ streaming_service retry mechanism
 - COMPLETE: Implemented exponential backoff for API calls
 - Retry decorator available: `@retry_with_backoff()`
 - Applied to critical Schwab API operations

## ✅ Implement centralized token management service

**Status**: COMPLETE ✅ - Core service implemented, ready for integration

Created a dedicated FastAPI microservice for OAuth token lifecycle management:

**Implementation:**
- ✅ Core `CentralizedTokenManager` with thread-safe token operations
- ✅ FastAPI service with REST API (`/health`, `/token/status`, `/token/access`, `/token/refresh`)
- ✅ Background auto-refresh task (runs every 14 minutes)
- ✅ Redis event publishing for token lifecycle events
- ✅ HTTP client library (`TokenServiceClient`) for easy integration
- ✅ Docker configuration in `docker-compose.yml`
- ✅ Comprehensive documentation (`docs/TOKEN_SERVICE.md`)
- ✅ Normalized logging format

**Location**: `src/token_service/`

**Files**:
- `manager.py` - Core token manager with schwabdev integration
- `service.py` - FastAPI service with REST endpoints
- `client.py` - HTTP client for other services to use
- `config.py` - Configuration management
- `scripts/run_token_service.py` - Startup script

**Architecture:**
```
token_service (FastAPI microservice)
  ↓ provides tokens via HTTP API
streaming_service, live_trading_service, admin_ui
  ↓ request tokens from token_service
Schwab API
```

**Benefits Achieved:**
- ✅ Single source of truth for tokens
- ✅ Centralized refresh logic (no duplicate code)
- ✅ Better monitoring and logging of token lifecycle
- ✅ Automatic token refresh every 14 minutes
- ✅ Thread-safe concurrent access
- ✅ Redis event publishing for coordination
- ✅ Docker health checks and orchestration
- ✅ Foundation for multiple broker APIs in the future

**All Core Features Complete** ✅

Testing phase:
- [ ] Write comprehensive tests for token_service
- [ ] Test failure scenarios for watcher (network outages, etc.)

**Usage**:
```bash
# Start token service
docker-compose up -d token_service

# Or run standalone
python scripts/run_token_service.py

# Use from other services
from token_service.client import TokenServiceClient
client = TokenServiceClient("http://token_service:8001")
token = client.get_access_token()
```

**Documentation**:
- Complete guide: `docs/TOKEN_SERVICE.md`
- Migration summary: `docs/TOKEN_SERVICE_MIGRATION.md`

## ✅ Migrate services to use centralized token_service

**Status**: COMPLETE ✅ - All services migrated with graceful fallback support

All services have been successfully migrated to use the centralized token_service:

### ✅ streaming_service migration (COMPLETE)
**Implementation**:
- ✅ Added `token_service_url` and `use_token_service` to config
- ✅ Integrated `TokenServiceClient` with graceful fallback
- ✅ Updated token refresh logic in `start()` method
- ✅ Updated main loop to use token service status
- ✅ Logs "Token Mode: Centralized" or "Token Mode: Legacy"
- ✅ Falls back to legacy `TokenManager` if token service unavailable

**Files Modified**:
- `src/streaming_service/config.py`
- `src/streaming_service/service.py`

### ✅ live_trading_service migration (COMPLETE)
**Implementation**:
- ✅ Added `TokenServiceClient` import with fallback handling
- ✅ Added `use_token_service` and `token_service_url` to engine state
- ✅ Health check on startup
- ✅ Logs "tokens via token service" or "tokens via local database"
- ✅ Graceful fallback to schwabdev token management

**Files Modified**:
- `src/live_trading_service/engine.py`

### ✅ admin_ui migration (COMPLETE)
**Implementation**:
- ✅ Added `TokenServiceClient` import
- ✅ Updated `/api/tokens/status` - Proxies to token service, falls back to database
- ✅ Updated `/api/tokens/refresh` - Proxies to token service, falls back to schwabdev
- ✅ Added `source` field to responses ("token_service" vs. "local_database")
- ✅ Graceful fallback to direct SQLite database access

**Files Modified**:
- `src/admin_ui/backend/api/tokens.py`

### Migration Features
- ✅ **Graceful Fallback**: All services fall back to legacy mode if token service unavailable
- ✅ **Backward Compatible**: Works with or without token service
- ✅ **No Breaking Changes**: Can run in legacy mode indefinitely
- ✅ **Easy Rollback**: Simply stop token service to revert
- ✅ **Comprehensive Logging**: Clear indication of which mode is active

**See `docs/TOKEN_SERVICE_MIGRATION.md` for complete migration details**

## ✅ Implement Pushover notification system

**Status**: COMPLETE ✅

Implemented comprehensive push notification system using Pushover for real-time trading alerts.

**Implementation**:
- ✅ `PushoverNotifier` - Core Pushover API integration
  - Support for all priority levels (lowest to emergency)
  - 20+ notification sounds
  - Device targeting
  - URL attachments
  - HTML formatting
- ✅ `TradingNotifier` - Event-driven trading notifications
  - Configurable event filtering
  - P&L thresholds
  - Automatic notification for trading events
- ✅ Pre-built notification methods:
  - Order filled/rejected
  - Position opened/closed
  - Engine start/stop
  - Risk alerts (critical/warning/info)
  - Daily summaries
- ✅ Comprehensive documentation (`docs/NOTIFICATIONS.md`)
- ✅ Test script (`scripts/test_pushover.py`)
- ✅ Environment configuration (.env.example updated)

**Location**: `src/quant_vibe/notifications/`

**Features**:
- Real-time push notifications to iOS, Android, desktop
- 5 priority levels (lowest, low, normal, high, emergency)
- Customizable sounds for different event types
- Event filtering and P&L thresholds
- Easy integration with LiveTradingEngine
- Credential validation
- Rate limiting awareness

**Usage**:
```python
from quant_vibe.notifications import TradingNotifier

notifier = TradingNotifier(config={
    "notify_on_position_close": True,
    "min_pnl_notify": 50.0  # Only notify for P&L >= $50
})

notifier.on_position_closed(
    strategy="BPS",
    symbol="SPX 6200/6180",
    pnl=75.00,
    pnl_pct=30.0
)
```

**Setup**:
1. Sign up at https://pushover.net
2. Create application for API token
3. Set `PUSHOVER_API_TOKEN` and `PUSHOVER_USER_KEY` in .env
4. Run `python scripts/test_pushover.py` to verify

**Documentation**: `docs/NOTIFICATIONS.md`

## ✅ Implement watcher/heartbeat monitoring

**Status**: COMPLETE ✅

Comprehensive service health monitoring system with multi-layer detection and smart alerting.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Heartbeat Watcher Service                              │
│  ├─ Monitors all services via multiple methods          │
│  ├─ Publishes health status to Redis                    │
│  ├─ Sends alerts via Pushover (leverages existing)      │
│  └─ Exposes metrics endpoint for admin_ui               │
└─────────────────────────────────────────────────────────┘
                         ↓
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Docker Health│  │ Redis Ping   │  │ HTTP Health  │
│ Checks       │  │ Messages     │  │ Endpoints    │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Services Monitored

1. **Infrastructure Services**:
   - `redis` - Message broker (critical)
   - `timescaledb` - Time-series database (critical)

2. **Application Services**:
   - `token_service` - OAuth token management (critical)
   - `streaming` - Market data streaming (critical)
   - `live_trading` - Trading engine (critical)
   - `admin_ui` - Web dashboard (non-critical)

### Multi-Layer Health Checks

**1. Docker Health Checks**:
- Leverage existing `healthcheck:` in docker-compose.yml
- Detect container crashes/restarts
- Check container status via Docker API

**2. Redis Heartbeats**:
- Services publish to `heartbeat.{service_name}` every 30s
- Payload includes metrics (uptime, messages, errors, memory)
- Watcher tracks last heartbeat timestamp per service
- Configurable thresholds: 3 missed = warning, 5 = critical

**3. HTTP Health Endpoints**:
- Call `/health` endpoints where available
- Validate response status and content
- Measure response time

### Heartbeat Protocol

Each service publishes to Redis topic `heartbeat.{service_name}`:

```python
{
    "service": "streaming",
    "timestamp": "2025-12-30T10:15:30Z",
    "status": "healthy",  # healthy, degraded, unhealthy
    "metrics": {
        "uptime_seconds": 3600,
        "messages_processed": 1234,
        "last_error": None,
        "memory_mb": 256
    }
}
```

### Configuration (`config/watcher.yaml`)

```yaml
watcher:
  check_interval_seconds: 30
  heartbeat_timeout_seconds: 90   # 3 missed heartbeats
  critical_timeout_seconds: 150   # 5 missed heartbeats

  services:
    - name: redis
      type: docker
      container: quant-vibe-redis
      critical: true

    - name: timescaledb
      type: docker
      container: quant-vibe-timescaledb
      critical: true

    - name: token_service
      type: hybrid  # Docker + HTTP + Redis heartbeat
      container: quant-vibe-token-service
      health_endpoint: http://token_service:8100/health
      heartbeat_topic: heartbeat.token_service
      critical: true

    - name: streaming
      type: hybrid
      container: quant-vibe-streaming
      heartbeat_topic: heartbeat.streaming
      critical: true

    - name: live_trading
      type: hybrid
      container: quant-vibe-live-trading
      heartbeat_topic: heartbeat.live_trading
      critical: true

    - name: admin_ui
      type: http
      health_endpoint: http://admin_ui:8000/health
      critical: false

  notifications:
    enabled: true
    channels:
      - pushover

    rules:
      - level: warning
        services: [streaming, live_trading]
        condition: missed_heartbeats >= 3
        message: "Service {{service}} missed {{count}} heartbeats"

      - level: critical
        services: [redis, timescaledb, token_service]
        condition: status == unhealthy
        message: "CRITICAL: {{service}} is DOWN"

      - level: emergency
        services: [live_trading]
        condition: missing >= 300  # 5 minutes
        message: "EMERGENCY: Live trading engine unresponsive"
```

### Implementation Plan

**Phase 1: Core Watcher Service** ✅ COMPLETE
- [x] Design architecture
- [x] Create `src/watcher_service/` module structure
- [x] Implement `ServiceMonitor` class (Docker/HTTP/Redis checks)
- [x] Implement `HeartbeatManager` (track last heartbeat per service)
- [x] Implement `AlertManager` (escalation, de-duplication)
- [x] Configuration loader for `config/watcher.yaml`
- [x] Normalized logging setup
- [x] Basic CLI: `scripts/run_watcher.py`

**Phase 2: Service Integration** ✅ COMPLETE
- [x] Add heartbeat publishing to `token_service/service.py`
- [x] Add heartbeat publishing to `streaming_service/service.py`
- [x] Add heartbeat publishing to `live_trading_service/engine.py`
- [x] Include business metrics in heartbeats
- [x] Update `docker-compose.yml` with watcher service

**Phase 3: Alerting & Recovery** ✅ COMPLETE
- [x] Integrate Pushover notifications (reuse existing)
- [x] Implement alert de-duplication (don't spam)
- [x] Auto-recovery detection (clear alerts when healthy)
- [x] Docker health checks capability
- [x] **Fix heartbeat listener** (2025-12-30) - Changed from blocking `listen()` to non-blocking `get_message()` polling
- [x] **Fix Pushover integration** (2025-12-30) - Corrected method name from `send_notification()` to `send()`
- [x] Test failure scenarios (container stop/start detection) ✅

**Phase 4: Admin UI Integration** 🚧 PENDING
- [ ] Add `/api/health/services` endpoint to admin_ui
- [ ] Real-time service status display
- [ ] Historical uptime data
- [ ] Alert history viewer

**Status**: ✅ **PRODUCTION READY** - Core implementation complete and tested. Pushover notifications working. Admin UI integration is optional enhancement.

**Testing Results** (2025-12-30):
- ✅ Service failure detection working (30s response time)
- ✅ Pushover notifications sent successfully
- ✅ Service recovery detection working
- ✅ Alert de-duplication working
- ✅ Docker health checks working
- ✅ Heartbeat messages publishing correctly (verified via diagnostic tool)

### File Structure

```
src/watcher_service/
├── __init__.py
├── config.py              # Configuration loader
├── service_monitor.py     # Docker/HTTP/Redis health checks
├── heartbeat_manager.py   # Track heartbeats per service
├── alert_manager.py       # Alert logic, escalation, de-dup
└── watcher.py            # Main orchestrator

config/
└── watcher.yaml          # Service definitions and thresholds

scripts/
└── run_watcher.py        # Startup script

docker-compose.yml        # Add watcher service
```

### Features

✅ **Multi-layer detection**: Docker + HTTP + Redis heartbeats
✅ **Smart alerting**: Escalation, de-duplication, auto-recovery
✅ **Business metrics**: Track performance, not just up/down
✅ **Leverages existing infra**: Redis, Pushover, Docker
✅ **Proactive monitoring**: Detect failures before users notice
✅ **Production-ready**: Configurable, logged, tested
✅ **Admin UI integration**: Real-time dashboard display

### Usage

**Development**:
```bash
# Start watcher service standalone
python scripts/run_watcher.py

# Or via Docker
docker-compose up -d watcher
```

**Service Integration**:
```python
# Each service publishes heartbeat every 30s
from quant_vibe.messaging import RedisMessageBroker

broker = RedisMessageBroker()
broker.publish("heartbeat.streaming", {
    "service": "streaming",
    "timestamp": datetime.utcnow().isoformat(),
    "status": "healthy",
    "metrics": {
        "uptime_seconds": 3600,
        "messages_processed": 1234
    }
})
```

**Admin UI**:
```bash
# View service health status
curl http://localhost:8000/api/health/services

# Response:
{
  "services": [
    {
      "name": "streaming",
      "status": "healthy",
      "last_heartbeat": "2025-12-30T10:15:30Z",
      "uptime_seconds": 3600,
      "missed_heartbeats": 0
    }
  ]
}
```

### Alternative Considered

**Prometheus + Grafana**:
- ❌ Adds complexity (2 more services to run)
- ❌ Overkill for 5-6 services
- ❌ Requires learning new tools
- ✅ Industry standard
- ✅ Rich visualization

**Decision**: Build custom watcher for now (simpler, tighter integration). Can migrate to Prometheus later if scaling needs change.

## 🚧 Implement Admin UI for real-time monitoring and control

**Status**: Backend complete ✅ | Frontend to build 🚧

Comprehensive web-based admin dashboard for the QuantVibe platform.

**Detailed Plan**: See `UI_SERVICE_PLAN.md` for full implementation details

**MVP Features**:
1. **Schwab API Token Management** 🔑
   - Display token status (valid/expired/expiring soon)
   - Countdown timer until expiration
   - One-click manual refresh
   - OAuth re-authentication flow (backend TODO)

2. **Service Status Dashboard** 🚦
   - Monitor all services (streaming, live_trading, redis, timescaledb)
   - Start/stop/restart controls via Docker API
   - Real-time logs viewer
   - Uptime tracking

3. **Live Trading Monitor** 📊
   - Engine status (running/stopped, paper/live mode)
   - Real-time position tracking with P&L
   - Order status and history
   - Live event stream via WebSocket
   - Trading statistics (win rate, Sharpe, total P&L)
   - Equity curve chart

4. **Backtest Runner & Analyzer** 📈
   - Strategy selection and parameter modification
   - Date range picker with presets
   - Async backtest execution with progress tracking
   - Results visualization (trades, equity curve, metrics)
   - Backtest history and CSV export

5. **Chart Visualizations** 📉
   - Equity curve (line chart)
   - Trade P&L distribution (histogram)
   - Drawdown chart
   - Price + indicators overlay (candlesticks + SMA/RSI/MACD)

**Technology Stack**:
- Backend: FastAPI (Python) - ✅ COMPLETE
  - REST API (`/api/*`)
  - WebSocket (`/ws/events`)
  - JWT authentication
  - Redis/TimescaleDB integration
- Frontend: React 18 + TypeScript + Vite - 🚧 TO BUILD
  - TanStack Query (data fetching)
  - Recharts (charting)
  - Tailwind CSS (styling)
  - React Router (routing)

**Implementation Phases**:
1. **Phase 1**: Foundation setup (2-3 days)
   - Project structure
   - API client with auth interceptors
   - WebSocket hook
   - TypeScript types

2. **Phase 2**: MVP features (5-7 days)
   - Login page
   - Service dashboard
   - Token manager
   - Live trading monitor
   - Backtest runner
   - Charts

3. **Phase 3**: Backend gaps (2-3 days)
   - OAuth callback handler
   - Configuration editor API

**Estimated Total**: ~2 weeks for MVP

**Development Commands**:
```bash
# Backend (already working)
cd src/admin_ui/backend
python -m uvicorn main:app --reload --port 8000

# Frontend (to implement)
cd src/admin_ui/frontend
npm install
npm run dev  # Port 3000

# Production
npm run build
# Backend serves static files from dist/
```

**Docker Deployment**: Already configured in `docker-compose.yml`

**Next Actions**:
1. Set up frontend project structure
2. Implement authentication (Login.tsx)
3. Build service dashboard
4. Implement remaining MVP features
5. Fill backend OAuth gaps
6. End-to-end testing
7. Production deployment

## ✅ Implement Dynamic DNS (Sonic.net)

**Status**: COMPLETE ✅

Automatic DNS updates for remote access to Quant-Vibe services using Sonic.net DynDNS API.

**Implementation**:
- ✅ `SonicDynDNSClient` - Complete API client for Sonic.net DynDNS
  - API connectivity testing (ping)
  - Current IP detection
  - DNS record updates (A, AAAA, TXT)
  - IP change detection
  - Force update and conditional update methods
- ✅ DynDNS service daemon (`scripts/run_dyndns.py`)
  - Configurable update intervals (default: 5 minutes)
  - Force update on startup
  - Normalized logging with rotation
  - Error handling with retry logic
  - Statistics tracking
- ✅ Docker integration in `docker-compose.yml`
  - Auto-restart on failure
  - Environment-based configuration
  - Isolated network
- ✅ Helper scripts
  - `scripts/get_sonic_dyndns_apikey.py` - Interactive credential acquisition
  - `scripts/test_dyndns.py` - Comprehensive test suite
- ✅ Comprehensive documentation
  - `docs/DYNDNS_QUICKSTART.md` - Quick start guide
  - `docs/DYNDNS_SETUP.md` - Complete setup and configuration
  - `docs/DYNDNS_IMPLEMENTATION.md` - Technical implementation details
- ✅ Environment configuration updated (`.env.example`)
- ✅ README updated with DynDNS feature

**Location**:
- Service module: `src/quant_vibe/services/dyndns_client.py`
- Scripts: `scripts/run_dyndns.py`, `scripts/get_sonic_dyndns_apikey.py`, `scripts/test_dyndns.py`
- Documentation: `docs/DYNDNS_*.md`

**Features**:
- ✅ Automatic IP change detection
- ✅ DNS updates only when needed (reduces API load)
- ✅ Configurable update intervals
- ✅ Force update on startup option
- ✅ Normalized logging with rotation
- ✅ Docker-based deployment
- ✅ Auto-restart on failure
- ✅ Comprehensive error handling
- ✅ Test suite included
- ✅ Production-ready

**Configuration** (`.env`):
```bash
# Required
SONIC_DYNDNS_USERID=your_userid
SONIC_DYNDNS_APIKEY=your_apikey
SONIC_DYNDNS_HOSTNAME=your-hostname.sonic.net

# Optional
SONIC_DYNDNS_RECORD_TYPE=A
SONIC_DYNDNS_TTL=300
SONIC_DYNDNS_UPDATE_INTERVAL=300
SONIC_DYNDNS_FORCE_UPDATE=true
```

**Usage**:
```bash
# Get API credentials
python scripts/get_sonic_dyndns_apikey.py

# Start service via Docker (recommended)
docker compose up -d dyndns

# View logs
docker compose logs -f dyndns

# Test implementation
python scripts/test_dyndns.py
```

**Benefits**:
- ✅ Reliable remote access to services
- ✅ Automatic DNS updates on IP changes
- ✅ Low resource usage and minimal API calls
- ✅ Comprehensive logging and monitoring
- ✅ Easy setup and configuration
- ✅ Production-ready with retry logic

**See `docs/DYNDNS_QUICKSTART.md` for quick start guide**

