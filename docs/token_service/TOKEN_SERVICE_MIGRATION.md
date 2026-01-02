# Token Service Migration Summary

This document summarizes the migration of all services to use the centralized token_service.

## Overview

All QuantVibe services have been migrated to use the centralized `token_service` for OAuth token management. This eliminates duplicate token refresh logic and provides a single, reliable source for Schwab API authentication.

## Migration Status

### ✅ Completed Migrations

#### 1. **token_service** - Centralized Service (NEW)
**Location**: `src/token_service/`

**Implementation**:
- ✅ Core `CentralizedTokenManager` with thread-safe token operations
- ✅ FastAPI service with REST API
- ✅ Background auto-refresh task (runs every 14 minutes)
- ✅ Redis event publishing
- ✅ HTTP client library (`TokenServiceClient`)
- ✅ Docker configuration
- ✅ Comprehensive documentation

**API Endpoints**:
- `GET /health` - Service health check
- `GET /token/status` - Get token status
- `GET /token/access` - Get current access token
- `POST /token/refresh` - Manually trigger refresh

**Docker**:
- Service: `token_service`
- Port: 8100
- Health checks: Every 30 seconds
- Auto-refresh: Every 14 minutes

#### 2. **streaming_service** - Data Streaming
**Location**: `src/streaming_service/`

**Changes Made**:
- ✅ Added `token_service_url` and `use_token_service` to config
- ✅ Added `TokenServiceClient` import with fallback handling
- ✅ Conditional initialization: token service vs. legacy mode
- ✅ Updated token refresh logic in `start()` method
- ✅ Updated main loop to use token service status
- ✅ Graceful fallback to legacy `TokenManager` if token service unavailable

**Configuration**:
```yaml
# Environment variable
TOKEN_SERVICE_URL=http://token_service:8100
```

**Behavior**:
- If `TOKEN_SERVICE_URL` is set → Uses centralized token service
- If token service unavailable → Falls back to legacy local token database
- Token service handles auto-refresh → No manual refresh needed in main loop

**Files Modified**:
- `src/streaming_service/config.py` - Added token service config
- `src/streaming_service/service.py` - Integrated token service client

#### 3. **live_trading_service** - Trading Engine
**Location**: `src/live_trading_service/`

**Changes Made**:
- ✅ Added `TokenServiceClient` import with fallback handling
- ✅ Added `use_token_service` and `token_service_url` to engine state
- ✅ Conditional initialization: token service vs. legacy mode
- ✅ Health check on startup
- ✅ Graceful fallback to legacy schwabdev token management

**Configuration**:
```yaml
# Environment variable
TOKEN_SERVICE_URL=http://token_service:8100

# config/live_trading.yaml
engine:
  use_token_service: true  # Enable token service (default)
```

**Behavior**:
- If token service is available → Connects and logs "tokens via token service"
- If token service unavailable → Falls back to "tokens via local database"
- schwabdev.Client still handles local token file for backward compatibility

**Files Modified**:
- `src/live_trading_service/engine.py` - Integrated token service client

#### 4. **admin_ui** - Admin Dashboard
**Location**: `src/admin_ui/backend/api/`

**Changes Made**:
- ✅ Added `TokenServiceClient` import
- ✅ Added `USE_TOKEN_SERVICE` and `TOKEN_SERVICE_URL` config
- ✅ Updated `/api/tokens/status` - Proxies to token service first, falls back to database
- ✅ Updated `/api/tokens/refresh` - Proxies to token service first, falls back to schwabdev
- ✅ Added `source` field to responses ("token_service" vs. "local_database")

**Configuration**:
```yaml
# Environment variables
USE_TOKEN_SERVICE=true  # Enable token service proxy (default)
TOKEN_SERVICE_URL=http://token_service:8100
```

**Behavior**:
- If token service available → Proxies requests to token service
- If token service unavailable → Falls back to reading SQLite database directly
- Response includes `source` field indicating which method was used

**Files Modified**:
- `src/admin_ui/backend/api/tokens.py` - Proxied endpoints to token service

## Architecture

