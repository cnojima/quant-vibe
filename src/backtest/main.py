"""
FastAPI application for Backtest Service.

This module provides REST API endpoints for managing backtests.
"""

import os
import json
import asyncio
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
from redis.asyncio import Redis

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc
from .models import (
    BacktestRequest,
    BacktestResponse,
    BacktestStatus,
    BacktestResult,
    BacktestListResponse,
    BacktestCancelRequest,
    BacktestCancelResponse,
    BacktestError,
    WebSocketMessage,
)
from .service import BacktestService
from .repository import BacktestRepository
from .worker import BacktestWorker


logger = get_logger(__name__)


# Global instances
redis_client: Optional[Redis] = None
backtest_service: Optional[BacktestService] = None
backtest_repository: Optional[BacktestRepository] = None
backtest_worker: Optional[BacktestWorker] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.

    Handles startup and shutdown events.
    """
    # Startup
    global redis_client, backtest_service, backtest_repository, backtest_worker

    # Get configuration from environment
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    db_url = os.getenv("DATABASE_URL", "postgresql://quantvibe:quantvibe_dev@localhost:5432/options_data")

    # Initialize Redis client
    redis_client = await aioredis.from_url(
        redis_url,
        decode_responses=True,
    )

    # Initialize repository
    backtest_repository = BacktestRepository(db_url)

    # Create database tables if they don't exist
    backtest_repository.create_tables()

    # Initialize backtest service
    backtest_service = BacktestService(
        redis_client=redis_client,
        db_connection_string=db_url,
        data_cache_ttl=int(os.getenv("DATA_CACHE_TTL", "3600")),
        results_base_dir=os.getenv("RESULTS_BASE_DIR", "results/backtests"),
        max_concurrent_backtests=int(os.getenv("MAX_CONCURRENT_BACKTESTS", "5")),
    )

    # Initialize and start worker if in worker mode
    if os.getenv("WORKER_MODE", "false").lower() == "true":
        backtest_worker = BacktestWorker(
            redis_client=redis_client,
            backtest_service=backtest_service,
            backtest_repository=backtest_repository,
        )
        # Start worker in background
        asyncio.create_task(backtest_worker.start())

    logger.info("Backtest service started successfully")

    yield

    # Shutdown
    if backtest_worker:
        await backtest_worker.stop()

    if redis_client:
        await redis_client.close()

    logger.info("Backtest service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Backtest Service",
    description="API for managing strategy backtests",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================================================================
# Dependencies
# ========================================================================

def get_service() -> BacktestService:
    """Get backtest service instance."""
    if not backtest_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return backtest_service


def get_repository() -> BacktestRepository:
    """Get backtest repository instance."""
    if not backtest_repository:
        raise HTTPException(status_code=503, detail="Repository not initialized")
    return backtest_repository


# ========================================================================
# API Endpoints
# ========================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "backtest"}


@app.post("/api/backtests", response_model=BacktestResponse)
async def create_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    service: BacktestService = Depends(get_service),
    repository: BacktestRepository = Depends(get_repository),
):
    """
    Create a new backtest.

    This endpoint creates a backtest task and queues it for processing.
    """
    try:
        # Create backtest task
        backtest_id = await service.create_backtest(
            strategy_name=request.strategy_name,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            params=request.params,
            ticker=request.ticker,
            timeframe=request.timeframe,
            description=request.description,
        )

        # Also store in database
        repository.create_backtest_task(
            backtest_id=backtest_id,
            strategy_name=request.strategy_name,
            params=request.params,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            ticker=request.ticker,
            timeframe=request.timeframe,
            description=request.description,
        )

        # Queue for processing (worker will pick it up)
        # If no worker is running, process in background
        if not backtest_worker:
            background_tasks.add_task(service.run_backtest, backtest_id)

        return BacktestResponse(
            id=backtest_id,
            status="pending",
            message=f"Backtest {backtest_id} created and queued for processing",
            created_at=now_utc(),  # Use current time for created_at
        )

    except Exception as e:
        logger.error(f"Failed to create backtest: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/backtests/{backtest_id}", response_model=BacktestStatus)
async def get_backtest_status(
    backtest_id: str,
    service: BacktestService = Depends(get_service),
):
    """
    Get backtest status by ID.

    Returns the current status and progress of a backtest.
    """
    status = await service.get_status(backtest_id)

    if not status:
        raise HTTPException(status_code=404, detail=f"Backtest {backtest_id} not found")

    return BacktestStatus(**status)


@app.get("/api/backtests/{backtest_id}/results", response_model=BacktestResult)
async def get_backtest_results(
    backtest_id: str,
    repository: BacktestRepository = Depends(get_repository),
):
    """
    Get backtest results.

    Returns the results of a completed backtest.
    """
    results = repository.get_backtest_results(backtest_id)

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"Results for backtest {backtest_id} not found. The backtest may not be completed yet.",
        )

    return BacktestResult(**results)


@app.delete("/api/backtests/{backtest_id}", response_model=BacktestCancelResponse)
async def cancel_backtest(
    backtest_id: str,
    request: Optional[BacktestCancelRequest] = None,
    service: BacktestService = Depends(get_service),
):
    """
    Cancel a running backtest.

    Attempts to cancel a backtest that is pending or running.
    """
    success = await service.cancel_backtest(backtest_id)

    if not success:
        return BacktestCancelResponse(
            success=False,
            message=f"Unable to cancel backtest {backtest_id}. It may not exist or is already completed.",
        )

    return BacktestCancelResponse(
        success=True,
        message=f"Backtest {backtest_id} cancelled successfully",
    )


@app.get("/api/backtests", response_model=BacktestListResponse)
async def list_backtests(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    service: BacktestService = Depends(get_service),
):
    """
    List backtests with optional filtering.

    Returns a paginated list of backtests.
    """
    # Validate status if provided
    valid_statuses = ["pending", "running", "completed", "failed", "cancelled"]
    if status and status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    backtests = await service.list_backtests(
        status=status,
        limit=limit,
        offset=offset,
    )

    # Convert to BacktestStatus objects
    backtest_statuses = []
    for bt in backtests:
        # Handle missing or None values with defaults
        backtest_statuses.append(BacktestStatus(
            id=bt.get("id", ""),
            status=bt.get("status", "pending"),
            progress=float(bt.get("progress", 0)),
            strategy_name=bt.get("strategy_name", ""),
            created_at=bt.get("created_at", ""),
            started_at=bt.get("started_at"),
            completed_at=bt.get("completed_at"),
            error=bt.get("error"),
            eta=bt.get("eta"),
            current_step=bt.get("current_step"),
        ))

    return BacktestListResponse(
        backtests=backtest_statuses,
        total=len(backtest_statuses),
        offset=offset,
        limit=limit,
    )


# ========================================================================
# WebSocket Endpoint
# ========================================================================

@app.websocket("/ws/backtests/{backtest_id}")
async def websocket_endpoint(websocket: WebSocket, backtest_id: str):
    """
    WebSocket endpoint for real-time backtest updates.

    Clients can connect to this endpoint to receive real-time progress updates.
    """
    await websocket.accept()

    # Subscribe to Redis pub/sub for this backtest
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"backtest:updates:{backtest_id}")

    try:
        while True:
            # Get message from Redis pub/sub
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if message and message["type"] == "message":
                # Parse and send update to WebSocket client
                update_data = json.loads(message["data"])

                ws_message = WebSocketMessage(
                    type="progress",
                    backtest_id=backtest_id,
                    data=update_data,
                )

                await websocket.send_json(ws_message.dict())

            # Check if WebSocket is still connected
            # This is done by sending a ping (FastAPI handles pong automatically)
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for backtest {backtest_id}")
    except Exception as e:
        logger.error(f"WebSocket error for backtest {backtest_id}: {str(e)}")
    finally:
        await pubsub.unsubscribe(f"backtest:updates:{backtest_id}")
        await pubsub.close()


# ========================================================================
# Error Handlers
# ========================================================================

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions."""
    return JSONResponse(
        status_code=400,
        content=BacktestError(
            error="Invalid request",
            detail=str(exc),
        ).dict(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG", "false").lower() == "true" else None,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8001")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )