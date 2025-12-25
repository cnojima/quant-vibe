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

# Import routers
from admin_ui.backend.api import (
    auth,
    backtests,
    config,
    live,
    services,
    status,
    tokens,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager for startup/shutdown tasks."""
    settings = get_settings()

    # Startup
    print(f"Starting {settings.app_name}...")
    await init_db_pool()
    await init_redis()
    print("Database and Redis connections initialized")

    # Start Redis listener in background
    redis_task = asyncio.create_task(listen_to_redis())
    print("Redis listener started")

    yield

    # Shutdown
    print("Shutting down...")
    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass
    await close_db_pool()
    await close_redis()
    print("Connections closed")


# Create FastAPI application
app = FastAPI(
    title="Quant-Vibe Admin UI API",
    description="REST API for managing Quant-Vibe trading system",
    version="0.1.0",
    lifespan=lifespan,
)

# Get settings
settings = get_settings()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "admin_ui"}


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "docs_url": "/docs",
        "health_url": "/health",
    }


# Include routers
app.include_router(auth.router, prefix=f"{settings.api_prefix}/auth", tags=["auth"])
app.include_router(services.router, prefix=f"{settings.api_prefix}/services", tags=["services"])
app.include_router(status.router, prefix=f"{settings.api_prefix}/status", tags=["status"])
app.include_router(tokens.router, prefix=f"{settings.api_prefix}/tokens", tags=["tokens"])
app.include_router(live.router, prefix=f"{settings.api_prefix}/live", tags=["live"])
app.include_router(backtests.router, prefix=f"{settings.api_prefix}/backtests", tags=["backtests"])
app.include_router(config.router, prefix=f"{settings.api_prefix}/config", tags=["config"])


# WebSocket endpoint for real-time updates
@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event streaming.

    Connects to Redis pub/sub and forwards messages to the client.
    """
    await websocket.accept()
    register_websocket(websocket)

    try:
        # Keep connection alive and handle incoming messages
        while True:
            # Receive (and ignore) any messages from client (ping/pong)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        unregister_websocket(websocket)


# Exception handlers
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
