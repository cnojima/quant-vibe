"""FastAPI service for centralized token management."""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
import uvicorn

from token_service.config import TokenServiceConfig
from token_service.errors import TokenLockoutError
from token_service.manager import CentralizedTokenManager
from quant_vibe.logging import setup_normalized_logging
from quant_vibe.messaging import RedisMessageBroker
from quant_vibe.utils.timestamp_utils import now_utc


# Global state
token_manager: Optional[CentralizedTokenManager] = None
config: Optional[TokenServiceConfig] = None
logger = None
message_broker: Optional[RedisMessageBroker] = None
refresh_task: Optional[asyncio.Task] = None
heartbeat_task: Optional[asyncio.Task] = None
service_start_time = None


async def heartbeat_task_func():
    """Background task to publish heartbeat messages."""
    logger.info("Starting heartbeat task (interval: 30 seconds)")

    while True:
        try:
            await asyncio.sleep(30)

            if message_broker and config.enable_redis:
                await _publish_heartbeat()

        except asyncio.CancelledError:
            logger.info("Heartbeat task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in heartbeat task: {e}", exc_info=True)
            await asyncio.sleep(30)


async def _publish_heartbeat():
    """Publish heartbeat message to Redis."""
    try:
        token_status, last_error = _get_service_health()
        uptime_seconds = (now_utc() - service_start_time).total_seconds() if service_start_time else 0

        message_broker.publish(
            "heartbeat.token_service",
            {
                "service": "token_service",
                "timestamp": now_utc().isoformat(),
                "status": token_status,
                "metrics": {
                    "uptime_seconds": round(uptime_seconds, 1),
                    "has_token": token_manager and token_manager.get_status().get("has_token", False),
                    "token_expired": not token_manager or token_manager.get_status().get("is_access_token_expired", True),
                    "last_error": last_error,
                },
            },
        )
        logger.debug(f"Heartbeat published (status: {token_status})")
    except Exception as e:
        logger.error(f"Failed to publish heartbeat: {e}", exc_info=True)


def _get_service_health() -> tuple[str, Optional[str]]:
    """Get service health status."""
    if not token_manager:
        return "unhealthy", "Token manager not initialized"

    status = token_manager.get_status()
    if not status.get("has_token"):
        error = "OAuth authentication required" if status.get("requires_oauth") else "No token available"
        return "unhealthy", error

    if status.get("is_access_token_expired", True):
        return "degraded", "Access token expired"

    return "healthy", None


async def auto_refresh_task():
    """Background task to automatically refresh tokens."""
    logger.info(f"Starting auto-refresh task (interval: {config.refresh_interval_minutes} minutes)")

    while True:
        try:
            await asyncio.sleep(config.refresh_interval_minutes * 60)
            await _check_and_refresh_token()

        except asyncio.CancelledError:
            logger.info("Auto-refresh task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in auto-refresh task: {e}", exc_info=True)
            await asyncio.sleep(60)  # Wait 1 minute before retrying


async def _check_and_refresh_token():
    """Check token status and refresh if needed."""
    logger.info("Auto-refresh check triggered")

    if not token_manager:
        logger.warning("Token manager not initialized - skipping auto-refresh")
        return

    # Check lockout state before attempting refresh
    if token_manager.is_locked_out():
        logger.error("Token service is in LOCKOUT state - skipping auto-refresh")
        _publish_lockout_status()
        return

    if not token_manager.needs_refresh(threshold_minutes=5):
        token_info = token_manager.get_token_info()
        if token_info:
            logger.info(f"Token still valid - {token_info.seconds_until_expiration/60:.1f} minutes remaining")
        return

    logger.info("Token needs refresh - refreshing now")

    try:
        success = token_manager.refresh_token()

        if success:
            logger.info("Auto-refresh successful")
            _publish_token_event("token.refreshed", {
                "timestamp": token_manager.last_refresh.isoformat(),
                "status": "success"
            })
        else:
            logger.error("Auto-refresh failed")
            _publish_token_event("token.refresh_failed", {
                "timestamp": now_utc().isoformat(),
                "status": "failed",
                "consecutive_failures": token_manager._consecutive_failures,
            })

            # Check if lockout was triggered by this failure
            if token_manager.is_locked_out():
                _publish_lockout_event()

    except TokenLockoutError as e:
        logger.critical(f"Token lockout triggered: {e}")
        _publish_lockout_event()


