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
- [ ] Migrate streaming_service to use token_service (see below)
- [ ] Migrate live_trading_service to use token_service (see below)
- [ ] Update admin_ui to use token_service API
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

**Documentation**: See `docs/TOKEN_SERVICE.md` for complete guide

## Migrate services to use centralized token_service

### streaming_service migration
**Status**: Pending

Update streaming service to get tokens from token_service instead of managing its own:

**Changes needed**:
1. Replace direct `schwabdev.Client` initialization with `TokenServiceClient`
2. Remove local `TokenManager` class (in `src/streaming_service/token_manager.py`)
3. Update token refresh logic to use HTTP client
4. Add `TOKEN_SERVICE_URL` environment variable support
5. Update error handling for token service unavailable

**Steps**:
```python
# Before
self.schwab_client = schwabdev.Client(...)
self.token_manager = TokenManager(self.schwab_client)

# After
from token_service.client import TokenServiceClient
self.token_client = TokenServiceClient(os.getenv("TOKEN_SERVICE_URL"))
token = self.token_client.get_access_token()
# Use token with schwabdev or directly with requests
```

### live_trading_service migration
**Status**: Pending

Update live trading service to get tokens from token_service:

**Changes needed**:
1. Replace direct `schwabdev.Client` token handling
2. Use `TokenServiceClient` for token retrieval
3. Add token refresh fallback logic
4. Update Docker dependencies

### admin_ui migration
**Status**: Pending

Update admin UI to use token_service API instead of reading database directly:

**Changes needed**:
1. Replace `get_token_from_db()` with `TokenServiceClient` calls
2. Update `/api/tokens/status` endpoint to proxy to token_service
3. Update `/api/tokens/refresh` endpoint to proxy to token_service
4. Remove direct SQLite database access

## Implement notifcations/emails/sms system

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

