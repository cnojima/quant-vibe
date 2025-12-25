"""
Backtest execution and results API endpoints.

Provides endpoints to run backtests and view results.
"""

import asyncio
import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings

router = APIRouter()

# Track running backtests
_running_backtests: dict[str, dict[str, Any]] = {}


class BacktestRequest(BaseModel):
    """Backtest execution request."""

    strategy_name: str
    start_date: datetime
    end_date: datetime
    parameters: Optional[dict[str, Any]] = None


class BacktestStatus(BaseModel):
    """Backtest execution status."""

    backtest_id: str
    status: str  # pending, running, completed, failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result_files: Optional[dict[str, str]] = None


async def run_backtest_task(backtest_id: str, request: BacktestRequest):
    """
    Background task to run a backtest.

    Args:
        backtest_id: Unique ID for this backtest run
        request: Backtest parameters
    """
    settings = get_settings()

    # Update status
    _running_backtests[backtest_id]["status"] = "running"
    _running_backtests[backtest_id]["started_at"] = datetime.now()

    try:
        # Build command to run backtest
        cmd = [
            "python",
            str(settings.project_root / "scripts" / "run_backtest.py"),
            "--strategy",
            request.strategy_name,
        ]

        # Run backtest as subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(settings.project_root),
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            # Success - find result files
            result_files = find_latest_backtest_results(request.strategy_name)

            _running_backtests[backtest_id]["status"] = "completed"
            _running_backtests[backtest_id]["completed_at"] = datetime.now()
            _running_backtests[backtest_id]["result_files"] = result_files
        else:
            # Failed
            error_msg = stderr.decode("utf-8") if stderr else "Unknown error"
            _running_backtests[backtest_id]["status"] = "failed"
            _running_backtests[backtest_id]["completed_at"] = datetime.now()
            _running_backtests[backtest_id]["error"] = error_msg

    except Exception as e:
        _running_backtests[backtest_id]["status"] = "failed"
        _running_backtests[backtest_id]["completed_at"] = datetime.now()
        _running_backtests[backtest_id]["error"] = str(e)


def find_latest_backtest_results(strategy_name: str) -> Optional[dict[str, str]]:
    """
    Find the latest result files for a strategy.

    Args:
        strategy_name: Name of the strategy

    Returns:
        Dict with paths to result files (trades, equity)
    """
    settings = get_settings()
    results_dir = settings.logs_dir / "backtests"

    if not results_dir.exists():
        return None

    # Find all files for this strategy
    trades_files = list(results_dir.glob(f"{strategy_name}_trades_*.csv"))
    equity_files = list(results_dir.glob(f"{strategy_name}_equity_*.csv"))

    if not trades_files or not equity_files:
        return None

    # Get most recent files
    latest_trades = max(trades_files, key=lambda p: p.stat().st_mtime)
    latest_equity = max(equity_files, key=lambda p: p.stat().st_mtime)

    return {
        "trades": str(latest_trades),
        "equity": str(latest_equity),
    }


@router.post("/run")
async def run_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    Run a backtest asynchronously.

    Args:
        request: Backtest parameters
        background_tasks: FastAPI background tasks
        current_user: Authenticated user

    Returns:
        Backtest ID for status checking
    """
    # Generate unique backtest ID
    backtest_id = f"{request.strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Initialize status
    _running_backtests[backtest_id] = {
        "backtest_id": backtest_id,
        "status": "pending",
        "request": request.dict(),
    }

    # Start backtest in background
    background_tasks.add_task(run_backtest_task, backtest_id, request)

    return {
        "backtest_id": backtest_id,
        "status": "pending",
        "message": "Backtest started",
    }


@router.get("/{backtest_id}/status")
async def get_backtest_status(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the status of a running or completed backtest.

    Args:
        backtest_id: Backtest ID
        current_user: Authenticated user

    Returns:
        Backtest status
    """
    if backtest_id not in _running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")

    return _running_backtests[backtest_id]


@router.get("/{backtest_id}/results")
async def get_backtest_results(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the results of a completed backtest.

    Args:
        backtest_id: Backtest ID
        current_user: Authenticated user

    Returns:
        Backtest results (trades and equity data)
    """
    if backtest_id not in _running_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")

    backtest = _running_backtests[backtest_id]

    if backtest["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Backtest is {backtest['status']}, not completed"
        )

    result_files = backtest.get("result_files")
    if not result_files:
        raise HTTPException(status_code=404, detail="Result files not found")

    # Load and return CSV data
    trades_data = load_csv_file(result_files["trades"])
    equity_data = load_csv_file(result_files["equity"])

    return {
        "backtest_id": backtest_id,
        "trades": trades_data,
        "equity": equity_data,
    }


@router.get("/history")
async def get_backtest_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """
    Get history of recent backtests.

    Args:
        limit: Maximum number of backtests to return
        current_user: Authenticated user

    Returns:
        List of past backtests
    """
    # Return in-memory backtest history
    history = list(_running_backtests.values())
    history.sort(key=lambda x: x.get("started_at", datetime.min), reverse=True)

    return {
        "backtests": history[:limit],
        "total": len(history),
    }


@router.get("/strategies")
async def list_strategies(current_user: User = Depends(get_current_user)):
    """
    List available strategies.

    Args:
        current_user: Authenticated user

    Returns:
        List of available strategies
    """
    # TODO: Dynamically load from backtest.yaml or strategy registry
    # For now, return hardcoded list

    strategies = [
        {
            "name": "bullish_vertical_put",
            "display_name": "Bullish Vertical Put",
            "description": "0 DTE bullish vertical put spread strategy",
        },
        {
            "name": "bullish_vertical_call",
            "display_name": "Bullish Vertical Call",
            "description": "0 DTE bullish vertical call spread strategy",
        },
    ]

    return {
        "strategies": strategies,
        "count": len(strategies),
    }


def load_csv_file(file_path: str, max_rows: int = 1000) -> list[dict]:
    """
    Load a CSV file and return as list of dicts.

    Args:
        file_path: Path to CSV file
        max_rows: Maximum rows to return

    Returns:
        List of row dictionaries
    """
    try:
        with open(file_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)[:max_rows]
            return rows
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load CSV file: {str(e)}"
        )