def _publish_lockout_event():
    """Publish lockout event to Redis."""
    if not message_broker or not config.enable_redis:
        return

    try:
        lockout_status = token_manager.get_lockout_status()
        message_broker.publish(
            "token.lockout",
            {
                "service": "token_service",
                "timestamp": now_utc().isoformat(),
                "lockout_triggered_at": lockout_status.get("lockout_triggered_at"),
                "reason": lockout_status.get("last_error_message"),
                "error_type": lockout_status.get("last_error_type"),
                "consecutive_failures": lockout_status.get("consecutive_failures"),
                "requires_reauth": True,
            },
        )
        logger.critical("Lockout event published to Redis on topic: token.lockout")
    except Exception as e:
        logger.error(f"Failed to publish lockout event: {e}")


def _publish_lockout_status():
    """Publish current lockout status to Redis (for periodic heartbeat)."""
    if not message_broker or not config.enable_redis:
        return

    try:
        lockout_status = token_manager.get_lockout_status()
        message_broker.publish(
            "token.lockout_status",
            {
                "service": "token_service",
                "timestamp": now_utc().isoformat(),
                **lockout_status,
            },
        )
    except Exception as e:
        logger.error(f"Failed to publish lockout status: {e}")


def _publish_token_event(topic: str, data: dict):
    """Publish token event to Redis if enabled."""
    if message_broker and config.enable_redis:
        try:
            message_broker.publish(topic, data)
            logger.info(f"Published {topic} event to Redis")
        except Exception as e:
            logger.error(f"Failed to publish token event to Redis: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global token_manager, config, logger, message_broker, refresh_task, heartbeat_task, service_start_time

    service_start_time = now_utc()

    # Startup
    logger.info("=" * 70)
    logger.info("Token Management Service Starting")
    logger.info("=" * 70)

    await _initialize_service()
    await _start_background_tasks()
    _log_initial_status()

    logger.info("=" * 70)
    logger.info(f"Token Service Ready - Listening on {config.host}:{config.port}")
    logger.info("=" * 70)

    yield

    # Shutdown
    await _shutdown_service()


async def _initialize_service():
    """Initialize service components."""
    global config, token_manager, message_broker

    # Load configuration
    try:
        config = TokenServiceConfig.from_env()
        logger.info("Configuration loaded")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise

    # Initialize token manager
    try:
        token_manager = CentralizedTokenManager(
            api_key=config.schwab_api_key,
            api_secret=config.schwab_api_secret,
            callback_url=config.schwab_callback_url,
            tokens_db_path=config.tokens_db_path,
            # Lockout configuration
            max_consecutive_failures=config.max_consecutive_failures,
            lockout_on_non_retryable=config.lockout_on_non_retryable,
            # Retry configuration
            refresh_max_retries=config.refresh_max_retries,
            refresh_backoff_base=config.refresh_backoff_base,
            refresh_max_backoff=config.refresh_max_backoff,
        )
        logger.info("Token manager initialized")
        logger.info(
            f"Lockout config: max_failures={config.max_consecutive_failures}, "
            f"lockout_on_non_retryable={config.lockout_on_non_retryable}"
        )
    except Exception as e:
        logger.error(f"Failed to initialize token manager: {e}")
        logger.error("Service will start but token operations will not be available")
        token_manager = None

    # Initialize Redis
    if config.enable_redis:
        try:
            message_broker = RedisMessageBroker(
                host=config.redis_host,
                port=config.redis_port,
                db=config.redis_db,
            )
            logger.info("Redis message broker connected")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            logger.warning("Continuing without Redis event publishing")
            message_broker = None


async def _start_background_tasks():
    """Start background tasks."""
    global refresh_task, heartbeat_task

    refresh_task = asyncio.create_task(auto_refresh_task())
    logger.info("Background auto-refresh task started")

    if config.enable_redis and message_broker:
        heartbeat_task = asyncio.create_task(heartbeat_task_func())
        logger.info("Background heartbeat task started")


def _log_initial_status():
    """Log initial token status."""
    if not token_manager:
        logger.warning("Token manager not initialized - OAuth authentication required")
        return

    status = token_manager.get_status()
    if status.get("has_token"):
        logger.info("Token found in database")
        logger.info(f"  Access token age: {status.get('access_token_age_seconds', 0)/60:.1f} minutes")
        logger.info(f"  Expires in: {status.get('seconds_until_expiration', 0)/60:.1f} minutes")
    else:
        logger.warning("No token found - authentication required")
        if status.get("requires_oauth"):
            logger.warning("  Use Admin UI to complete OAuth flow")


async def _shutdown_service():
    """Shutdown service cleanly."""
    logger.info("Token Management Service Shutting Down")

    # Cancel background tasks
    for task in [refresh_task, heartbeat_task]:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # Close Redis connection
    if message_broker:
        try:
            message_broker.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Token Management Service",
    description="Centralized OAuth token management for Schwab API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    _ensure_token_manager()

    token_status = token_manager.get_status()

    # Determine overall health status
    if token_manager.is_locked_out():
        health_status = "lockout"
    elif not token_status.get("has_token", False):
        health_status = "unhealthy"
    elif token_status.get("is_access_token_expired", True):
        health_status = "degraded"
    else:
        health_status = "healthy"

    return {
        "status": health_status,
        "service": "token_service",
        "has_token": token_status.get("has_token", False),
        "token_expired": token_status.get("is_access_token_expired", True),
        "is_locked_out": token_manager.is_locked_out(),
    }


@app.get("/token/status")
async def get_token_status():
    """Get comprehensive token status."""
    _ensure_token_manager()
    return token_manager.get_status()


@app.get("/token/access")
async def get_access_token():
    """Get current access token."""
    _ensure_token_manager()

    # Check lockout first
    if token_manager.is_locked_out():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token service is in LOCKOUT state - manual re-authentication required"
        )

    token_info = token_manager.get_token_info()
    if not token_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No token found in database")

    if token_info.is_access_token_expired:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token is expired - refresh required")

    if token_info.is_refresh_token_expired:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is expired - re-authentication required")

    return {
        "access_token": token_info.access_token,
        "token_type": token_info.token_type,
        "expires_in": int(token_info.seconds_until_expiration),
        "issued_at": token_info.access_token_issued.isoformat(),
        "expires_at": token_info.access_token_expires_at.isoformat(),
    }


