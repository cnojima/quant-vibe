# Quant-Vibe Admin UI

Web-based administration interface for managing the Quant-Vibe trading system.

## Quick Reference

### 🚀 Getting Started

**Production (Docker)**:
```bash
# Start all services including nginx frontend
docker-compose up -d
```

Access at: **http://localhost** (nginx on port 80)

**Development (Local)**:
```bash
# One-command startup (backend + frontend)
./scripts/start_admin_ui_dev.sh
```

This starts:
- **Backend** (FastAPI): http://localhost:8000
- **Frontend** (React + Vite): http://localhost:5173

Login with credentials from `.env`:
- Username: `ADMIN_USERNAME`
- Password: `ADMIN_PASSWORD`

### 📦 Manual Setup

```bash
# Install backend dependencies
pip install -e ".[admin_ui]"

# Install frontend dependencies
cd src/admin_ui/frontend
npm install
```

### 🔧 Development Workflow

**Backend only**:
```bash
python scripts/run_admin_ui.py --reload
```

**Frontend only**:
```bash
cd src/admin_ui/frontend && npm run dev
```

**Production build**:
```bash
cd src/admin_ui/frontend
npm run build  # Output: dist/
```

## Overview

The Admin UI provides a centralized interface to:
- **Manage services** - Start, stop, restart streaming and live trading services via Docker API
- **Monitor live trading** - View real-time positions, orders, P&L, and strategy execution
- **Manage Schwab tokens** - View token status and refresh OAuth tokens
- **Execute backtests** - Run backtests with custom parameters and view results
- **Configure system** - Edit YAML configuration files for backtest and live trading
- **Monitor health** - Check system status, connectivity, and service heartbeats

## Architecture

### Backend (FastAPI)

**Location**: `src/admin_ui/backend/`

**Components**:
- `main.py` - FastAPI application entry point
- `config.py` - Configuration management
- `auth.py` - JWT authentication
- `db/timescale.py` - TimescaleDB queries
- `redis_client.py` - Redis pub/sub and WebSocket broadcasting
- `docker/manager.py` - Docker API wrapper
- `api/` - REST API endpoints
  - `auth.py` - Login/logout endpoints
  - `services.py` - Service control (start/stop/logs)
  - `status.py` - Health checks and connectivity
  - `tokens.py` - Schwab token management
  - `live.py` - Live trading monitoring
  - `backtests.py` - Backtest execution
  - `config.py` - Configuration management

**Technology Stack**:
- **FastAPI** - Modern async web framework
- **Uvicorn** - ASGI server
- **asyncpg** - Async PostgreSQL driver
- **redis** - Redis client for pub/sub
- **python-docker** - Docker API client
- **python-jose** - JWT token handling
- **passlib** - Password hashing

### Frontend (React)

**Location**: `src/admin_ui/frontend/`

**Technology Stack**:
- **React 18** - UI framework
- **TypeScript** - Type safety
- **React Router** - Routing
- **TanStack Query** - Data fetching and caching
- **Axios** - HTTP client
- **Recharts** - Charts for backtest results
- **Vite** - Build tool
- **nginx** - Production web server (Docker only)

**Deployment Architecture**:

```
┌─────────────────────────────────────────────────────────┐
│                     Production (Docker)                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────┐                                │
│  │  Browser (Port 80)  │                                │
│  └──────────┬──────────┘                                │
│             │                                            │
│             v                                            │
│  ┌──────────────────────────────────────────┐          │
│  │  nginx (admin_ui_frontend container)     │          │
│  │  - Serves static React build (dist/)     │          │
│  │  - Proxies /api → admin_ui:8000          │          │
│  │  - Proxies /ws → admin_ui:8000           │          │
│  │  - Handles SPA routing (fallback)        │          │
│  └──────────────────┬───────────────────────┘          │
│                     │                                    │
│                     v                                    │
│  ┌──────────────────────────────────────────┐          │
│  │  FastAPI (admin_ui container)            │          │
│  │  - REST API endpoints                    │          │
│  │  - WebSocket events                      │          │
│  │  - Docker service control                │          │
│  └──────────────────────────────────────────┘          │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**Benefits**:
- ✅ Single entry point on port 80
- ✅ No CORS issues (same origin)
- ✅ Production-optimized React build
- ✅ Static asset caching and compression
- ✅ WebSocket support
- ✅ SPA routing handled by nginx

## Installation

### Prerequisites

- Python 3.9+
- Docker and Docker Compose (for service control)
- TimescaleDB and Redis running
- Access to Docker socket (for service management)

### Install Dependencies

```bash
# Install admin UI dependencies
pip install -e ".[admin_ui]"

