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

## Implement centralized token management service

Create a dedicated token manager service to handle OAuth token lifecycle:
- Centralized token refresh/rotation logic
- Shared token access across all services (streaming, live_trading, etc.)
- Token expiry monitoring and automatic renewal
- REST API for token access: `GET /token`, `POST /refresh`
- Eliminates duplicate token refresh logic across services
- Single point of maintenance for token management

**Architecture:**
```
token_manager (service)
  ↓ provides tokens via API
streaming_service, live_trading_service, etc.
  ↓ request tokens from token_manager
Schwab API
```

**Benefits:**
- ✅ Single source of truth for tokens
- ✅ Centralized refresh logic (no duplicate code)
- ✅ Better monitoring and logging of token lifecycle
- ✅ Easier to implement token rotation policies
- ✅ Supports multiple broker APIs in the future

## Implement notifcations/emails/sms system

## Implement watcher/heartbeat monitoring

## Implement some kind of UI to monitor in realtime, change strategy params, etc.

