"""
Strategy optimization API endpoints (v2 - using OptimizationService).

Provides endpoints to run parameter optimization with async execution,
Redis caching, and dynamic parameter grid generation.
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings
from admin_ui.backend.redis_client import get_redis
from quant_vibe.services.optimization_service import OptimizationService
from quant_vibe.services.optimization_task_queue import OptimizationTaskQueue
from quant_vibe.utils import now_utc
from quant_vibe.logging import get_logger

logger = get_logger(__name__)

# Load .env file
env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

router = APIRouter()

# Global optimization service instance (initialized on startup)
_optimization_service: Optional[OptimizationService] = None
_task_queue: Optional[OptimizationTaskQueue] = None


def get_task_queue() -> OptimizationTaskQueue:
    """Get or initialize task queue."""
    global _task_queue

    if _task_queue is None:
        logger.info("[API] Initializing OptimizationTaskQueue...")
        redis_client = get_redis()
        _task_queue = OptimizationTaskQueue(redis_client)
        logger.info("[API] OptimizationTaskQueue initialized successfully")

    return _task_queue


def get_optimization_service() -> OptimizationService:
    """Get or initialize optimization service."""
    global _optimization_service

    if _optimization_service is None:
        logger.info("[API] Initializing OptimizationService...")
        settings = get_settings()
        redis_client = get_redis()

        # Build database connection string
        db_host = os.getenv("TIMESCALE_HOST", "localhost")
        db_port = os.getenv("TIMESCALE_PORT", "5432")
        db_name = os.getenv("TIMESCALE_DB", "options_data")
        db_user = os.getenv("TIMESCALE_USER", "quantvibe")
        db_password = os.getenv("TIMESCALE_PASSWORD", "quantvibe_dev")

        db_connection_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        logger.info(f"[API] DB connection: {db_user}@{db_host}:{db_port}/{db_name}")

        _optimization_service = OptimizationService(
            redis_client=redis_client,
            db_connection_string=db_connection_string,
            data_cache_ttl=3600,  # 1 hour
            results_base_dir=str(settings.project_root / "results" / "optimization"),
        )
        logger.info("[API] OptimizationService initialized successfully")

    return _optimization_service


# ============================================================================
# Request/Response Models
# ============================================================================

class OptimizationRequest(BaseModel):
    """Optimization execution request."""

    strategy_name: str = Field(..., description="Strategy name")
    train_start_date: datetime = Field(..., description="Training period start date")
    train_end_date: datetime = Field(..., description="Training period end date")
    test_start_date: Optional[datetime] = Field(None, description="Test period start date (for walk-forward)")
    test_end_date: Optional[datetime] = Field(None, description="Test period end date (for walk-forward)")
    initial_capital: float = Field(100000.0, description="Initial capital")
    optimization_type: str = Field("grid_search", description="Optimization type (grid_search or walk_forward)")
    param_grid: Optional[dict[str, list[Any]]] = Field(None, description="Custom parameter grid")
    fixed_params: Optional[dict[str, Any]] = Field(None, description="Fixed parameters")
    underlying_ticker: str = Field("SPX", description="Underlying ticker")
    timeframe: str = Field("5min", description="Time aggregation (1min, 5min, 15min, 1hour, daily)")


class OptimizationStatus(BaseModel):
    """Optimization execution status."""

    optimization_id: str
    status: str  # pending, running, completed, failed, cancelled
    progress_current: Optional[int] = 0
    progress_total: Optional[int] = 0
    progress_pct: Optional[float] = 0
    estimated_completion_time: Optional[datetime] = None
    current_params: Optional[dict[str, Any]] = None
    current_metrics: Optional[dict[str, float]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    strategy_name: Optional[str] = None
    optimization_type: Optional[str] = None
    total_combinations: Optional[int] = None
    best_params: Optional[dict[str, Any]] = None
    best_sharpe_ratio: Optional[float] = None
    best_total_return: Optional[float] = None
    best_win_rate: Optional[float] = None


class OptimizationResult(BaseModel):
    """Optimization results."""

    optimization_id: str
    status: str
    strategy_name: str
    optimization_type: str
    total_combinations: int
    best_params: Optional[dict[str, Any]] = None
    best_sharpe_ratio: Optional[float] = None
    best_total_return: Optional[float] = None
    best_win_rate: Optional[float] = None
    results: list[dict[str, Any]]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ParamGridRequest(BaseModel):
    """Request to generate or validate parameter grid."""

    strategy_name: str
    custom_ranges: Optional[dict[str, list[Any]]] = None
    optimize_only: Optional[list[str]] = None


class ParamGridValidationRequest(BaseModel):
    """Request to validate parameter grid."""

    strategy_name: str
    param_grid: dict[str, list[Any]]
    max_combinations: int = 200


class ParamGridResponse(BaseModel):
    """Parameter grid response."""

    strategy_name: str
    param_grid: dict[str, list[Any]]
    total_combinations: int


class ParamGridValidationResponse(BaseModel):
    """Parameter grid validation response."""

    valid: bool
    total_combinations: int
    warnings: list[str]
    errors: list[str]


class FixedParamsResponse(BaseModel):
    """Fixed parameters response."""

    strategy_name: str
    fixed_params: dict[str, Any]


class CacheStatusResponse(BaseModel):
    """Cache status response."""

    cache_key: str
    underlying_ticker: str
    start_date: datetime
    end_date: datetime
    timeframe: str
    num_options_rows: int
    num_underlying_rows: int
    data_size_mb: float
    hit_count: int
    last_accessed_at: datetime


# ============================================================================
# Parameter Grid Endpoints
# ============================================================================

@router.get("/param-grid/{strategy_name}", response_model=ParamGridResponse)
async def get_param_grid(
    strategy_name: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get auto-generated parameter grid for a strategy.

    Args:
        strategy_name: Strategy name
        current_user: Authenticated user

    Returns:
        Parameter grid with total combinations
    """
    try:
        service = get_optimization_service()
        param_grid = service.generate_param_grid(strategy_name)
        total_combinations = service.count_permutations(param_grid)

        return ParamGridResponse(
            strategy_name=strategy_name,
            param_grid=param_grid,
            total_combinations=total_combinations,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/param-grid/generate", response_model=ParamGridResponse)
async def generate_param_grid(
    request: ParamGridRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Generate parameter grid with custom ranges or filters.

    Args:
        request: Generation request
        current_user: Authenticated user

    Returns:
        Parameter grid with total combinations
    """
    try:
        service = get_optimization_service()
        param_grid = service.generate_param_grid(
            strategy_name=request.strategy_name,
            custom_ranges=request.custom_ranges,
            optimize_only=request.optimize_only,
        )
        total_combinations = service.count_permutations(param_grid)

        return ParamGridResponse(
            strategy_name=request.strategy_name,
            param_grid=param_grid,
            total_combinations=total_combinations,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/param-grid/validate", response_model=ParamGridValidationResponse)
async def validate_param_grid(
    request: ParamGridValidationRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Validate parameter grid and check combination count.

    Args:
        request: Validation request
        current_user: Authenticated user

    Returns:
        Validation result with warnings and errors
    """
    try:
        service = get_optimization_service()
        result = service.validate_param_grid(
            strategy_name=request.strategy_name,
            param_grid=request.param_grid,
            max_combinations=request.max_combinations,
        )

        return ParamGridValidationResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/fixed-params/{strategy_name}", response_model=FixedParamsResponse)
async def get_fixed_params(
    strategy_name: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get fixed (non-optimizable) parameters for a strategy.

    Args:
        strategy_name: Strategy name
        current_user: Authenticated user

    Returns:
        Fixed parameters
    """
    try:
        service = get_optimization_service()
        fixed_params = service.get_fixed_params(strategy_name)

        return FixedParamsResponse(
            strategy_name=strategy_name,
            fixed_params=fixed_params,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Optimization Execution Endpoints
# ============================================================================

@router.post("/run", response_model=dict)
async def run_optimization(
    request: OptimizationRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Start a new optimization run.

    Args:
        request: Optimization parameters
        current_user: Authenticated user

    Returns:
        Optimization ID and status
    """
    try:
        logger.info(f"[API] Received optimization request: strategy={request.strategy_name}, dates={request.train_start_date} to {request.train_end_date}")
        service = get_optimization_service()
        logger.info("[API] Got optimization service")

        # Generate or validate param grid
        if request.param_grid:
            logger.info(f"[API] Validating custom param grid with {len(request.param_grid)} parameters")
            # Validate custom grid
            validation = service.validate_param_grid(
                strategy_name=request.strategy_name,
                param_grid=request.param_grid,
            )
            if not validation["valid"]:
                raise ValueError(f"Invalid parameter grid: {', '.join(validation['errors'])}")

            param_grid = request.param_grid
        else:
            logger.info("[API] Auto-generating param grid")
            # Auto-generate grid
            param_grid = service.generate_param_grid(request.strategy_name)

        # Create optimization
        logger.info("[API] Creating optimization in database...")
        optimization_id = await service.create_optimization(
            strategy_name=request.strategy_name,
            train_start_date=request.train_start_date,
            train_end_date=request.train_end_date,
            param_grid=param_grid,
            optimization_type=request.optimization_type,
            test_start_date=request.test_start_date,
            test_end_date=request.test_end_date,
            initial_capital=request.initial_capital,
            fixed_params=request.fixed_params,
            underlying_ticker=request.underlying_ticker,
            timeframe=request.timeframe,
        )
        logger.info(f"[API] Created optimization {optimization_id}")

        # Publish task to queue (worker will pick it up)
        logger.info(f"[API] Publishing optimization task {optimization_id} to queue...")
        task_queue = get_task_queue()
        await task_queue.publish_task(
            optimization_id=optimization_id,
            task_data={
                "strategy_name": request.strategy_name,
                "train_start_date": request.train_start_date.isoformat(),
                "train_end_date": request.train_end_date.isoformat(),
                "optimization_type": request.optimization_type,
            }
        )
        logger.info(f"[API] Optimization {optimization_id} task queued for worker")

        # Get queue size
        queue_size = await task_queue.get_queue_size()

        return {
            "optimization_id": optimization_id,
            "status": "queued",
            "message": f"Optimization queued for execution (queue size: {queue_size})",
            "queue_position": queue_size,
        }

    except Exception as e:
        logger.error(f"[API] Optimization request failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{optimization_id}", response_model=OptimizationStatus)
async def get_optimization_status(
    optimization_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get status of a running or completed optimization.

    Args:
        optimization_id: Optimization ID
        current_user: Authenticated user

    Returns:
        Optimization status with progress and ETA
    """
    try:
        logger.debug(f"[API] Status request for {optimization_id}")
        service = get_optimization_service()
        status = await service.get_status(optimization_id)

        # Calculate progress percentage
        progress_pct = 0
        if status["progress_total"] and status["progress_total"] > 0:
            progress_pct = (status["progress_current"] / status["progress_total"]) * 100

        # Parse datetime strings
        estimated_completion_time = None
        if status["estimated_completion_time"]:
            estimated_completion_time = datetime.fromisoformat(status["estimated_completion_time"])

        started_at = None
        if status["started_at"]:
            started_at = datetime.fromisoformat(status["started_at"])

        completed_at = None
        if status["completed_at"]:
            completed_at = datetime.fromisoformat(status["completed_at"])

        return OptimizationStatus(
            optimization_id=optimization_id,
            status=status["status"],
            progress_current=status["progress_current"],
            progress_total=status["progress_total"],
            progress_pct=progress_pct,
            estimated_completion_time=estimated_completion_time,
            started_at=started_at,
            completed_at=completed_at,
            error_message=status["error_message"],
            strategy_name=status["strategy_name"],
            optimization_type=status["optimization_type"],
            total_combinations=status["total_combinations"],
            best_params=status["best_params"],
            best_sharpe_ratio=status["best_sharpe_ratio"],
            best_total_return=status["best_total_return"],
            best_win_rate=status["best_win_rate"],
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{optimization_id}", response_model=OptimizationResult)
async def get_optimization_results(
    optimization_id: str,
    limit: int = 100,
    sort_by: str = "sharpe_ratio",
    current_user: User = Depends(get_current_user),
):
    """
    Get results of a completed optimization.

    Args:
        optimization_id: Optimization ID
        limit: Maximum number of results to return
        sort_by: Sort by (sharpe_ratio, total_return, win_rate)
        current_user: Authenticated user

    Returns:
        Optimization results with top N combinations
    """
    try:
        service = get_optimization_service()
        results = await service.get_results(
            optimization_id=optimization_id,
            limit=limit,
            sort_by=sort_by,
        )

        # Parse datetime strings
        started_at = None
        if results["started_at"]:
            started_at = datetime.fromisoformat(results["started_at"])

        completed_at = None
        if results["completed_at"]:
            completed_at = datetime.fromisoformat(results["completed_at"])

        return OptimizationResult(
            optimization_id=optimization_id,
            status=results["status"],
            strategy_name=results["strategy_name"],
            optimization_type=results["optimization_type"],
            total_combinations=results["total_combinations"],
            best_params=results["best_params"],
            best_sharpe_ratio=results["best_sharpe_ratio"],
            best_total_return=results["best_total_return"],
            best_win_rate=results["best_win_rate"],
            results=results["results"],
            started_at=started_at,
            completed_at=completed_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel/{optimization_id}")
async def cancel_optimization(
    optimization_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Cancel a queued or running optimization.

    Args:
        optimization_id: Optimization ID
        current_user: Authenticated user

    Returns:
        Success message
    """
    try:
        task_queue = get_task_queue()
        service = get_optimization_service()

        # Try to cancel queued task first
        cancelled_from_queue = await task_queue.cancel_task(optimization_id)

        if cancelled_from_queue:
            # Update DB status
            await service._update_optimization_status(optimization_id, "cancelled")
            return {
                "message": f"Optimization {optimization_id} cancelled (removed from queue)",
                "cancelled_from_queue": True
            }

        # If not in queue, try to cancel running optimization
        try:
            await service.cancel_optimization(optimization_id)
            return {
                "message": f"Optimization {optimization_id} cancellation requested (running in worker)",
                "cancelled_from_queue": False
            }
        except ValueError:
            # Not running either
            raise HTTPException(
                status_code=404,
                detail=f"Optimization {optimization_id} not found in queue or running optimizations"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{optimization_id}")
async def delete_optimization(
    optimization_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Delete an optimization run.

    Args:
        optimization_id: Optimization ID
        current_user: Authenticated user

    Returns:
        Success message
    """
    # TODO: Implement deletion from database and filesystem
    raise HTTPException(status_code=501, detail="Not implemented yet")


# ============================================================================
# Cache Management Endpoints
# ============================================================================

@router.get("/cache/status")
async def get_cache_status(
    current_user: User = Depends(get_current_user),
):
    """
    Get data cache statistics.

    Args:
        current_user: Authenticated user

    Returns:
        Cache status information
    """
    # TODO: Query optimization_cache_status table
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/cache/clear")
async def clear_cache(
    cache_key: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    Clear cached data.

    Args:
        cache_key: Specific cache key to clear (or None for all)
        current_user: Authenticated user

    Returns:
        Number of keys deleted
    """
    try:
        service = get_optimization_service()
        deleted = await service.clear_cache(cache_key=cache_key)

        return {
            "message": f"Cleared {deleted} cache keys",
            "deleted_count": deleted,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# History Endpoint (for backward compatibility)
# ============================================================================

@router.get("/queue/status")
async def get_queue_status(
    current_user: User = Depends(get_current_user),
):
    """
    Get optimization queue status.

    Args:
        current_user: Authenticated user

    Returns:
        Queue size and worker status
    """
    try:
        task_queue = get_task_queue()
        queue_size = await task_queue.get_queue_size()

        return {
            "queue_size": queue_size,
            "worker_active": True,  # TODO: Add worker health check
            "message": f"{queue_size} optimization(s) in queue"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_optimization_history(
    current_user: User = Depends(get_current_user),
):
    """
    Get list of all optimization runs.

    Args:
        current_user: Authenticated user

    Returns:
        List of optimization runs
    """
    # TODO: Query optimization_runs table for all runs
    raise HTTPException(status_code=501, detail="Not implemented yet - query DB for history")