# Or install all dependencies
pip install -e ".[all]"
```

### Environment Variables

Add to your `.env` file:

```bash
# Admin UI Security
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
JWT_SECRET_KEY=your-secret-key-min-32-chars

# Optional: Override defaults
REDIS_HOST=localhost
REDIS_PORT=6379
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
```

**Security Notes**:
- Change `ADMIN_PASSWORD` from default
- Use a strong random string for `JWT_SECRET_KEY` (min 32 characters)
- For production, hash the password using bcrypt:
  ```bash
  python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-password'))"
  ```

## Usage

### Running the Backend Server

#### Development Mode (Local)

```bash
# Run with auto-reload
python scripts/run_admin_ui.py --reload

# Run on custom port
python scripts/run_admin_ui.py --port 8080

# Run with debug logging
python scripts/run_admin_ui.py --log-level debug
```

**Backend runs on**: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

#### Production Mode (Docker)

**Start all services** (backend + nginx frontend):
```bash
# Build and start all services
docker-compose up -d

# Or build with fresh images
docker-compose up -d --build
```

This starts:
- **Backend** (admin_ui): http://localhost:8000
- **Frontend** (admin_ui_frontend): http://localhost:80

**Start individual services**:
```bash
# Start just backend (requires redis and timescaledb running)
docker-compose up -d admin_ui

# Start just frontend (requires backend running)
docker-compose up -d admin_ui_frontend
```

**View logs**:
```bash
# Backend logs
docker-compose logs -f admin_ui

# Frontend (nginx) logs
docker-compose logs -f admin_ui_frontend

# Both
docker-compose logs -f admin_ui admin_ui_frontend
```

**Rebuild after code changes**:
```bash
# Rebuild backend
docker-compose up -d --build admin_ui

# Rebuild frontend (after npm run build)
docker-compose up -d --build admin_ui_frontend

# Rebuild both
docker-compose up -d --build admin_ui admin_ui_frontend
```

**Stop services**:
```bash
# Stop frontend
docker-compose stop admin_ui_frontend

# Stop backend
docker-compose stop admin_ui

# Stop all services
docker-compose down
```

### Running the Frontend (React)

The frontend is a separate React application that runs alongside the backend.

#### Development Mode

```bash
# Navigate to frontend directory
cd src/admin_ui/frontend

# Install dependencies (first time only)
npm install

# Start development server with hot reload
npm run dev
```

**Frontend runs on**: http://localhost:5173
- Automatically proxies API requests to http://localhost:8000
- Hot module replacement (HMR) enabled
- TypeScript type checking

**Important**: Both backend and frontend must be running:
1. **Terminal 1**: `python scripts/run_admin_ui.py --reload` (backend)
2. **Terminal 2**: `cd src/admin_ui/frontend && npm run dev` (frontend)

#### Production Build

```bash
cd src/admin_ui/frontend

# Build optimized production bundle
npm run build

# Preview production build locally
npm run preview