@app.post("/token/refresh")
async def refresh_token():
    """Manually trigger token refresh."""
    _ensure_token_manager()

    logger.info("Manual token refresh requested")

    try:
        success = token_manager.refresh_token()
    except TokenLockoutError as e:
        logger.critical(f"Token refresh blocked by lockout: {e}")
        _publish_lockout_event()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Token service is in LOCKOUT state: {e}"
        )

    if not success:
        logger.error("Manual token refresh failed")
        _publish_token_event("token.refresh_failed", {
            "timestamp": now_utc().isoformat(),
            "status": "failed",
            "manual": True,
            "consecutive_failures": token_manager._consecutive_failures,
        })

        # Check if lockout was triggered
        if token_manager.is_locked_out():
            _publish_lockout_event()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Token refresh failed and lockout triggered - manual re-authentication required"
            )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed - check service logs"
        )

    logger.info("Manual token refresh successful")
    _publish_token_event(
        "token.refreshed",
        {"timestamp": token_manager.last_refresh.isoformat(), "status": "success", "manual": True}
    )

    return {
        "success": True,
        "message": "Token refreshed successfully",
        "token_status": token_manager.get_status(),
    }


@app.get("/token/lockout-status")
async def get_lockout_status():
    """Get current lockout status.

    Returns detailed information about the lockout state, including
    when it was triggered, the reason, and consecutive failure count.
    """
    _ensure_token_manager()
    return token_manager.get_lockout_status()


@app.post("/token/clear-lockout")
async def clear_lockout():
    """Clear lockout state for manual recovery.

    This only clears the lockout flag. Tokens must still be re-obtained
    via OAuth flow before service can resume normal operation.

    Steps after clearing lockout:
    1. Complete OAuth re-authentication via Admin UI or scripts/authorize_schwab.py
    2. Restart the token service to reinitialize with new tokens
    """
    _ensure_token_manager()

    if not token_manager.is_locked_out():
        return {
            "success": False,
            "message": "Service is not in lockout state",
            "is_locked_out": False,
        }

    logger.info("Manual lockout clear requested")
    token_manager.clear_lockout()

    # Publish lockout cleared event
    if message_broker and config.enable_redis:
        try:
            message_broker.publish(
                "token.lockout_cleared",
                {
                    "service": "token_service",
                    "timestamp": now_utc().isoformat(),
                    "cleared_by": "manual_api_call",
                },
            )
            logger.info("Lockout cleared event published to Redis")
        except Exception as e:
            logger.error(f"Failed to publish lockout cleared event: {e}")

    return {
        "success": True,
        "message": "Lockout cleared. Please complete OAuth re-authentication.",
        "is_locked_out": False,
        "next_steps": [
            "1. Use Admin UI OAuth flow, or",
            "2. Run: python scripts/authorize_schwab.py",
            "3. Restart token service after re-authentication",
        ],
    }


def _ensure_token_manager():
    """Ensure token manager is initialized."""
    if not token_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token manager not initialized"
        )


def main():
    """Main entry point for running the service."""
    global logger, config

    logger = setup_normalized_logging(app_name="token_service", log_dir="logs/token_service")

    try:
        config = TokenServiceConfig.from_env()
        uvicorn.run(
            "token_service.service:app",
            host=config.host,
            port=config.port,
            log_level="info",
        )
    except Exception as e:
        logger.error(f"Failed to start service: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
