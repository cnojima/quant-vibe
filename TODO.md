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

**Pending**:
- [x] Migrate streaming_service to use token_service ✅
- [x] Migrate live_trading_service to use token_service ✅
- [x] Update admin_ui to use token_service API ✅
- [ ] Write comprehensive tests

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

## Implement watcher/heartbeat monitoring

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