# Output: dist/ directory (ready for deployment)
```

**Production Deployment**:
- Serve `dist/` folder with nginx, Apache, or CDN
- Configure reverse proxy to backend API
- Set `VITE_API_URL` environment variable if backend is on different domain

### Quick Start (Development)

**Option 1: One-Command Startup (Easiest)**
```bash
# Start both backend and frontend with one script
./scripts/start_admin_ui_dev.sh
```

This script:
- Checks and installs dependencies if needed
- Starts backend on http://localhost:8000
- Starts frontend on http://localhost:5173
- Runs both with hot reload enabled
- Press Ctrl+C to stop both services

**Option 2: Separate Terminals (Manual)**
```bash
# Terminal 1: Start backend
python scripts/run_admin_ui.py --reload

# Terminal 2: Start frontend
cd src/admin_ui/frontend && npm run dev
```

**Option 3: Using tmux/screen**
```bash
# Create split terminal
tmux new -s admin-ui

# Left pane: backend
python scripts/run_admin_ui.py --reload

# Right pane: frontend (Ctrl+B, %)
cd src/admin_ui/frontend && npm run dev
```

### Accessing the UI

**Production (Docker with nginx)**:
- **Main UI**: http://localhost (nginx serving React build)
- **API**: Proxied through nginx at http://localhost/api
- **Docs**: http://localhost/docs
- **Health**: http://localhost/health

**Development (Vite dev server)**:
- **Main UI**: http://localhost:5173 (React + HMR)
- **Login**: http://localhost:5173/login
- **Dashboard**: http://localhost:5173/dashboard

**Backend (Direct Access)**:
- **API Documentation**: http://localhost:8000/docs (Swagger UI)
- **Alternative Docs**: http://localhost:8000/redoc (ReDoc)
- **Health Check**: http://localhost:8000/health
- **WebSocket**: ws://localhost:8000/ws/events

## API Endpoints

### Authentication

**POST /api/auth/login**
- Body: `{"username": "admin", "password": "your-password"}`
- Returns: JWT access token
- Use token in header: `Authorization: Bearer <token>`

**POST /api/auth/logout**
- Logout current user (primarily client-side token removal)

**GET /api/auth/me**
- Get current user info

**GET /api/auth/verify**
- Verify token validity

### Service Control

**GET /api/services**
- List all services and their status

**GET /api/services/{service_name}**
- Get specific service status

**POST /api/services/{service_name}/start**
- Start a service

**POST /api/services/{service_name}/stop**
- Stop a service
- Body (optional): `{"timeout": 10}`

**POST /api/services/{service_name}/restart**
- Restart a service
- Body (optional): `{"timeout": 10}`

**GET /api/services/{service_name}/logs**
- Get service logs
- Query params: `?tail=100` (default: 100 lines)

### Status Monitoring

**GET /api/status/health**
- Overall system health (database, Redis, Docker)

**GET /api/status/redis**
- Redis connectivity status

**GET /api/status/database**
- TimescaleDB connectivity status

**GET /api/status/docker**
- Docker daemon connectivity status

**GET /api/status/heartbeats**
- Last heartbeat from each service

### Schwab Token Management

**GET /api/tokens/status**
- Get token status (age, expiration, validity)

**POST /api/tokens/refresh**
- Manually refresh tokens (MVP: placeholder)

**GET /api/tokens/oauth-url**
- Get OAuth URL for re-authentication (MVP: placeholder)

**POST /api/tokens/oauth-callback**
- Handle OAuth callback (MVP: placeholder)

### Live Trading Monitoring

**GET /api/live/status**
- Get live trading engine status

**GET /api/live/positions**
- Get positions
- Query params: `?status=open|closed|all&limit=100`

**GET /api/live/orders**
- Get open orders
- Query params: `?limit=100`

**GET /api/live/events**
- Get recent events
- Query params: `?limit=100&event_type=signal&severity=error`

**GET /api/live/stats**
- Get aggregate trading statistics
- Query params: `?start_time=ISO8601&end_time=ISO8601`

### Backtest Execution

**GET /api/backtests/strategies**
- List available strategies

**POST /api/backtests/run**
- Run a backtest (async)
- Body:
  ```json
  {
    "strategy_name": "bullish_vertical_put",
    "start_date": "2025-12-01T00:00:00Z",
    "end_date": "2025-12-12T00:00:00Z",
    "parameters": {"spread_width": 20.0}
  }
  ```
- Returns: `{"backtest_id": "...", "status": "pending"}`

**GET /api/backtests/{backtest_id}/status**
- Check backtest status

**GET /api/backtests/{backtest_id}/results**
- Get backtest results (trades and equity curve)

**GET /api/backtests/history**
- Get history of past backtests
- Query params: `?limit=50`

### Configuration Management

**GET /api/config/list**
- List all configuration files

**GET /api/config/backtest**
- Get backtest configuration

**PUT /api/config/backtest**
- Update backtest configuration
- Body: `{"config": {...}}`

**GET /api/config/live**
- Get live trading configuration

**PUT /api/config/live**
- Update live trading configuration
- Body: `{"config": {...}}`

### WebSocket

**WS /ws/events**
- Real-time event stream
- Receives messages from Redis pub/sub:
  - `streaming.*` - Market data events
  - `trading.*` - Trading signals/orders
  - `system.*` - System heartbeats/errors
- Send `"ping"` to receive `{"type": "pong"}`

## Database Schema

Admin UI queries the following TimescaleDB tables:

**live_engine_state**
- Latest engine state (RUNNING/STOPPED)
- Bars processed, signals generated
- Uptime and metadata

**live_positions**
- Active and closed positions
- Entry/exit times, costs, P&L
- Position legs (JSONB)

**live_orders**
- Open and closed orders
- Order type, status, timestamps
- Symbol, quantity, limit price

**live_events**
- Event log (signals, orders, errors)
- Timestamp, event type, severity
- Message and metadata

## Docker Integration

### Service Names

The Docker manager can control these services:
- `streaming` - Streaming service
- `live_trading` - Live trading engine
- `timescaledb` - Database
- `redis` - Redis cache
- `admin_ui` - Admin UI backend (FastAPI)
- `admin_ui_frontend` - Admin UI frontend (nginx)

### Docker Socket Access

The admin UI requires access to the Docker socket to control services:

**Local Development**:
- Docker socket: `unix:///var/run/docker.sock`
- Automatically detected by docker-py

