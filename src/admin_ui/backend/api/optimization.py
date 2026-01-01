"""
Strategy optimization API endpoints.

Provides endpoints to run parameter optimization (grid search and walk-forward analysis).
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings

router = APIRouter()

# Track running optimizations (persistent storage)
def _get_optimization_state_file() -> Path:
    """Get path to optimization state file."""
    from admin_ui.backend.config import get_settings
    settings = get_settings()
    state_dir = settings.logs_dir / "optimization_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "running_optimizations.json"

def _load_optimizations() -> dict[str, dict[str, Any]]:
    """Load optimization state from file."""
    state_file = _get_optimization_state_file()
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_optimizations(optimizations: dict[str, dict[str, Any]]):
    """Save optimization state to file."""
    state_file = _get_optimization_state_file()
    try:
        with open(state_file, 'w') as f:
            json.dump(optimizations, f, indent=2, default=str)
    except Exception as e:
        print(f"Error saving optimization state: {e}")

# Load existing state on module init
_running_optimizations: dict[str, dict[str, Any]] = _load_optimizations()


class OptimizationRequest(BaseModel):
    """Optimization execution request."""

    strategy_name: str
    train_start_date: datetime
    train_end_date: datetime
    test_start_date: Optional[datetime] = None
    test_end_date: Optional[datetime] = None
    initial_capital: Optional[float] = 100000.0
    optimization_type: str = "grid_search"  # grid_search or walk_forward
    param_grid: Optional[dict[str, list[Any]]] = None  # Parameter grid to search
    walk_forward_config: Optional[dict[str, Any]] = None  # Walk-forward specific config


class OptimizationStatus(BaseModel):
    """Optimization execution status."""

    optimization_id: str
    status: str  # pending, running, completed, failed
    progress: Optional[int] = 0  # Progress percentage
    current_combination: Optional[int] = None
    total_combinations: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result_files: Optional[dict[str, str]] = None


class OptimizationResult(BaseModel):
    """Optimization results."""

    optimization_id: str
    strategy_name: str
    optimization_type: str
    best_params: Optional[dict[str, Any]] = None
    best_sharpe: Optional[float] = None
    best_return: Optional[float] = None
    top_results: Optional[list[dict[str, Any]]] = None
    walk_forward_summary: Optional[dict[str, Any]] = None


async def run_optimization_task(optimization_id: str, request: OptimizationRequest):
    """
    Background task to run optimization.

    Args:
        optimization_id: Unique ID for this optimization run
        request: Optimization parameters
    """
    settings = get_settings()

    # Update status
    _running_optimizations[optimization_id]["status"] = "running"
    _running_optimizations[optimization_id]["started_at"] = datetime.now()
    _save_optimizations(_running_optimizations)

    try:
        # Build command to run optimization
        cmd = [
            "python",
            str(settings.project_root / "scripts" / "optimize_strategy.py"),
            "--strategy",
            request.strategy_name,
            "--train-start",
            request.train_start_date.strftime("%Y-%m-%d"),
            "--train-end",
            request.train_end_date.strftime("%Y-%m-%d"),
        ]

        # Add test dates if provided
        if request.test_start_date:
            cmd.extend(["--test-start", request.test_start_date.strftime("%Y-%m-%d")])
        if request.test_end_date:
            cmd.extend(["--test-end", request.test_end_date.strftime("%Y-%m-%d")])

        # Add initial capital if provided
        if request.initial_capital is not None:
            cmd.extend(["--initial-capital", str(request.initial_capital)])

        # Add walk-forward flag if requested
        if request.optimization_type == "walk_forward":
            cmd.append("--walk-forward")

        # Add output directory with optimization ID
        output_dir = settings.project_root / "results" / "optimization" / optimization_id
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--output-dir", str(output_dir)])

        print(f"[Optimization] Running: {' '.join(cmd)}")

        # Run optimization as subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(settings.project_root),
        )

        # Wait for process to complete (with timeout for long-running optimizations)
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=3600.0  # 1 hour timeout
            )

            if process.returncode == 0:
                # Success - parse results
                _running_optimizations[optimization_id]["status"] = "completed"
                _running_optimizations[optimization_id]["completed_at"] = datetime.now()
                _running_optimizations[optimization_id]["progress"] = 100

                # Find result files
                result_files = {}
                for file in output_dir.glob("*.csv"):
                    result_files[file.stem] = str(file)

                _running_optimizations[optimization_id]["result_files"] = result_files

                print(f"[Optimization] {optimization_id} completed successfully")

            else:
                # Failed
                error_msg = stderr.decode() if stderr else "Unknown error"
                _running_optimizations[optimization_id]["status"] = "failed"
                _running_optimizations[optimization_id]["error"] = error_msg
                _running_optimizations[optimization_id]["completed_at"] = datetime.now()

                print(f"[Optimization] {optimization_id} failed: {error_msg}")

        except asyncio.TimeoutError:
            # Timeout
            process.kill()
            _running_optimizations[optimization_id]["status"] = "failed"
            _running_optimizations[optimization_id]["error"] = "Optimization timeout (1 hour limit exceeded)"
            _running_optimizations[optimization_id]["completed_at"] = datetime.now()

            print(f"[Optimization] {optimization_id} timed out")

        _save_optimizations(_running_optimizations)

    except Exception as e:
        # Unexpected error
        _running_optimizations[optimization_id]["status"] = "failed"
        _running_optimizations[optimization_id]["error"] = str(e)
        _running_optimizations[optimization_id]["completed_at"] = datetime.now()
        _save_optimizations(_running_optimizations)

        print(f"[Optimization] {optimization_id} error: {e}")
        import traceback
        traceback.print_exc()


@router.post("/run", response_model=dict)
async def run_optimization(
    request: OptimizationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    Start a new optimization run.

    Args:
        request: Optimization parameters
        background_tasks: FastAPI background tasks
        current_user: Authenticated user

    Returns:
        Optimization ID and status
    """
    # Generate unique ID
    optimization_id = f"opt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Initialize optimization state
    _running_optimizations[optimization_id] = {
        "optimization_id": optimization_id,
        "status": "pending",
        "request": request.dict(),
        "created_at": datetime.now(),
        "progress": 0,
    }
    _save_optimizations(_running_optimizations)

    # Start background task
    background_tasks.add_task(run_optimization_task, optimization_id, request)

    return {
        "optimization_id": optimization_id,
        "status": "pending",
        "message": "Optimization started"
    }


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
        Optimization status
    """
    if optimization_id not in _running_optimizations:
        raise HTTPException(status_code=404, detail="Optimization not found")

    opt = _running_optimizations[optimization_id]

    return OptimizationStatus(
        optimization_id=optimization_id,
        status=opt["status"],
        progress=opt.get("progress", 0),
        current_combination=opt.get("current_combination"),
        total_combinations=opt.get("total_combinations"),
        started_at=opt.get("started_at"),
        completed_at=opt.get("completed_at"),
        error=opt.get("error"),
        result_files=opt.get("result_files"),
    )


@router.get("/results/{optimization_id}", response_model=OptimizationResult)
async def get_optimization_results(
    optimization_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get results of a completed optimization.

    Args:
        optimization_id: Optimization ID
        current_user: Authenticated user

    Returns:
        Optimization results
    """
    if optimization_id not in _running_optimizations:
        raise HTTPException(status_code=404, detail="Optimization not found")

    opt = _running_optimizations[optimization_id]

    if opt["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Optimization is {opt['status']}, not completed"
        )

    # Parse result files
    import pandas as pd

    result_files = opt.get("result_files", {})
    best_params = None
    best_sharpe = None
    best_return = None
    top_results = []
    walk_forward_summary = None

    # Parse grid search results
    grid_search_file = None
    for key, path in result_files.items():
        if "grid_search" in key:
            grid_search_file = path
            break

    if grid_search_file and os.path.exists(grid_search_file):
        df = pd.read_csv(grid_search_file)

        if len(df) > 0:
            # Get best result (highest Sharpe ratio)
            best_row = df.iloc[0]
            best_params = eval(best_row["params"]) if isinstance(best_row["params"], str) else best_row["params"]
            best_sharpe = float(best_row["sharpe_ratio"])
            best_return = float(best_row["total_return"])

            # Get top 10 results
            top_results = df.head(10).to_dict(orient="records")

    # Parse walk-forward results if available
    wf_file = None
    for key, path in result_files.items():
        if "walk_forward" in key:
            wf_file = path
            break

    if wf_file and os.path.exists(wf_file):
        df = pd.read_csv(wf_file)

        if len(df) > 0:
            walk_forward_summary = {
                "num_periods": len(df),
                "avg_out_of_sample_sharpe": float(df["out_of_sample_sharpe"].mean()),
                "avg_out_of_sample_return": float(df["out_of_sample_return"].mean()),
                "avg_sharpe_degradation": float(df["sharpe_degradation"].mean()),
                "avg_return_degradation": float(df["return_degradation"].mean()),
            }

    return OptimizationResult(
        optimization_id=optimization_id,
        strategy_name=opt["request"]["strategy_name"],
        optimization_type=opt["request"]["optimization_type"],
        best_params=best_params,
        best_sharpe=best_sharpe,
        best_return=best_return,
        top_results=top_results,
        walk_forward_summary=walk_forward_summary,
    )


@router.get("/history", response_model=list[dict])
async def get_optimization_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """
    Get history of optimization runs.

    Args:
        limit: Maximum number of results to return
        current_user: Authenticated user

    Returns:
        List of optimization runs (most recent first)
    """
    # Sort by created_at descending
    history = sorted(
        _running_optimizations.values(),
        key=lambda x: x.get("created_at", datetime.min),
        reverse=True
    )

    return history[:limit]


@router.delete("/{optimization_id}")
async def delete_optimization(
    optimization_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Delete an optimization and its result files.

    Args:
        optimization_id: Optimization ID
        current_user: Authenticated user

    Returns:
        Success message
    """
    if optimization_id not in _running_optimizations:
        raise HTTPException(status_code=404, detail="Optimization not found")

    opt = _running_optimizations[optimization_id]

    # Delete result files if they exist
    result_files = opt.get("result_files", {})
    deleted_files = 0

    for path in result_files.values():
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted_files += 1
            except Exception as e:
                print(f"Error deleting file {path}: {e}")

    # Remove from state
    del _running_optimizations[optimization_id]
    _save_optimizations(_running_optimizations)

    return {
        "message": "Optimization deleted",
        "deleted_files": deleted_files
    }
