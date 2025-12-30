# Token Management Service

Centralized OAuth token management service for Schwab API authentication.

## Overview

The Token Management Service is a FastAPI microservice that centralizes OAuth token lifecycle management for all QuantVibe services. Instead of each service managing its own tokens, they all request tokens from this single service.

## Architecture

```
┌─────────────────────────────────────────────┐
│   token_service (FastAPI microservice)     │
│   - Centralized token storage & refresh    │
│   - REST API: GET /token, POST /refresh    │
│   - Auto-refresh background task           │
│   - Health monitoring                       │
│   - Redis pub/sub for token events         │
└─────────────────────────────────────────────┘
            ↓ provides tokens via HTTP
┌───────────┬──────────────┬──────────────────┐
│ streaming │ live_trading │ admin_ui         │
│ _service  │ _service     │                  │
└───────────┴──────────────┴──────────────────┘
            ↓ all use Schwab API
┌─────────────────────────────────────────────┐
│              Schwab API                     │
└─────────────────────────────────────────────┘
```

## Features

✅ **Single Source of Truth** - One service manages all tokens
✅ **Automatic Refresh** - Background task refreshes tokens every 14 minutes
✅ **Thread-Safe** - Concurrent requests handled safely
✅ **Event Publishing** - Publishes token events to Redis for coordination
✅ **Health Checks** - Docker health checks ensure service availability
✅ **Normalized Logging** - Consistent `[datetime][app][level][msg]` format
✅ **REST API** - Simple HTTP interface for other services

## API Endpoints

### Health Check
```http
GET /health
```

Returns service health status.

**Response**:
```json
{
  "status": "healthy",
  "service": "token_service",
  "has_token": true,
  "token_expired": false
}
```

### Get Token Status
```http
GET /token/status
```

Returns comprehensive token status including expiration info.

**Response**:
```json
{
  "has_token": true,
  "access_token_issued": "2025-12-30T10:00:00+00:00",
  "access_token_expires_at": "2025-12-30T10:30:00+00:00",
  "refresh_token_issued": "2025-12-30T10:00:00+00:00",
  "refresh_token_expires_at": "2026-01-06T10:00:00+00:00",
  "is_access_token_expired": false,
  "is_refresh_token_expired": false,
  "access_token_age_seconds": 420.5,
  "seconds_until_expiration": 1379.5,
  "expires_in": 1800,
  "token_type": "Bearer",
  "scope": "api"
}
```

### Get Access Token
```http
GET /token/access
```

Returns current access token with metadata.

**Response**:
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 1379,
  "issued_at": "2025-12-30T10:00:00+00:00",
  "expires_at": "2025-12-30T10:30:00+00:00"
}
```

**Error Responses**:
- `404 Not Found` - No token found in database
- `401 Unauthorized` - Token is expired

### Refresh Token
```http
POST /token/refresh
```

Manually trigger token refresh.

**Response**:
```json
{
  "success": true,
  "message": "Token refreshed successfully",
  "token_status": { ... }
}
```

**Error Responses**:
- `500 Internal Server Error` - Refresh failed

## Configuration

The service is configured via environment variables:

### Required Variables
```bash
# Schwab API credentials
SCHWAB_API_KEY=your_api_key
SCHWAB_API_SECRET=your_app_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
```

### Optional Variables
```bash
# Token service settings
TOKEN_SERVICE_HOST=0.0.0.0                    # Listen address
TOKEN_SERVICE_PORT=8001                       # Listen port
TOKEN_REFRESH_INTERVAL_MINUTES=14             # Auto-refresh interval

# Token storage
SCHWAB_TOKENS_DB=./tokens/schwabdev_tokens.db # Token database path

# Redis (for event publishing)
REDIS_HOST=localhost                          # Redis host
REDIS_PORT=6379                               # Redis port
REDIS_DB=0                                    # Redis database
TOKEN_SERVICE_ENABLE_REDIS=true               # Enable Redis events

# Logging
TOKEN_SERVICE_LOG_DIR=logs/token_service      # Log directory
TOKEN_SERVICE_LOG_LEVEL=INFO                  # Log level
```

## Running the Service

### Standalone (Development)
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -e ".[dev,schwab]"

# Run service
python scripts/run_token_service.py
```

The service will start on `http://localhost:8001`.