### Before Migration
```
┌───────────────┐  ┌──────────────┐  ┌──────────────┐
│  streaming    │  │ live_trading │  │   admin_ui   │
│   service     │  │   service    │  │              │
│               │  │              │  │              │
│ TokenManager  │  │ schwabdev    │  │  SQLite DB   │
│ (local)       │  │ (local)      │  │  (direct)    │
└───────┬───────┘  └──────┬───────┘  └──────┬───────┘
        │                 │                  │
        └─────────────────┴──────────────────┘
                          ↓
                  ┌───────────────┐
                  │  Schwab API   │
                  └───────────────┘
```

**Issues**:
- ❌ Duplicate token refresh logic across services
- ❌ No centralized monitoring
- ❌ Difficult to coordinate token updates
- ❌ Each service manages its own refresh timing

### After Migration
```
┌─────────────────────────────────────────────┐
│        token_service (Centralized)          │
│  - Auto-refresh every 14 minutes            │
│  - REST API for token access                │
│  - Redis event publishing                   │
│  - Thread-safe concurrent access            │
└─────────────────┬───────────────────────────┘
                  │ HTTP (port 8100)
        ┌─────────┴──────────┬────────────────┐
        ↓                    ↓                 ↓
┌───────────────┐  ┌──────────────┐  ┌──────────────┐
│  streaming    │  │ live_trading │  │   admin_ui   │
│   service     │  │   service    │  │              │
│               │  │              │  │              │
│ TokenService  │  │ TokenService │  │ TokenService │
│   Client      │  │   Client     │  │   Proxy      │
└───────────────┘  └──────────────┘  └──────────────┘
```

**Benefits**:
- ✅ Single source of truth for tokens
- ✅ Centralized auto-refresh (no duplicate logic)
- ✅ Better monitoring and observability
- ✅ Easy to add new services
- ✅ Graceful fallback if token service unavailable

## Configuration

### Environment Variables

All services now support these environment variables:

```bash
# Token Service (required for token_service)
TOKEN_SERVICE_HOST=0.0.0.0
TOKEN_SERVICE_PORT=8100
TOKEN_REFRESH_INTERVAL_MINUTES=14

# Token Service URL (required for other services)
TOKEN_SERVICE_URL=http://token_service:8100

# Legacy token database (fallback)
SCHWAB_TOKENS_DB=./tokens/schwabdev_tokens.db

# Schwab API credentials (still required)
SCHWAB_API_KEY=your_api_key
SCHWAB_API_SECRET=your_app_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
```

### Docker Compose

Updated `docker-compose.yml`:

```yaml
# New token_service container
token_service:
  ports:
    - "8100:8100"
  environment:
    TOKEN_SERVICE_URL: http://token_service:8100
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8100/health"]

# Updated dependencies
streaming:
  depends_on:
    token_service:
      condition: service_healthy
  environment:
    TOKEN_SERVICE_URL: http://token_service:8100

live_trading:
  depends_on:
    token_service:
      condition: service_healthy
  environment:
    TOKEN_SERVICE_URL: http://token_service:8100

admin_ui:
  environment:
    TOKEN_SERVICE_URL: http://token_service:8100
    USE_TOKEN_SERVICE: "true"
```

## Migration Features

### Graceful Fallback

All services implement graceful fallback:

1. **Try token service first**
   - Check if `TOKEN_SERVICE_URL` is set
   - Check if `TokenServiceClient` is available (import succeeded)
   - Test connection with health check

2. **Fall back to legacy mode if**:
   - Token service URL not configured
   - Token service is unhealthy
   - Connection fails
   - TokenServiceClient import fails

3. **Legacy mode uses**:
   - Local token database (`tokens/schwabdev_tokens.db`)
   - Direct schwabdev.Client token management
   - Local TokenManager (streaming_service only)

### Logging

All services log their token mode at startup:

**Token Service Mode**:
```
[2025-12-30 10:00:00][streaming][INFO    ]   Token Mode: Centralized (via http://token_service:8100)
[2025-12-30 10:00:00][streaming][INFO    ]   ✓ Token service connected
```

