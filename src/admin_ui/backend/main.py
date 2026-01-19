"""
FastAPI application entry point for Quant-Vibe Admin UI.

Provides REST API and WebSocket endpoints for:
- Service management (Docker control)
- Schwab token management
- Live trading monitoring
- Backtest execution
- Configuration management
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from admin_ui.backend.config import get_settings
from admin_ui.backend.db.timescale import close_db_pool, init_db_pool
from admin_ui.backend.redis_client import (
    close_redis,
    init_redis,
    listen_to_redis,
    register_websocket,
    unregister_websocket,
)
from admin_ui.backend.api import (
    auth,
    backtests,
    config,
    live,
    notifications,
    optimization_v2 as optimization,
    services,
    status,
    strategies,
    tokens,
    watcher,
)
from quant_vibe.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager for startup/shutdown tasks."""
    settings = get_settings()

    # Startup
    logger.info(f"Starting {settings.app_name}...")
    await init_db_pool()
    await init_redis()
    logger.info("Database and Redis connections initialized")

    # Start Redis listener in background
    redis_task = asyncio.create_task(listen_to_redis())
    logger.info("Redis listener started")

    yield

    # Shutdown
    logger.info("Shutting down...")
    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass

    await close_db_pool()
    await close_redis()
    logger.info("Connections closed")


settings = get_settings()

app = FastAPI(
    title="Quant-Vibe Admin UI API",
    description="REST API for managing Quant-Vibe trading system",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "admin_ui"}


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs_url": "/docs",
        "health_url": "/health",
    }


# Include routers with API prefix
api_prefix = settings.api_prefix
routers = [
    (auth.router, "auth"),
    (services.router, "services"),
    (status.router, "status"),
    (tokens.router, "tokens"),
    (live.router, "live"),
    (backtests.router, "backtests"),
    (config.router, "config"),
    (strategies.router, "strategies"),
    (watcher.router, "watcher"),
    (optimization.router, "optimization"),
    (notifications.router, "notifications"),
]

for router, tag in routers:
    app.include_router(router, prefix=f"{api_prefix}/{tag}", tags=[tag])


@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event streaming.

    Connects to Redis pub/sub and forwards messages to the client.
    """
    await websocket.accept()
    register_websocket(websocket)
    logger.info(f"[WebSocket] Client connected from {websocket.client}")

    try:
        await websocket.send_json({
            "type": "connection",
            "message": "Connected to live trading events",
            "timestamp": asyncio.get_event_loop().time()
        })
        logger.debug("[WebSocket] Welcome message sent")
    except Exception as e:
        logger.error(f"[WebSocket] Failed to send welcome message: {type(e).__name__}: {e}")
        unregister_websocket(websocket)
        return

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                logger.debug("[WebSocket] Client initiated disconnect")
                break

            if message["type"] == "websocket.receive" and "text" in message:
                data = message["text"]
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                    logger.debug("[WebSocket] Responded to ping")

    except WebSocketDisconnect:
        logger.info("[WebSocket] Client disconnected (WebSocketDisconnect)")
    except Exception as e:
        logger.error(f"[WebSocket] Error: {type(e).__name__}: {e}", exc_info=True)
    finally:
        unregister_websocket(websocket)
        logger.debug("[WebSocket] Connection closed and unregistered")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "admin_ui.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