### Docker (Production)
```bash
# Start all services including token_service
docker-compose up -d

# View logs
docker-compose logs -f token_service

# Check health
curl http://localhost:8001/health
```

### Docker Service Configuration

The token_service is defined in `docker-compose.yml`:

```yaml
token_service:
  build:
    context: .
    dockerfile: docker/Dockerfile.streaming
  container_name: quant-vibe-token-service
  restart: unless-stopped
  ports:
    - "8001:8001"
  depends_on:
    redis:
      condition: service_healthy
  environment:
    SCHWAB_API_KEY: ${SCHWAB_API_KEY}
    SCHWAB_API_SECRET: ${SCHWAB_API_SECRET}
    TOKEN_SERVICE_HOST: 0.0.0.0
    TOKEN_SERVICE_PORT: 8001
    TOKEN_REFRESH_INTERVAL_MINUTES: 14
    REDIS_HOST: redis
    REDIS_PORT: 6379
    TOKEN_SERVICE_ENABLE_REDIS: "true"
  volumes:
    - .:/app
    - ./tokens:/app/tokens
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

## Client Usage

### Python Client

Use the provided `TokenServiceClient` to interact with the service:

```python
from token_service.client import TokenServiceClient

# Initialize client
client = TokenServiceClient("http://localhost:8001")

# Check if service is healthy
health = client.health_check()
print(health)  # {'status': 'healthy', ...}

# Get token status
status = client.get_token_status()
print(status)  # {'has_token': True, 'access_token_age_seconds': ...}

# Get access token
token = client.get_access_token()
print(token)  # "eyJhbGc..."

# Check if token is valid
is_valid = client.is_token_valid()
print(is_valid)  # True/False

# Manually refresh token
success = client.refresh_token()
print(success)  # True/False
```

### Convenience Function

For simple use cases:

```python
from token_service.client import get_token

# Get token in one line
token = get_token("http://localhost:8001")
print(token)  # "eyJhbGc..." or None
```

### Docker Environment

When running in Docker, use the service name as hostname:

```python
client = TokenServiceClient("http://token_service:8001")
token = client.get_access_token()
```

Set the `TOKEN_SERVICE_URL` environment variable in your service:

```yaml
environment:
  TOKEN_SERVICE_URL: http://token_service:8001
```

## Background Auto-Refresh

The service runs a background task that:
- Checks token expiration every 14 minutes (configurable)
- Refreshes token if it expires within 5 minutes
- Publishes refresh events to Redis (`token.refreshed`, `token.refresh_failed`)
- Logs all refresh activity

**Token Lifecycle**:
- Access tokens expire in 30 minutes (Schwab default)
- Refresh tokens expire in 7 days (Schwab default)
- Auto-refresh runs every 14 minutes (configurable)
- Refreshes when < 5 minutes remaining

## Redis Event Publishing

When Redis is enabled, the service publishes events:

### Token Refreshed
```python
topic = "token.refreshed"
data = {
    "timestamp": "2025-12-30T10:15:00+00:00",
    "status": "success",
    "manual": False  # True if triggered by POST /token/refresh
}
```

### Token Refresh Failed
```python
topic = "token.refresh_failed"
data = {
    "timestamp": None,
    "status": "failed",
    "manual": False
}
```

Other services can subscribe to these events to coordinate token updates.

## Token Storage

Tokens are stored in a SQLite database using schwabdev's format:

**Database**: `./tokens/schwabdev_tokens.db`

**Table**: `schwabdev`

**Schema**:
- `access_token` - OAuth access token
- `refresh_token` - OAuth refresh token
- `access_token_issued` - When access token was issued (ISO format)
- `refresh_token_issued` - When refresh token was issued (ISO format)
- `expires_in` - Access token expiration time in seconds (usually 1800)
- `token_type` - Token type (usually "Bearer")
- `scope` - Token scope
- `id_token` - OpenID Connect ID token

## Logging

The service uses normalized logging format:

```
[2025-12-30 10:00:00][token_service][INFO    ] Token Service Ready - Listening on 0.0.0.0:8001
[2025-12-30 10:14:00][token_service][INFO    ] Auto-refresh check triggered
[2025-12-30 10:14:00][token_service][INFO    ] Token needs refresh - refreshing now
[2025-12-30 10:14:01][token_service][INFO    ] Refreshing Schwab OAuth token...
[2025-12-30 10:14:02][token_service][INFO    ] ✓ Token refresh successful
[2025-12-30 10:14:02][token_service][INFO    ] Auto-refresh successful
```

**Log Location**: `logs/token_service/token_service_YYYYMMDD.log`

## Migration Guide

### From Direct schwabdev Usage

**Before** (each service manages its own tokens):
```python
import schwabdev

