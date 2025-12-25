# Admin UI Service

Web-based administration interface for the Quant-Vibe trading system.

## Quick Start

### Install Dependencies

```bash
pip install -e ".[admin_ui]"
```

### Set Environment Variables

Add to `.env`:

```bash
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
JWT_SECRET_KEY=your-secret-key-min-32-chars
```

### Run the Server

```bash
# Development mode with auto-reload
python scripts/run_admin_ui.py --reload

# Production mode
python scripts/run_admin_ui.py
```

### Access the API

- **Swagger Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **WebSocket**: ws://localhost:8000/ws/events

## Features

### Service Management
- Start, stop, restart services via Docker API
- View service logs
- Monitor service health

### Live Trading Monitoring
- View real-time positions and P&L
- Track open orders
- Monitor strategy execution
- View event logs

### Schwab Token Management
- View token status and expiration
- Refresh tokens manually
- Re-authenticate via OAuth (future)

### Backtest Execution
- Run backtests with custom parameters
- View results and equity curves
- Compare multiple strategies
- Access historical backtest data

### Configuration Management
- View and edit backtest.yaml
- View and edit live_trading.yaml
- Backup configurations automatically

### System Monitoring
- Check database connectivity
- Monitor Redis status
- Verify Docker daemon
- Track service heartbeats

## Architecture

```
admin_ui/
├── backend/                # FastAPI backend
│   ├── main.py            # App entry point
│   ├── config.py          # Settings
│   ├── auth.py            # JWT authentication
│   ├── redis_client.py    # Pub/sub & WebSocket
│   ├── api/               # REST endpoints
│   ├── db/                # Database queries
│   └── docker/            # Docker API wrapper
└── frontend/              # React frontend (future)
    └── src/
```

## API Endpoints

All endpoints require authentication except `/health` and `/api/auth/login`.

### Authentication
- `POST /api/auth/login` - Login and get JWT token
- `GET /api/auth/me` - Get current user

### Services
- `GET /api/services` - List all services
- `POST /api/services/{name}/start` - Start service
- `POST /api/services/{name}/stop` - Stop service
- `GET /api/services/{name}/logs` - Get logs

### Live Trading
- `GET /api/live/status` - Engine status
- `GET /api/live/positions` - Active positions
- `GET /api/live/orders` - Open orders
- `GET /api/live/events` - Recent events
- `GET /api/live/stats` - Trading statistics

### Backtests
- `POST /api/backtests/run` - Execute backtest
- `GET /api/backtests/{id}/status` - Check status
- `GET /api/backtests/{id}/results` - Get results

### Configuration
- `GET /api/config/backtest` - Get backtest config
- `PUT /api/config/backtest` - Update backtest config
- `GET /api/config/live` - Get live config
- `PUT /api/config/live` - Update live config

### Status
- `GET /api/status/health` - System health
- `GET /api/status/redis` - Redis status
- `GET /api/status/database` - Database status

### Tokens
- `GET /api/tokens/status` - Token status
- `POST /api/tokens/refresh` - Refresh tokens

## WebSocket Events

Connect to `ws://localhost:8000/ws/events` to receive real-time updates:

- `streaming.*` - Market data events
- `trading.*` - Trading signals and orders
- `system.*` - System heartbeats and errors

## Security

- JWT token authentication (24-hour expiration)
- Password hashing with bcrypt
- CORS protection
- Docker socket access required for service control

## Docker

Run via Docker Compose:

```bash
docker-compose -f docker-compose.admin.yml up -d
```

## Documentation

See [docs/ADMIN_UI.md](../../docs/ADMIN_UI.md) for complete documentation.

## Development

```bash
# Run with debug logging
python scripts/run_admin_ui.py --log-level debug --reload

# Format code
black src/admin_ui

# Lint
ruff check src/admin_ui
```

## Troubleshooting

**Cannot connect to database**:
- Verify TimescaleDB is running
- Check credentials in `.env`

**Cannot control services**:
- Verify Docker daemon is running
- Check Docker socket permissions
- Ensure user is in `docker` group

**WebSocket disconnects**:
- Check Redis connectivity
- Review server logs

For more help, see [docs/ADMIN_UI.md](../../docs/ADMIN_UI.md)
