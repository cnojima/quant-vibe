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

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings

# Load .env file to ensure environment variables are available for subprocesses
# In Docker, environment variables are set via docker-compose, but load_dotenv() won't hurt
from quant_vibe.utils import now_utc, to_utc
env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"[Optimization] Loaded .env from {env_path}")
else:
    print(f"[Optimization] No .env file at {env_path}, using docker-compose environment variables")

# Import Pushover notifications
try:
    from quant_vibe.notifications import PushoverNotifier
    PUSHOVER_AVAILABLE = True
except ImportError:
    PUSHOVER_AVAILABLE = False
    print("[Optimization] Pushover notifications not available")

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


def _read_status_file(optimization_id: str) -> dict[str, Any]:
    """
    Read status file and extract latest progress and logs.

    Args:
        optimization_id: Optimization ID

    Returns:
        Dict with latest progress, params, metrics, and recent logs
    """
    settings = get_settings()
    status_file = settings.project_root / "results" / "optimization" / optimization_id / "status.jsonl"

    result = {
        "current_combination": None,
        "total_combinations": None,
        "progress_pct": 0,
        "current_params": None,
        "current_metrics": None,
        "logs": [],
    }

    if not status_file.exists():
        return result

    try:
        # Read all lines (newline-delimited JSON)
        with open(status_file, 'r') as f:
            lines = f.readlines()

        # Keep track of latest progress and collect recent logs
        logs = []
        latest_progress = None

        for line in lines:
            if not line.strip():
                continue

            try:
                entry = json.loads(line)

                if entry.get("type") == "progress":
                    latest_progress = entry
                elif entry.get("type") == "log":
                    logs.append({
                        "timestamp": entry.get("timestamp"),
                        "level": entry.get("level", "INFO"),
                        "message": entry.get("message"),
                    })
            except json.JSONDecodeError:
                continue

        # Extract latest progress info
        if latest_progress:
            result["current_combination"] = latest_progress.get("current_combination")
            result["total_combinations"] = latest_progress.get("total_combinations")
            result["progress_pct"] = latest_progress.get("progress_pct", 0)
            result["current_params"] = latest_progress.get("current_params")
            result["current_metrics"] = latest_progress.get("current_metrics")

        # Keep last 50 log entries
        result["logs"] = logs[-50:]

    except Exception as e:
        print(f"[Optimization] Error reading status file: {e}")

    return result


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
    current_params: Optional[dict[str, Any]] = None
    current_metrics: Optional[dict[str, float]] = None
    current_error: Optional[str] = None  # Error from current backtest (if any)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result_files: Optional[dict[str, str]] = None
    logs: Optional[list[dict[str, Any]]] = None  # Recent log messages


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
    start_time = now_utc()

    # Update status
    _running_optimizations[optimization_id]["status"] = "running"
    _running_optimizations[optimization_id]["started_at"] = start_time
    _save_optimizations(_running_optimizations)

    try:
        # Build command to run optimization
        # Use sys.executable to ensure we use the same Python that's running this backend
        import sys
        cmd = [
            sys.executable,  # Use current Python interpreter
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

        # Add status file for real-time updates
        status_file = output_dir / "status.jsonl"
        cmd.extend(["--status-file", str(status_file)])

        print(f"[Optimization] Running: {' '.join(cmd)}")

        # Build environment for subprocess - inherit parent env and add any missing vars
        import os
        subprocess_env = os.environ.copy()

        # Debug: Check what Pushover vars are in the environment
        pushover_vars = ['PUSHOVER_API_TOKEN', 'PUSHOVER_USER_KEY', 'PUSHOVER_DEVICE', 'PUSHOVER_ENABLED']
        print("[Optimization] Checking Pushover environment variables:")
        for key in pushover_vars:
            value = os.environ.get(key, "NOT_SET")
            if value and value != "NOT_SET":
                masked_value = value[:10] + "..." if 'TOKEN' in key or 'KEY' in key else value
                print(f"[Optimization]   {key}: {masked_value}")
                subprocess_env[key] = value
            else:
                print(f"[Optimization]   {key}: NOT SET")

        # Run optimization as subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(settings.project_root),
            env=subprocess_env,
        )

        # Wait for process to complete (with timeout for long-running optimizations)
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=3600.0  # 1 hour timeout
            )

            if process.returncode == 0:
                # Success - parse results
                end_time = now_utc()
                runtime_minutes = (end_time - start_time).total_seconds() / 60.0

                _running_optimizations[optimization_id]["status"] = "completed"
                _running_optimizations[optimization_id]["completed_at"] = end_time
                _running_optimizations[optimization_id]["progress"] = 100

                # Find result files
                result_files = {}
                for file in output_dir.glob("*.csv"):
                    result_files[file.stem] = str(file)

                _running_optimizations[optimization_id]["result_files"] = result_files

                print(f"[Optimization] {optimization_id} completed successfully")

                # Send success notification
                if PUSHOVER_AVAILABLE:
                    try:
                        # Try to parse results for notification
                        best_sharpe = None
                        best_return = None

                        grid_search_file = None
                        for key, path in result_files.items():
                            if "grid_search" in key:
                                grid_search_file = path
                                break

                        if grid_search_file and os.path.exists(grid_search_file):
                            df = pd.read_csv(grid_search_file)
                            if len(df) > 0:
                                best_sharpe = float(df.iloc[0]["sharpe_ratio"])
                                best_return = float(df.iloc[0]["total_return"])

                        notifier = PushoverNotifier()
                        notifier.send_optimization_complete(
                            strategy_name=request.strategy_name,
                            optimization_id=optimization_id,
                            best_sharpe=best_sharpe,
                            best_return=best_return,
                            runtime_minutes=runtime_minutes,
                        )
                    except Exception as e:
                        print(f"[Optimization] Failed to send success notification: {e}")

            else:
                # Failed
                end_time = now_utc()
                runtime_minutes = (end_time - start_time).total_seconds() / 60.0

                # Build error message from both stdout and stderr
                error_parts = []
                if stdout:
                    stdout_text = stdout.decode().strip()
                    if stdout_text:
                        error_parts.append(f"STDOUT:\n{stdout_text[-1000:]}")  # Last 1000 chars
                if stderr:
                    stderr_text = stderr.decode().strip()
                    if stderr_text:
                        error_parts.append(f"STDERR:\n{stderr_text[-1000:]}")  # Last 1000 chars

                error_msg = "\n\n".join(error_parts) if error_parts else f"Process exited with code {process.returncode}"

                _running_optimizations[optimization_id]["status"] = "failed"
                _running_optimizations[optimization_id]["error"] = error_msg
                _running_optimizations[optimization_id]["completed_at"] = end_time

                print(f"[Optimization] {optimization_id} failed with return code {process.returncode}")
                print(f"[Optimization] Error output: {error_msg[:500]}")

                # Send failure notification
                if PUSHOVER_AVAILABLE:
                    try:
                        notifier = PushoverNotifier()
                        notifier.send_optimization_failed(
                            strategy_name=request.strategy_name,
                            optimization_id=optimization_id,
                            error_message=error_msg,
                            runtime_minutes=runtime_minutes,
                        )
                    except Exception as e:
                        print(f"[Optimization] Failed to send failure notification: {e}")

        except asyncio.TimeoutError:
            # Timeout
            end_time = now_utc()
            runtime_minutes = (end_time - start_time).total_seconds() / 60.0

            process.kill()
            error_msg = "Optimization timeout (1 hour limit exceeded)"
            _running_optimizations[optimization_id]["status"] = "failed"
            _running_optimizations[optimization_id]["error"] = error_msg
            _running_optimizations[optimization_id]["completed_at"] = end_time

            print(f"[Optimization] {optimization_id} timed out")

            # Send timeout notification
            if PUSHOVER_AVAILABLE:
                try:
                    notifier = PushoverNotifier()
                    notifier.send_optimization_failed(
                        strategy_name=request.strategy_name,
                        optimization_id=optimization_id,
                        error_message=error_msg,
                        runtime_minutes=runtime_minutes,
                    )
                except Exception as e:
                    print(f"[Optimization] Failed to send timeout notification: {e}")

        _save_optimizations(_running_optimizations)

    except Exception as e:
        # Unexpected error
        end_time = now_utc()
        runtime_minutes = (end_time - start_time).total_seconds() / 60.0

        error_msg = str(e)
        _running_optimizations[optimization_id]["status"] = "failed"
        _running_optimizations[optimization_id]["error"] = error_msg
        _running_optimizations[optimization_id]["completed_at"] = end_time
        _save_optimizations(_running_optimizations)

        print(f"[Optimization] {optimization_id} error: {e}")
        import traceback
        traceback.print_exc()

        # Send error notification
        if PUSHOVER_AVAILABLE:
            try:
                notifier = PushoverNotifier()
                notifier.send_optimization_failed(
                    strategy_name=request.strategy_name,
                    optimization_id=optimization_id,
                    error_message=error_msg,
                    runtime_minutes=runtime_minutes,
                )
            except Exception as notify_error:
                print(f"[Optimization] Failed to send error notification: {notify_error}")


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
    optimization_id = f"opt_{now_utc().strftime('%Y%m%d_%H%M%S')}"

    # Initialize optimization state
    _running_optimizations[optimization_id] = {
        "optimization_id": optimization_id,
        "status": "pending",
        "request": request.dict(),
        "created_at": now_utc(),
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

    # Read real-time status from status file if running
    status_data = {}
    if opt["status"] == "running":
        status_data = _read_status_file(optimization_id)

    # Extract current_metrics and current_error separately
    current_metrics = status_data.get("current_metrics")
    current_error = None

    # If current_metrics contains an 'error' key, extract it
    if current_metrics and "error" in current_metrics:
        current_error = current_metrics.get("error")
        # Create a copy without the error key (all other values should be floats)
        current_metrics = {k: v for k, v in current_metrics.items() if k != "error"}

    return OptimizationStatus(
        optimization_id=optimization_id,
        status=opt["status"],
        progress=int(status_data.get("progress_pct", opt.get("progress", 0))),
        current_combination=status_data.get("current_combination", opt.get("current_combination")),
        total_combinations=status_data.get("total_combinations", opt.get("total_combinations")),
        current_params=status_data.get("current_params"),
        current_metrics=current_metrics if current_metrics else None,
        current_error=current_error,
        started_at=opt.get("started_at"),
        completed_at=opt.get("completed_at"),
        error=opt.get("error"),
        result_files=opt.get("result_files"),
        logs=status_data.get("logs", []),
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

            # Handle NaN values - convert to None for JSON serialization
            best_sharpe = None if pd.isna(best_row["sharpe_ratio"]) else float(best_row["sharpe_ratio"])
            best_return = None if pd.isna(best_row["total_return"]) else float(best_row["total_return"])

            # Get top 10 results and replace NaN with None for JSON compatibility
            top_results = df.head(10).replace([np.nan, pd.NA], None).to_dict(orient="records")

    # Parse walk-forward results if available
    wf_file = None
    for key, path in result_files.items():
        if "walk_forward" in key:
            wf_file = path
            break

    if wf_file and os.path.exists(wf_file):
        df = pd.read_csv(wf_file)

        if len(df) > 0:
            # Handle NaN values in mean calculations
            def safe_mean(series):
                mean_val = series.mean()
                return None if pd.isna(mean_val) else float(mean_val)

            walk_forward_summary = {
                "num_periods": len(df),
                "avg_out_of_sample_sharpe": safe_mean(df["out_of_sample_sharpe"]),
                "avg_out_of_sample_return": safe_mean(df["out_of_sample_return"]),
                "avg_sharpe_degradation": safe_mean(df["sharpe_degradation"]),
                "avg_return_degradation": safe_mean(df["return_degradation"]),
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
    # Note: created_at might be a string (from JSON) or datetime object
    def get_sort_key(x):
        created_at = x.get("created_at")
        if created_at is None:
            # Return a very old UTC-aware datetime for missing timestamps
            return to_utc(datetime.min)
        if isinstance(created_at, str):
            try:
                # Parse and ensure UTC-aware
                return to_utc(datetime.fromisoformat(created_at))
            except (ValueError, TypeError):
                return to_utc(datetime.min)
        # If already a datetime object, ensure UTC-aware
        return to_utc(created_at)

    history = sorted(
        _running_optimizations.values(),
        key=get_sort_key,
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


@router.delete("/")
async def delete_all_optimizations(
    current_user: User = Depends(get_current_user),
):
    """
    Delete all optimizations and their result files.

    Args:
        current_user: Authenticated user

    Returns:
        Success message with count of deleted optimizations
    """
    settings = get_settings()
    deleted_count = 0
    deleted_files = 0

    # Get all optimization IDs
    optimization_ids = list(_running_optimizations.keys())

    # Delete each optimization
    for optimization_id in optimization_ids:
        opt = _running_optimizations[optimization_id]

        # Delete result files if they exist
        result_files = opt.get("result_files", {})
        for path in result_files.values():
            if os.path.exists(path):
                try:
                    os.remove(path)
                    deleted_files += 1
                except Exception as e:
                    print(f"Error deleting file {path}: {e}")

        # Also try to delete the optimization directory
        output_dir = settings.project_root / "results" / "optimization" / optimization_id
        if output_dir.exists():
            try:
                import shutil
                shutil.rmtree(output_dir)
            except Exception as e:
                print(f"Error deleting directory {output_dir}: {e}")

        deleted_count += 1

    # Clear all optimizations from state
    _running_optimizations.clear()
    _save_optimizations(_running_optimizations)

    return {
        "message": f"Deleted {deleted_count} optimization(s)",
        "deleted_optimizations": deleted_count,
        "deleted_files": deleted_files
    }


@router.post("/test-notification")
async def test_notification(
    current_user: User = Depends(get_current_user),
):
    """
    Send a test notification via Pushover.

    Args:
        current_user: Authenticated user

    Returns:
        Success/failure status
    """
    if not PUSHOVER_AVAILABLE:
        return {
            "sent": False,
            "message": "Pushover notifications not available. Install required packages."
        }

    try:
        notifier = PushoverNotifier()

        if not notifier.enabled:
            return {
                "sent": False,
                "message": "Pushover notifications are disabled. Check PUSHOVER_ENABLED env var and credentials."
            }

        success = notifier.send(
            message="This is a test notification from Quant-Vibe Admin UI. If you received this, your notifications are working correctly!",
            title="🧪 Test Notification",
            priority=0,
            sound="magic",
        )

        if success:
            return {
                "sent": True,
                "message": "Test notification sent successfully!"
            }
        else:
            return {
                "sent": False,
                "message": "Failed to send test notification. Check server logs for details."
            }

    except Exception as e:
        print(f"[Optimization] Test notification error: {e}")
        import traceback
        traceback.print_exc()

        return {
            "sent": False,
            "message": f"Error: {str(e)}"
        }
