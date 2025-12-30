"""FastAPI service for centralized token management."""

import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
import uvicorn

from token_service.config import TokenServiceConfig
from token_service.manager import CentralizedTokenManager
from quant_vibe.config.logging_config import setup_normalized_logging
from quant_vibe.messaging import RedisMessageBroker, Topic


# Global state
token_manager: Optional[CentralizedTokenManager] = None
config: Optional[TokenServiceConfig] = None
logger = None
message_broker: Optional[RedisMessageBroker] = None
refresh_task: Optional[asyncio.Task] = None
heartbeat_task: Optional[asyncio.Task] = None
service_start_time = None


async def heartbeat_task_func():
    """Background task to publish heartbeat messages.

    Publishes service health status to Redis every 30 seconds.
    """
    global token_manager, config, logger, message_broker, service_start_time

    logger.info("Starting heartbeat task (interval: 30 seconds)")

    while True:
        try:
            await asyncio.sleep(30)

            if message_broker and config.enable_redis:
                try:
                    # Get token status
                    token_status = "unknown"
                    last_error = None
                    if token_manager:
                        status = token_manager.get_status()
                        if status.get("has_token"):
                            if not status.get("is_access_token_expired", True):
                                token_status = "healthy"
                            else:
                                token_status = "degraded"
                                last_error = "Access token expired"
                        else:
                            token_status = "unhealthy"
                            last_error = "No token available"

                    # Calculate uptime
                    uptime_seconds = 0
                    if service_start_time:
                        uptime_seconds = (datetime.utcnow() - service_start_time).total_seconds()

                    # Publish heartbeat
                    message_broker.publish(
                        "heartbeat.token_service",
                        {
                            "service": "token_service",
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": token_status,
                            "metrics": {
                                "uptime_seconds": round(uptime_seconds, 1),
                                "has_token": status.get("has_token", False) if token_manager else False,
                                "token_expired": status.get("is_access_token_expired", True) if token_manager else True,
                                "last_error": last_error,
                            },
                        },
                    )

                    logger.debug(f"Heartbeat published (status: {token_status})")

                except Exception as e:
                    logger.error(f"Failed to publish heartbeat: {e}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("Heartbeat task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in heartbeat task: {e}", exc_info=True)
            await asyncio.sleep(30)


async def auto_refresh_task():
    """Background task to automatically refresh tokens.

    Runs every interval configured in config.refresh_interval_minutes
    and refreshes the token if it's close to expiration.
    """
    global token_manager, config, logger, message_broker

    logger.info(
        f"Starting auto-refresh task (interval: {config.refresh_interval_minutes} minutes)"
    )

    while True:
        try:
            await asyncio.sleep(config.refresh_interval_minutes * 60)

            logger.info("Auto-refresh check triggered")

            if token_manager.needs_refresh(threshold_minutes=5):
                logger.info("Token needs refresh - refreshing now")
                success = token_manager.refresh_token()

                if success:
                    logger.info("Auto-refresh successful")

                    # Publish token refresh event to Redis
                    if message_broker and config.enable_redis:
                        try:
                            message_broker.publish(
                                "token.refreshed",
                                {
                                    "timestamp": token_manager.last_refresh.isoformat(),
                                    "status": "success",
                                }
                            )
                            logger.info("Published token refresh event to Redis")
                        except Exception as e:
                            logger.error(f"Failed to publish token event to Redis: {e}")
                else:
                    logger.error("Auto-refresh failed")

                    # Publish failure event
                    if message_broker and config.enable_redis:
                        try:
                            message_broker.publish(
                                "token.refresh_failed",
                                {"timestamp": None, "status": "failed"}
                            )
                        except Exception as e:
                            logger.error(f"Failed to publish token event to Redis: {e}")
            else:
                token_info = token_manager.get_token_info()
                if token_info:
                    logger.info(
                        f"Token still valid - {token_info.seconds_until_expiration/60:.1f} "
                        f"minutes remaining"
                    )

        except asyncio.CancelledError:
            logger.info("Auto-refresh task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in auto-refresh task: {e}", exc_info=True)
            # Continue running even if there's an error
            await asyncio.sleep(60)  # Wait 1 minute before retrying


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    global token_manager, config, logger, message_broker, refresh_task, heartbeat_task, service_start_time

    # Record start time
    service_start_time = datetime.utcnow()

    # Startup
    logger.info("="*70)
    logger.info("Token Management Service Starting")
    logger.info("="*70)

    # Load configuration
    try:
        config = TokenServiceConfig.from_env()
        logger.info("✓ Configuration loaded")
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
            logger=logger,
        )
        logger.info("✓ Token manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize token manager: {e}")
        raise

    # Initialize Redis message broker
    if config.enable_redis:
        try:
            message_broker = RedisMessageBroker(
                host=config.redis_host,
                port=config.redis_port,
                db=config.redis_db,
            )
            logger.info("✓ Redis message broker connected")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            logger.warning("Continuing without Redis event publishing")
            message_broker = None

    # Start background auto-refresh task
    refresh_task = asyncio.create_task(auto_refresh_task())
    logger.info("✓ Background auto-refresh task started")

    # Start background heartbeat task
    if config.enable_redis and message_broker:
        heartbeat_task = asyncio.create_task(heartbeat_task_func())
        logger.info("✓ Background heartbeat task started")

    # Check initial token status
    status = token_manager.get_status()
    if status.get("has_token"):
        logger.info("✓ Token found in database")
        logger.info(f"  Access token age: {status.get('access_token_age_seconds', 0)/60:.1f} minutes")
        logger.info(f"  Expires in: {status.get('seconds_until_expiration', 0)/60:.1f} minutes")
    else:
        logger.warning("⚠ No token found - authentication required")

    logger.info("="*70)
    logger.info(f"Token Service Ready - Listening on {config.host}:{config.port}")
    logger.info("="*70)

    yield

    # Shutdown
    logger.info("Token Management Service Shutting Down")

    # Cancel background tasks
    if refresh_task:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass

    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    # Close Redis connection
    if message_broker:
        try:
            message_broker.close()
            logger.info("✓ Redis connection closed")
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
    """Health check endpoint.

    Returns:
        Health status with token manager status
    """
    global token_manager

    if not token_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token manager not initialized"
        )

    token_status = token_manager.get_status()

    return {
        "status": "healthy",
        "service": "token_service",
        "has_token": token_status.get("has_token", False),
        "token_expired": token_status.get("is_access_token_expired", True),
    }


