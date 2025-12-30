# Admin UI Quick Start Guide

Get the Quant-Vibe Admin UI up and running in 5 minutes.

## Prerequisites

- Python 3.9+
- Docker and Docker Compose running
- TimescaleDB and Redis containers running
- Quant-Vibe project installed

## Step 1: Install Dependencies

```bash
cd /Users/curisu/dev/quant-vibe

# Install admin UI dependencies
pip install -e ".[admin_ui]"
```

## Step 2: Configure Environment

Add these variables to your `.env` file:

```bash
# Admin UI Credentials (CHANGE THESE!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
JWT_SECRET_KEY=your-random-secret-key-min-32-characters-long

# Optional: Override defaults if needed
# REDIS_HOST=localhost
# REDIS_PORT=6379
# TIMESCALE_HOST=localhost
# TIMESCALE_PORT=5432
```

**Security**: Change the default password and generate a strong JWT secret:

```bash
# Generate a random secret key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Or hash your password with bcrypt
python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('your-password'))"
```

## Step 3: Start the Server

### Option A: Local Development

```bash
# Start with auto-reload (for development)
python scripts/run_admin_ui.py --reload

# Or without reload (for testing)
python scripts/run_admin_ui.py
```

### Option B: Docker (Recommended)

```bash
# Start all services including admin UI
docker-compose up -d

# Or start just the admin UI (requires redis and timescaledb)
docker-compose up -d admin_ui

# View logs
docker-compose logs -f admin_ui
```

## Step 4: Access the UI

Open your browser to:

- **API Documentation**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## Step 5: Test the API

### 1. Login

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"changeme"}'
```

Response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "user": {"username": "admin"}
}
```

### 2. List Services

```bash
TOKEN="your-token-from-login"

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/services
```

### 3. Check Live Trading Status

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/live/status
```

### 4. View Positions

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/live/positions?status=open
```

## Using the Swagger UI

The easiest way to explore the API is via the Swagger UI:

1. Go to http://localhost:8000/docs
2. Click "Authorize" button (top right)
3. Login at `/api/auth/login` endpoint
4. Copy the `access_token` from the response
5. Paste it in the Authorize dialog
6. Click "Authorize"
7. Now you can test all endpoints interactively!

## Common Use Cases

### Start a Service

1. Go to `/api/services/{service_name}/start`
2. Enter service name: `streaming` or `live_trading`
3. Click "Execute"

### Run a Backtest

1. Go to `/api/backtests/run`
2. Fill in the request body:
   ```json
   {
     "strategy_name": "bullish_vertical_put",
     "start_date": "2025-12-01T00:00:00Z",
     "end_date": "2025-12-12T00:00:00Z",
     "parameters": {}
   }
   ```
3. Click "Execute"
4. Note the `backtest_id` in response
5. Check status at `/api/backtests/{backtest_id}/status`

### View Configuration

1. Go to `/api/config/backtest` or `/api/config/live`
2. Click "Execute"
3. View the current configuration
4. To update, use the PUT endpoint with the modified config

## WebSocket Connection

Connect to real-time events:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/events');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data);
};

// Send ping
ws.send('ping');
```

## Troubleshooting

### Server won't start

**Error**: `Database pool not initialized`
- **Solution**: Make sure TimescaleDB is running: `docker ps | grep timescale`

**Error**: `Redis not initialized`
- **Solution**: Make sure Redis is running: `docker ps | grep redis`

### Authentication fails

**Error**: `Incorrect username or password`
- **Solution**: Check credentials in `.env` file
- Verify you're using the correct username/password

### Cannot control services

**Error**: `Failed to initialize Docker client`
- **Solution**: Make sure Docker daemon is running: `docker ps`
- Check permissions: User must be in `docker` group or have socket access

### WebSocket disconnects

- Check that Redis is running and accessible
- Review server logs for errors
- Ensure firewall isn't blocking WebSocket connections

## Next Steps

- Read the [full documentation](ADMIN_UI.md)
- Explore all API endpoints in Swagger UI
- Set up the React frontend (future)
- Configure production deployment
- Enable HTTPS with reverse proxy (nginx/traefik)

## Getting Help

- Review logs: `python scripts/run_admin_ui.py --log-level debug`
- Check Docker logs: `docker-compose logs admin_ui`
- See [ADMIN_UI.md](ADMIN_UI.md) for detailed troubleshooting

## Security Checklist

Before deploying to production:

- [ ] Changed default admin password
- [ ] Generated strong JWT secret (32+ characters)
- [ ] Enabled HTTPS (reverse proxy)
- [ ] Configured firewall rules
- [ ] Restricted CORS origins
- [ ] Set up backup strategy
- [ ] Enabled audit logging
- [ ] Reviewed Docker socket permissions