client = schwabdev.Client(
    app_key=os.getenv("SCHWAB_API_KEY"),
    app_secret=os.getenv("SCHWAB_API_SECRET"),
    callback_url=os.getenv("SCHWAB_CALLBACK_URL"),
    tokens_db="./tokens/schwabdev_tokens.db"
)

# Manually refresh tokens
client.update_tokens()
```

**After** (use token service):
```python
from token_service.client import TokenServiceClient

# Get token from centralized service
client = TokenServiceClient(os.getenv("TOKEN_SERVICE_URL", "http://localhost:8001"))
token = client.get_access_token()

# No need to refresh - token service handles it automatically
```

### Updating Services

1. Add `TOKEN_SERVICE_URL` environment variable
2. Import `TokenServiceClient`
3. Replace direct schwabdev usage with client calls
4. Remove local token refresh logic
5. Update Docker dependencies to include `token_service`

## Troubleshooting

### Token Database Not Found
```
⚠ No token found - authentication required
```

**Solution**: Run streaming service first to initialize Schwab OAuth and create token database.

### Service Unavailable
```
HTTPException: 503 Service Unavailable - Token manager not initialized
```

**Solution**: Check Schwab API credentials are set in environment variables.

### Token Expired
```
HTTPException: 401 Unauthorized - Access token is expired
```

**Solution**: Trigger manual refresh: `curl -X POST http://localhost:8001/token/refresh`

### Refresh Failed
```
Token refresh failed: [error details]
```

**Solution**: Check:
- Schwab API credentials are correct
- Refresh token hasn't expired (7 days)
- Network connectivity to Schwab API
- Token database file permissions

### Redis Connection Failed
```
Failed to connect to Redis: [error]
Continuing without Redis event publishing
```

**Solution**: Service continues without Redis. Fix Redis connection or set `TOKEN_SERVICE_ENABLE_REDIS=false`.

## Thread Safety

The `CentralizedTokenManager` is thread-safe:
- All public methods use a lock to protect concurrent access
- Safe to call from multiple threads/requests simultaneously
- Schwabdev client operations are serialized

## Security Considerations

1. **Access Tokens in Logs**: Tokens are never logged in full (redacted)
2. **Database Permissions**: Ensure token database has restrictive permissions
3. **Network Security**: Use HTTPS in production (TLS termination via reverse proxy)
4. **Token Sharing**: Tokens are shared across services - all services trust each other
5. **API Access**: No authentication on token service API (internal network only)

For production:
- Deploy behind a reverse proxy (nginx, traefik)
- Use TLS for all HTTP communication
- Restrict network access to internal services only
- Consider adding API authentication (JWT, API keys)

## Monitoring

Monitor the service using:

**Health Endpoint**:
```bash
curl http://localhost:8001/health
```

**Docker Health Checks**:
```bash
docker ps | grep token-service
# Should show "healthy" status
```

**Logs**:
```bash
# Docker
docker-compose logs -f token_service

# Standalone
tail -f logs/token_service/token_service_*.log
```

**Metrics to Monitor**:
- Token refresh success/failure rate
- Token age (should reset every 14 minutes)
- Service uptime
- Response times
- Redis event publishing success

## Future Enhancements

Potential improvements:
- [ ] Support for multiple broker APIs (not just Schwab)
- [ ] Token encryption at rest
- [ ] API authentication (JWT, API keys)
- [ ] Metrics/Prometheus endpoint
- [ ] Token rotation policies
- [ ] WebSocket endpoint for real-time token events
- [ ] Admin UI integration (token status widget)
- [ ] Alerting for token expiration
- [ ] Multi-user support (per-user tokens)

## See Also

- [Schwab API Documentation](https://developer.schwab.com/)
- [schwabdev Library](https://github.com/tylerebowers/Schwab-API-Python)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Redis Pub/Sub](https://redis.io/docs/manual/pubsub/)