@app.get("/token/status")
async def get_token_status():
    """Get comprehensive token status.

    Returns:
        Token status information including expiration, age, etc.
    """
    global token_manager

    if not token_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token manager not initialized"
        )

    return token_manager.get_status()


@app.get("/token/access")
async def get_access_token():
    """Get current access token.

    Returns:
        Access token (redacted for security) with metadata

    Raises:
        HTTPException: If no token available or token expired
    """
    global token_manager

    if not token_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token manager not initialized"
        )

    token_info = token_manager.get_token_info()

    if not token_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No token found in database"
        )

    if token_info.is_access_token_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token is expired - refresh required"
        )

    if token_info.is_refresh_token_expired:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is expired - re-authentication required"
        )

    # Return token with metadata (redact actual token value for logs)
    return {
        "access_token": token_info.access_token,
        "token_type": token_info.token_type,
        "expires_in": int(token_info.seconds_until_expiration),
        "issued_at": token_info.access_token_issued.isoformat(),
        "expires_at": token_info.access_token_expires_at.isoformat(),
    }


@app.post("/token/refresh")
async def refresh_token():
    """Manually trigger token refresh.

    Returns:
        Refresh operation result with updated token status

    Raises:
        HTTPException: If refresh fails
    """
    global token_manager, message_broker, config

    if not token_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token manager not initialized"
        )

    logger.info("Manual token refresh requested")

    success = token_manager.refresh_token()

    if success:
        logger.info("Manual token refresh successful")

        # Publish token refresh event
        if message_broker and config.enable_redis:
            try:
                message_broker.publish(
                    "token.refreshed",
                    {
                        "timestamp": token_manager.last_refresh.isoformat(),
                        "status": "success",
                        "manual": True,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to publish token event to Redis: {e}")

        # Get updated status
        updated_status = token_manager.get_status()

        return {
            "success": True,
            "message": "Token refreshed successfully",
            "token_status": updated_status,
        }
    else:
        logger.error("Manual token refresh failed")

        # Publish failure event
        if message_broker and config.enable_redis:
            try:
                message_broker.publish(
                    "token.refresh_failed",
                    {"timestamp": None, "status": "failed", "manual": True}
                )
            except Exception as e:
                logger.error(f"Failed to publish token event to Redis: {e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed - check service logs"
        )


def main():
    """Main entry point for running the service."""
    global logger, config

    # Initialize logging first (before config)
    # Read log level from env (default to INFO)
    log_level = os.getenv("TOKEN_SERVICE_LOG_LEVEL", "INFO").upper()
    logger = setup_normalized_logging(
        app_name="token_service",
        log_level=log_level,
        log_dir="logs/token_service",
    )

    try:
        # Load config to get host/port
        config = TokenServiceConfig.from_env()

        # Run uvicorn server
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