**Legacy Mode**:
```
[2025-12-30 10:00:00][streaming][INFO    ]   Token Mode: Legacy (local token database)
[2025-12-30 10:00:00][streaming][INFO    ]   ✓ Legacy token manager initialized
```

**Fallback**:
```
[2025-12-30 10:00:00][streaming][WARNING ]   ⚠️ Failed to connect to token service: Connection refused
[2025-12-30 10:00:00][streaming][WARNING ]   Falling back to legacy token management
```

## Testing

### Manual Testing

1. **Start token service**:
```bash
docker-compose up -d token_service

# Check health
curl http://localhost:8100/health

# Check token status
curl http://localhost:8100/token/status
```

2. **Start streaming service** (with token service):
```bash
docker-compose up -d streaming

# Check logs - should show "Token Mode: Centralized"
docker-compose logs streaming | grep "Token Mode"
```

3. **Test fallback** (stop token service):
```bash
docker-compose stop token_service
docker-compose restart streaming

# Check logs - should show "Falling back to legacy"
docker-compose logs streaming | grep "Falling back"
```

4. **Test admin UI**:
```bash
# Get token status (should show source: "token_service")
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/tokens/status

# Refresh token
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/api/tokens/refresh
```

### Automated Testing

Pending: Write comprehensive tests

- [ ] Unit tests for `CentralizedTokenManager`
- [ ] Integration tests for token service API
- [ ] End-to-end tests for service integration
- [ ] Fallback behavior tests
- [ ] Load tests for concurrent access

## Rollback Plan

If issues arise, rollback is simple:

1. **Stop token service**:
```bash
docker-compose stop token_service
```

2. **Services automatically fall back** to legacy mode

3. **Or disable token service** in environment:
```bash
# Set in .env
TOKEN_SERVICE_URL=
# or
USE_TOKEN_SERVICE=false
```

4. **Restart services**:
```bash
docker-compose restart streaming live_trading admin_ui
```

All services will operate in legacy mode using local token databases.

## Performance Impact

**Token Service**:
- Minimal overhead (simple HTTP GET/POST requests)
- Thread-safe concurrent access
- Background auto-refresh doesn't block requests

**Service Changes**:
- Streaming: Same performance (auto-refresh handled by token service)
- Live Trading: Same performance (only connects on startup)
- Admin UI: Slightly faster (proxies to token service vs. reading SQLite)

**Network**:
- Additional HTTP requests: ~1 per minute per service (status checks)
- Auto-refresh: Every 14 minutes (same as before)

## Security Considerations

**Token Service**:
- ⚠️ No authentication on API (internal network only)
- ✅ Tokens never logged in full (redacted)
- ✅ Database file has restrictive permissions
- ✅ Thread-safe concurrent access

**Production Recommendations**:
1. Deploy token service behind reverse proxy with TLS
2. Restrict network access to internal services only
3. Consider adding API authentication (JWT, API keys)
4. Monitor token service health and uptime
5. Set up alerts for token expiration

## Future Improvements

- [ ] Add API authentication to token service
- [ ] Implement WebSocket endpoint for real-time token events
- [ ] Add Prometheus metrics endpoint
- [ ] Support for multiple broker APIs (not just Schwab)
- [ ] Token encryption at rest
- [ ] Multi-user/multi-account support
- [ ] Token rotation policies
- [ ] Integration with admin UI frontend (real-time token status widget)

## Documentation

- **Complete Guide**: `docs/TOKEN_SERVICE.md`
- **Quick Start**: `src/token_service/README.md`
- **TODO Status**: `TODO.md`
- **This Document**: `docs/TOKEN_SERVICE_MIGRATION.md`

## Support

If you encounter issues:

1. Check token service logs: `docker-compose logs token_service`
2. Check service logs for fallback messages
3. Verify `TOKEN_SERVICE_URL` is set correctly
4. Test token service health: `curl http://localhost:8100/health`
5. If all else fails, set `USE_TOKEN_SERVICE=false` to use legacy mode

---

**Migration completed**: 2025-12-30
**Status**: ✅ All services migrated with graceful fallback support