**Docker Container**:
- Mount socket: `-v /var/run/docker.sock:/var/run/docker.sock`
- Already configured in `docker-compose.admin.yml`

### Container Naming

The Docker manager tries these naming patterns:
1. Exact name: `streaming`
2. With prefix: `quant-vibe_streaming_1`

## Security

### Authentication

- **Method**: JWT tokens
- **Algorithm**: HS256
- **Expiration**: 24 hours (configurable)
- **Storage**: Client-side (localStorage or cookies)

### Authorization

- **MVP**: Single admin user (configured in .env)
- **Future**: Role-based access control (RBAC)

### Best Practices

1. **Change default credentials** in `.env`
2. **Use strong JWT secret** (min 32 characters)
3. **Enable HTTPS** in production (use reverse proxy)
4. **Restrict CORS origins** to trusted domains
5. **Firewall port 8000** if exposing publicly
6. **Use Docker secrets** for sensitive data

## Development

### Project Structure

```
src/admin_ui/
├── __init__.py
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI app
│   ├── config.py            # Settings
│   ├── auth.py              # Authentication
│   ├── redis_client.py      # Redis pub/sub
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── services.py
│   │   ├── status.py
│   │   ├── tokens.py
│   │   ├── live.py
│   │   ├── backtests.py
│   │   └── config.py
│   ├── db/
│   │   ├── __init__.py
│   │   └── timescale.py     # Database queries
│   ├── docker/
│   │   ├── __init__.py
│   │   └── manager.py       # Docker API
│   └── schemas/             # Pydantic models
└── frontend/                # React app (future)
    ├── package.json
    ├── src/
    │   ├── components/
    │   ├── pages/
    │   ├── api/
    │   ├── hooks/
    │   └── App.tsx
    └── README.md
```

### Adding New Endpoints

