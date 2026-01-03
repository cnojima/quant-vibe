# Token Service Architecture

## Overview

The token service provides **centralized OAuth token management** for all Schwab API clients in the QuantVibe system.

## Separation of Concerns

### Token Service Responsibilities
- **Token lifecycle management**: Refresh, storage, expiration tracking
- **Background refresh**: Automatic token refresh every 14 minutes
- **Health monitoring**: Expose token status via HTTP API
- **Redis events**: Publish token refresh events for subscribers

### Client Responsibilities (Streaming, Live Trading, etc.)
- **Token verification only**: Check that a valid token exists
- **Token consumption**: Use tokens for API calls
- **Graceful degradation**: Fall back to legacy mode if token service unavailable

## Critical Design Principle

**Clients MUST NOT attempt to refresh tokens when using the token service.**

Token refresh is the token service's job. Clients should only:
1. Verify token availability at startup via `get_token_status()`
2. Trust that the token service is handling refresh in the background
3. Handle token service unavailability by falling back to legacy mode

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Token Service                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Background Refresh Loop (every 14 min)                    │  │
│  │  - Checks token expiration                                │  │
│  │  - Refreshes if needed                                    │  │
│  │  - Updates token database                                 │  │
│  │  - Publishes Redis event: "token.refreshed"              │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  HTTP API:                                                       │
│  - GET /health                                                   │
│  - GET /token/status                                            │
│  - POST /token/refresh (manual trigger)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Streaming Service                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Startup Sequence:                                         │  │
│  │  1. Check token service health                           │  │
│  │  2. Verify token exists (get_token_status)               │  │
│  │  3. Start streaming (token service handles refresh)      │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  Runtime:                                                        │
│  - NO token refresh attempts                                     │
│  - Consumes tokens via schwabdev client                         │
│  - Trusts token service background refresh                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                  Live Trading Service                            │
│  - Same pattern as streaming service                            │
│  - Verify token at startup only                                 │
│  - No refresh attempts                                          │
└─────────────────────────────────────────────────────────────────┘
```

## Client Implementation Pattern

### ✅ Correct Pattern (Token Service Mode)

```python
# At startup
self.logger.info("Verifying authentication token...")
token_valid = False

if self.token_service_client:
    # Check if token service has a valid token
    try:
        status = self.token_service_client.get_token_status()
        if status.get("has_token"):
            self.logger.info("✓ Token service has valid token")
            token_valid = True
        else:
            self.logger.warning("⚠️  Token service has no token")
    except Exception as e:
        self.logger.warning(f"⚠️  Failed to check token service: {e}")

if not token_valid:
    self.logger.error("❌ No valid token available!")
    return

# Continue with normal operation
# Token service handles refresh in the background
```

### ❌ Incorrect Pattern

```python
# WRONG: Client tries to refresh token
if self.token_service_client:
    try:
        if self.token_service_client.refresh_token():  # ❌ DON'T DO THIS
            self.logger.info("✓ Token refreshed")
        else:
            self.logger.warning("⚠️  Refresh failed")
    except Exception as e:
        self.logger.warning(f"⚠️  Refresh error: {e}")
```

**Why this is wrong:**
- Violates separation of concerns
- Creates race conditions with token service's background refresh
- Token service is already handling refresh every 14 minutes
- Client should only verify, not manage lifecycle

## Legacy Mode (Without Token Service)

For backwards compatibility, clients can fall back to legacy token management:

```python
# Fallback to legacy token manager
if not token_valid and self.token_manager:
    # Legacy mode: verify token exists, refresh if needed
    if self.token_manager.needs_refresh():
        if self.token_manager.refresh():
            self.logger.info("✓ Token refreshed via legacy token manager")
            token_valid = True
    else:
        self.logger.info("✓ Legacy token is valid")
        token_valid = True
```

**Legacy mode is only used when:**
- Token service is not available/configured
- Token service health check fails
- Running outside Docker (local development)

## Migration Path

### Phase 1: Current State (Token Service Available)
- Token service handles all refresh
- Streaming service verifies token only
- Legacy fallback available

### Phase 2: Full Migration (Future)
- Remove legacy token manager from clients
- All services depend on token service
- No local token refresh capability

## Troubleshooting

### "Token service has no token"

**Cause**: Token service database is empty or token expired

**Solution**:
1. Check token service logs: `docker logs token_service`
2. Manually authenticate: `python scripts/schwab_auth.py`
3. Verify token database exists: `ls -la tokens/schwab_tokens.db`
4. Restart token service: `docker-compose restart token_service`

### "Failed to check token service status"

**Cause**: Token service container not running or network issue

**Solution**:
1. Check containers: `docker ps | grep token`
2. Start token service: `docker-compose up -d token_service`
3. Check token service health: `curl http://localhost:8100/health`

### "Streaming service tries to refresh token"

**Cause**: Using old version of streaming service code

**Solution**:
1. Update to latest code (see this PR)
2. Rebuild container: `docker-compose build streaming`
3. Restart: `docker-compose restart streaming`

## Configuration

### Token Service (.env)

```bash
# Token service settings
TOKEN_SERVICE_HOST=0.0.0.0
TOKEN_SERVICE_PORT=8100
TOKEN_REFRESH_INTERVAL_MINUTES=14

# Schwab OAuth credentials
SCHWAB_API_KEY=your_key
SCHWAB_API_SECRET=your_secret
SCHWAB_CALLBACK_URL=https://quantview.net:53430/callback
```

### Client Services (.env)

```bash
# Token service URL (Docker service name)
TOKEN_SERVICE_URL=http://token_service:8100

# Legacy credentials (fallback only)
SCHWAB_API_KEY=your_key
SCHWAB_API_SECRET=your_secret
SCHWAB_CALLBACK_URL=https://quantview.net:53430/callback
```

## Benefits of This Architecture

✅ **Single source of truth**: One service manages tokens
✅ **No duplicate refresh**: Avoids race conditions
✅ **Easier debugging**: Token issues centralized in one place
✅ **Better observability**: Token service exposes metrics
✅ **Graceful degradation**: Clients fall back to legacy mode
✅ **Scalability**: Multiple clients share one token refresh service

## Related Documentation

- `docs/token_service/TOKEN_SERVICE.md` - Token service implementation
- `docs/token_service/TOKEN_SERVICE_MIGRATION.md` - Migration guide
- `src/streaming_service/README.md` - Streaming service overview