1. Create endpoint in `backend/api/<module>.py`
2. Add router to `main.py`: `app.include_router(...)`
3. Document in this file
4. Add tests (future)

### Testing

```bash
# Start server
python scripts/run_admin_ui.py

# Visit http://localhost:8000/docs
# Use Swagger UI to test endpoints interactively

# Test authentication
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'

# Use token in subsequent requests
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/services
```

## Troubleshooting

### Frontend Issues

**npm install fails**:
- Check Node.js version: `node --version` (requires v18+)
- Clear npm cache: `npm cache clean --force`
- Delete `node_modules` and `package-lock.json`, retry

**Frontend won't start (EADDRINUSE)**:
- Port 5173 is already in use
- Kill existing process: `lsof -ti:5173 | xargs kill -9`
- Or use different port: `npm run dev -- --port 3000`

**API requests fail (CORS errors)**:
- Ensure backend is running on port 8000
- Check Vite proxy configuration in `vite.config.ts`
- Verify CORS settings in backend `main.py`

**TypeScript errors**:
- Run type checking: `npm run type-check`
- Regenerate types: `npm run build`
- Check `tsconfig.json` configuration

**Hot reload not working**:
- Check file watcher limits: `echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p`
- Restart Vite dev server
- Clear browser cache

**Chart not displaying data**:
- Open browser console (F12) and check for errors
- Verify API response in Network tab
- Check data format matches TypeScript interfaces

### Backend Connection Errors

**Database connection failed**:
- Check TimescaleDB is running: `docker ps | grep timescale`
- Verify credentials in `.env`
- Check network: `docker network ls | grep quant-vibe`

**Redis connection failed**:
- Check Redis is running: `docker ps | grep redis`
- Verify host/port in `.env`
- Test connection: `redis-cli ping`

**Docker connection failed**:
- Check Docker daemon: `docker ps`
- Verify socket access: `ls -la /var/run/docker.sock`
- Check permissions (user must be in `docker` group)

### Authentication Issues

**Login fails**:
- Verify username/password in `.env`
- Check JWT_SECRET_KEY is set
- Review logs: `python scripts/run_admin_ui.py --log-level debug`

**Token expired**:
- Default expiration: 24 hours
- Re-login to get new token
- Adjust `access_token_expire_minutes` in `config.py`

### Service Control Issues

**Cannot start/stop services**:
- Verify Docker socket access
- Check container names: `docker ps -a`
- Review Docker manager logs
- Ensure services exist in docker-compose.yml

## Roadmap

### MVP (Completed)
- ✅ FastAPI backend with all API endpoints
- ✅ JWT authentication
- ✅ Docker service control
- ✅ Live trading monitoring
- ✅ Backtest execution
- ✅ Configuration management
- ✅ WebSocket real-time updates
- ✅ Health checks and status monitoring

### Phase 2 (Completed)
- ✅ React frontend implementation
- ✅ Token management UI
- ✅ Live trading dashboard with real-time updates
- ✅ Backtest results visualization with charts
  - ✅ Equity curve chart
  - ✅ Dual-axis overlay (portfolio + underlying price)
  - ✅ P&L distribution chart
  - ✅ Drawdown chart
  - ✅ Trade history table
- ✅ Service management dashboard
- ✅ Service uptime tracking
- ✅ Configuration editor UI

### Phase 3 (Future)
- ⬜ Service logs viewer (real-time)
- ⬜ Advanced chart customization
  - ⬜ Zoom/pan on equity curve
  - ⬜ Trade markers on chart
  - ⬜ Indicator overlays
- ⬜ Multi-user support with RBAC
- ⬜ Notification system (email/SMS)
- ⬜ Strategy deployment pipeline
- ⬜ Performance analytics dashboard
- ⬜ Audit logging
- ⬜ API rate limiting

## Contributing

To contribute to the Admin UI:

1. Follow existing code patterns
2. Add type hints to all functions
3. Update documentation
4. Test all endpoints manually
5. Follow security best practices

## License

Part of the Quant-Vibe trading system.
