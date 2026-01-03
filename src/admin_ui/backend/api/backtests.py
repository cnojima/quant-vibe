"""
Backtest execution and results API endpoints.

Provides endpoints to run backtests and view results.
"""

import asyncio
import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from quant_vibe.utils import now_utc
import pandas as pd

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings
from backtest.config_loader import BacktestConfig
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.utils.backtest_helpers import _convert_decimals_to_float

router = APIRouter()

# Track running backtests (persistent storage)
def _get_backtest_state_file() -> Path:
    """Get path to backtest state file."""
    from admin_ui.backend.config import get_settings
    settings = get_settings()
    state_dir = settings.logs_dir / "backtest_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "running_backtests.json"

def _load_backtests() -> dict[str, dict[str, Any]]:
    """Load backtest state from file."""
    import json
    state_file = _get_backtest_state_file()
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_backtests(backtests: dict[str, dict[str, Any]]):
    """Save backtest state to file."""
    import json
    state_file = _get_backtest_state_file()
    try:
        with open(state_file, 'w') as f:
            json.dump(backtests, f, indent=2, default=str)
    except Exception as e:
        print(f"Error saving backtest state: {e}")

# Load existing state on module init
_running_backtests: dict[str, dict[str, Any]] = _load_backtests()


def _get_timescale_store() -> TimescaleStore:
    """Get TimescaleDB connection based on environment configuration."""
    use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"

    if use_remote:
        return TimescaleStore(
            host=os.getenv("REMOTE_TIMESCALE_HOST"),
            port=int(os.getenv("REMOTE_TIMESCALE_PORT", "5432")),
            database=os.getenv("REMOTE_TIMESCALE_DB"),
            user=os.getenv("REMOTE_TIMESCALE_USER"),
            password=os.getenv("REMOTE_TIMESCALE_PASSWORD"),
        )
    else:
        return TimescaleStore()  # Uses TIMESCALE_* env vars


class BacktestRequest(BaseModel):
    """Backtest execution request."""

    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: Optional[float] = 100000.0  # Default $100k
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
    _running_backtests[backtest_id]["started_at"] = now_utc()
    _save_backtests(_running_backtests)

    try:
        # Build command to run backtest
        cmd = [
            "python",
            str(settings.project_root / "scripts" / "run_backtest.py"),
            "--strategy",
            request.strategy_name,
            "--start-date",
            request.start_date.strftime("%Y-%m-%d"),
            "--end-date",
            request.end_date.strftime("%Y-%m-%d"),
        ]

        # Add initial capital if provided
        if request.initial_capital is not None:
            cmd.extend(["--initial-capital", str(request.initial_capital)])

        # Add backtest ID to ensure database and API use the same ID
        cmd.extend(["--backtest-id", backtest_id])

        # Add DTE parameters if provided
        if request.parameters:
            if "min_dte" in request.parameters:
                cmd.extend(["--min-dte", str(request.parameters["min_dte"])])
            if "max_dte" in request.parameters:
                cmd.extend(["--max-dte", str(request.parameters["max_dte"])])
            if "max_trades_daily" in request.parameters:
                cmd.extend(["--max-trades-daily", str(request.parameters["max_trades_daily"])])

        # Run backtest as subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(settings.project_root),
        )

        # Wait for process to complete (with timeout for long-running backtests)
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=600.0  # 10 minute timeout for longer backtests
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            _running_backtests[backtest_id]["status"] = "failed"
            _running_backtests[backtest_id]["completed_at"] = now_utc()
            _running_backtests[backtest_id]["error"] = "Backtest timed out (exceeded 10 minutes)"
            _save_backtests(_running_backtests)
            return

        if process.returncode == 0:
            # Success - find result files
            result_files = find_latest_backtest_results(request.strategy_name)

            # Wait for database writes to complete before marking as completed
            # This prevents race condition where frontend fetches incomplete data
            max_retries = 10
            retry_count = 0
            db_ready = False

            while retry_count < max_retries and not db_ready:
                try:
                    ts_store = _get_timescale_store()
                    try:
                        # Check if backtest data is in database
                        backtest_run = ts_store.get_backtest_run(backtest_id)
                        if backtest_run:
                            # Verify we have trades and equity data
                            trades_df = ts_store.get_backtest_trades(backtest_id)
                            equity_df = ts_store.get_backtest_equity_curve(backtest_id)

                            if not trades_df.empty and not equity_df.empty:
                                db_ready = True
                                print(f"Database verification successful for {backtest_id}: {len(trades_df)} trades, {len(equity_df)} equity points")
                            else:
                                print(f"Database check {retry_count + 1}/{max_retries}: Backtest exists but data incomplete (trades: {len(trades_df)}, equity: {len(equity_df)})")
                        else:
                            print(f"Database check {retry_count + 1}/{max_retries}: Backtest not found yet")
                    finally:
                        ts_store.close()
                except Exception as e:
                    print(f"Database check {retry_count + 1}/{max_retries} failed: {e}")

                if not db_ready:
                    await asyncio.sleep(0.5)  # Wait 500ms before retry
                    retry_count += 1

            if not db_ready:
                print(f"WARNING: Database verification failed after {max_retries} retries, marking as completed anyway")

            _running_backtests[backtest_id]["status"] = "completed"
            _running_backtests[backtest_id]["completed_at"] = now_utc()
            _running_backtests[backtest_id]["result_files"] = result_files
            _save_backtests(_running_backtests)
        else:
            # Failed - capture both stdout and stderr for better error messages
            error_parts = []
            if stderr:
                error_parts.append("STDERR: " + stderr.decode("utf-8"))
            if stdout:
                # Get last 50 lines of stdout for context
                stdout_lines = stdout.decode("utf-8").split('\n')
                last_lines = stdout_lines[-50:] if len(stdout_lines) > 50 else stdout_lines
                error_parts.append("STDOUT (last 50 lines): " + '\n'.join(last_lines))

            error_msg = '\n\n'.join(error_parts) if error_parts else "Unknown error"
            _running_backtests[backtest_id]["status"] = "failed"
            _running_backtests[backtest_id]["completed_at"] = now_utc()
            _running_backtests[backtest_id]["error"] = error_msg
            _save_backtests(_running_backtests)

    except Exception as e:
        _running_backtests[backtest_id]["status"] = "failed"
        _running_backtests[backtest_id]["completed_at"] = now_utc()
        _running_backtests[backtest_id]["error"] = str(e)
        _save_backtests(_running_backtests)


def find_latest_backtest_results(strategy_name: str) -> Optional[dict[str, str]]:
    """
    Find the latest result files for a strategy.

    Args:
        strategy_name: Name of the strategy

    Returns:
        Dict with paths to result files (trades, equity)
    """
    settings = get_settings()

    # Check both reports/backtests (default output) and logs/backtests
    possible_dirs = [
        settings.project_root / "reports" / "backtests",
        settings.logs_dir / "backtests",
    ]

    all_trades_files = []
    all_equity_files = []

    for results_dir in possible_dirs:
        if results_dir.exists():
            all_trades_files.extend(results_dir.glob(f"{strategy_name}_trades_*.csv"))
            all_equity_files.extend(results_dir.glob(f"{strategy_name}_equity_*.csv"))

    if not all_trades_files or not all_equity_files:
        return None

    # Get most recent files
    latest_trades = max(all_trades_files, key=lambda p: p.stat().st_mtime)
    latest_equity = max(all_equity_files, key=lambda p: p.stat().st_mtime)

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
    backtest_id = f"{request.strategy_name}_{now_utc().strftime('%Y%m%d_%H%M%S')}"

    # Initialize status
    _running_backtests[backtest_id] = {
        "backtest_id": backtest_id,
        "status": "pending",
        "request": request.dict(),
    }
    _save_backtests(_running_backtests)

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

    Checks both database and in-memory state.

    Args:
        backtest_id: Backtest ID
        current_user: Authenticated user

    Returns:
        Backtest status
    """
    # First check in-memory state (for running backtests)
    if backtest_id in _running_backtests:
        return _running_backtests[backtest_id]

    # Then check database (for completed backtests)
    try:
        ts_store = _get_timescale_store()
        try:
            backtest_run = ts_store.get_backtest_run(backtest_id)
            if backtest_run:
                # Convert to format expected by frontend
                return {
                    "backtest_id": backtest_run['backtest_id'],
                    "status": backtest_run['status'],
                    "started_at": backtest_run.get('started_at').isoformat() if backtest_run.get('started_at') else None,
                    "completed_at": backtest_run.get('completed_at').isoformat() if backtest_run.get('completed_at') else None,
                    "error": backtest_run.get('error_message'),
                    "result_files": None,  # Database-backed backtests don't have file paths
                }
        finally:
            ts_store.close()
    except Exception as e:
        print(f"Error checking database for backtest status: {e}")

    # Not found in either location
    raise HTTPException(status_code=404, detail="Backtest not found")


@router.get("/{backtest_id}/results")
async def get_backtest_results(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get the results of a completed backtest.

    Fetches from PostgreSQL database first, falls back to CSV files if not found.

    Args:
        backtest_id: Backtest ID
        current_user: Authenticated user

    Returns:
        Backtest results (trades and equity data)
    """
    # Try fetching from PostgreSQL database first
    try:
        ts_store = _get_timescale_store()
        try:
            # Get backtest metadata
            backtest_run = ts_store.get_backtest_run(backtest_id)
            print(f"Database lookup for {backtest_id}: {'Found' if backtest_run else 'Not found'}")

            if backtest_run:
                # Get trades and equity curve from database
                trades_df = ts_store.get_backtest_trades(backtest_id)
                equity_df = ts_store.get_backtest_equity_curve(backtest_id)

                # Get underlying price bars for the backtest date range
                underlying_data = []
                underlying_fetch_error = None
                try:
                    start_date = backtest_run.get('start_date')
                    end_date = backtest_run.get('end_date')
                    print(f"📊 Fetching underlying bars for backtest {backtest_id}")
                    print(f"  Start date: {start_date}, End date: {end_date}")

                    if start_date and end_date:
                        # Fetch underlying bars from database (returns List[UnderlyingBar])
                        underlying_bars = ts_store.get_underlying_bars(
                            ticker='SPX',
                            start_time=start_date,
                            end_time=end_date
                        )
                        print(f"  Retrieved {len(underlying_bars)} underlying bars")

                        if underlying_bars:
                            underlying_df = pd.DataFrame([bar.model_dump() for bar in underlying_bars])
                            underlying_df = _convert_decimals_to_float(underlying_df)

                            # Set timestamp as index
                            if 'timestamp' in underlying_df.columns:
                                underlying_df = underlying_df.set_index('timestamp')
                            # Downsample for multi-day backtests to reduce data size
                            duration_days = (end_date - start_date).days
                            num_bars = len(underlying_df)

                            # Determine downsampling strategy based on duration
                            # Target: ~500-1000 data points for chart rendering
                            max_points = 1000

                            # Ensure index is DatetimeIndex for resampling
                            if not isinstance(underlying_df.index, pd.DatetimeIndex):
                                print(f"  WARNING: Index is not DatetimeIndex, it's {type(underlying_df.index)}")
                                underlying_df.index = pd.to_datetime(underlying_df.index)

                            # Use time-based resampling (handles gaps/holidays correctly)
                            try:
                                if duration_days > 7:
                                    # > 1 week: use 15-minute bars
                                    underlying_df = underlying_df.resample('15min').agg({
                                        'open': 'first',
                                        'high': 'max',
                                        'low': 'min',
                                        'close': 'last',
                                        'volume': 'sum'
                                    }).dropna()
                                    print(f"  Resampled to 15-min bars: {len(underlying_df)} bars (from {num_bars})")
                                elif duration_days > 2:
                                    # 3-7 days: use 5-minute bars
                                    underlying_df = underlying_df.resample('5min').agg({
                                        'open': 'first',
                                        'high': 'max',
                                        'low': 'min',
                                        'close': 'last',
                                        'volume': 'sum'
                                    }).dropna()
                                    print(f"  Resampled to 5-min bars: {len(underlying_df)} bars (from {num_bars})")
                                else:
                                    # <= 2 days: use all 1-minute bars
                                    print(f"  Using 1-min bars: {len(underlying_df)} bars")
                            except Exception as resample_error:
                                print(f"  ERROR during resampling: {resample_error}")
                                print(f"  Index type: {type(underlying_df.index)}")
                                print(f"  Index sample: {underlying_df.index[:5] if len(underlying_df) > 0 else 'empty'}")
                                # Fall back to simple step sampling
                                if duration_days > 2:
                                    step = 5 if duration_days <= 7 else 15
                                    underlying_df = underlying_df.iloc[::step]
                                    print(f"  Fallback: sampled every {step} bars: {len(underlying_df)} bars")

                            # If still too many points, downsample further using step sampling
                            if len(underlying_df) > max_points:
                                step = len(underlying_df) // max_points
                                underlying_df = underlying_df.iloc[::step]
                                print(f"  Further downsampled to {len(underlying_df)} bars (step={step})")

                            # Reset index to include timestamp as a column
                            underlying_df = underlying_df.reset_index()
                            print(f"  Final bar count: {len(underlying_df)}")
                            print(f"  Sample bar (with timestamp): {underlying_df.iloc[0].to_dict()}")
                            underlying_data = underlying_df.to_dict('records')
                        else:
                            underlying_data = []
                    else:
                        print(f"⚠️  No start/end date found in backtest_run")
                        underlying_fetch_error = "No start/end date in backtest metadata"
                except Exception as e:
                    print(f"❌ ERROR: Could not fetch underlying bars: {e}")
                    import traceback
                    traceback.print_exc()
                    underlying_data = []
                    underlying_fetch_error = str(e)

                # Convert DataFrames to list of dicts for JSON serialization
                trades_data = trades_df.to_dict('records') if not trades_df.empty else []
                equity_data = equity_df.to_dict('records') if not equity_df.empty else []

                # Convert timestamps to ISO strings for JSON serialization
                import math

                for trade in trades_data:
                    # Parse legs JSON
                    if 'legs' in trade and isinstance(trade['legs'], str):
                        trade['legs'] = json.loads(trade['legs'])
                    # Convert timestamp fields
                    for field in ['entry_time', 'exit_time']:
                        if field in trade and trade[field] is not None:
                            if hasattr(trade[field], 'isoformat'):
                                trade[field] = trade[field].isoformat()
                    # Convert NaN/Inf to None for JSON serialization
                    for key, value in list(trade.items()):
                        if isinstance(value, float):
                            if math.isnan(value) or math.isinf(value):
                                trade[key] = None

                for point in equity_data:
                    # Convert timestamp to ISO string
                    if 'timestamp' in point and point['timestamp'] is not None:
                        if hasattr(point['timestamp'], 'isoformat'):
                            point['timestamp'] = point['timestamp'].isoformat()
                    # Convert NaN/Inf to None for JSON serialization
                    for key, value in list(point.items()):
                        if isinstance(value, float):
                            if math.isnan(value) or math.isinf(value):
                                point[key] = None

                for bar in underlying_data:
                    # Convert timestamp to ISO string
                    if 'timestamp' in bar and bar['timestamp'] is not None:
                        if hasattr(bar['timestamp'], 'isoformat'):
                            bar['timestamp'] = bar['timestamp'].isoformat()
                    # Convert NaN/Inf to None for JSON serialization
                    for key, value in list(bar.items()):
                        if isinstance(value, float):
                            if math.isnan(value) or math.isinf(value):
                                bar[key] = None

                # Build metrics from database (handle None values)
                def safe_float(value, default=0.0):
                    """Safely convert to float, handling None."""
                    return float(value) if value is not None else default

                def safe_int(value, default=0):
                    """Safely convert to int, handling None."""
                    return int(value) if value is not None else default

                # Database stores percentages as 0-100, frontend expects 0-1 for some fields
                metrics = {
                    "total_return": safe_float(backtest_run.get('total_return_pct')),
                    "max_drawdown": safe_float(backtest_run.get('max_drawdown')),
                    "win_rate": safe_float(backtest_run.get('win_rate')) / 100.0,  # Convert 100.0 → 1.0
                    "sharpe_ratio": safe_float(backtest_run.get('sharpe_ratio')),
                    "total_trades": safe_int(backtest_run.get('num_trades')),
                    "num_winning_trades": safe_int(backtest_run.get('num_winning_trades')),
                    "num_losing_trades": safe_int(backtest_run.get('num_losing_trades')),
                    "avg_win": safe_float(backtest_run.get('avg_win')),
                    "avg_loss": safe_float(backtest_run.get('avg_loss')),
                    "profit_factor": safe_float(backtest_run.get('profit_factor')),
                }

                # Get strategy parameters
                parameters = backtest_run.get('parameters', {})
                if isinstance(parameters, str):
                    import json
                    parameters = json.loads(parameters)

                print(f"✅ Returning backtest results:")
                print(f"  Trades: {len(trades_data)}")
                print(f"  Equity curve points: {len(equity_data)}")
                print(f"  Underlying bars: {len(underlying_data)}")
                if underlying_fetch_error:
                    print(f"  ⚠️  Underlying fetch error: {underlying_fetch_error}")

                return {
                    "backtest_id": backtest_id,
                    "trades": trades_data,
                    "equity_curve": equity_data,
                    "underlying_bars": underlying_data,
                    "metrics": metrics,
                    "parameters": parameters or {},
                    "strategy_name": backtest_run.get('strategy_name'),
                    "start_date": backtest_run.get('start_date').isoformat() if backtest_run.get('start_date') else None,
                    "end_date": backtest_run.get('end_date').isoformat() if backtest_run.get('end_date') else None,
                    "initial_capital": safe_float(backtest_run.get('initial_capital'), default=100000.0),
                    "source": "database",
                    "debug": {
                        "underlying_fetch_error": underlying_fetch_error,
                        "underlying_count": len(underlying_data),
                    } if underlying_fetch_error else None,
                }
        finally:
            ts_store.close()
    except Exception as e:
        print(f"Failed to fetch from database: {e}, falling back to CSV files")
        import traceback
        traceback.print_exc()

    # Fallback to CSV files (legacy behavior) - only if backtest exists in memory
    if backtest_id not in _running_backtests:
        raise HTTPException(
            status_code=404,
            detail=f"Backtest '{backtest_id}' not found in database or in-memory state"
        )

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

    # Calculate basic metrics from the data
    metrics = calculate_metrics(trades_data, equity_data)

    return {
        "backtest_id": backtest_id,
        "trades": trades_data,
        "equity_curve": equity_data,  # Frontend expects this name
        "metrics": metrics,
        "source": "csv",
    }


@router.get("/history")
async def get_backtest_history(
    limit: int = 50,
    strategy_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """
    Get history of recent backtests from PostgreSQL database.

    Args:
        limit: Maximum number of backtests to return
        strategy_name: Filter by strategy name (optional)
        current_user: Authenticated user

    Returns:
        List of past backtests
    """
    try:
        ts_store = _get_timescale_store()
        try:
            # Fetch backtest history from database
            history = ts_store.get_backtest_history(
                strategy_name=strategy_name,
                limit=limit,
            )

            # Convert datetime objects to ISO strings for JSON serialization
            for backtest in history:
                for key in ['created_at', 'started_at', 'completed_at', 'start_date', 'end_date']:
                    if key in backtest:
                        value = backtest[key]
                        if value is not None:
                            # Handle both datetime and date objects
                            if hasattr(value, 'isoformat'):
                                backtest[key] = value.isoformat()
                            else:
                                backtest[key] = str(value)
                        # Leave None as None for proper JSON null serialization

                # Parse parameters JSON if it's a string
                if 'parameters' in backtest and isinstance(backtest['parameters'], str):
                    try:
                        backtest['parameters'] = json.loads(backtest['parameters'])
                    except:
                        backtest['parameters'] = {}

                # Convert numeric types to native Python types for JSON
                for key in ['total_return_pct', 'win_rate', 'sharpe_ratio', 'max_drawdown',
                           'num_trades', 'final_capital', 'initial_capital']:
                    if key in backtest and backtest[key] is not None:
                        if hasattr(backtest[key], 'item'):
                            backtest[key] = backtest[key].item()
                        elif isinstance(backtest[key], (int, float)):
                            backtest[key] = float(backtest[key]) if '.' in str(backtest[key]) or isinstance(backtest[key], float) else int(backtest[key])

            return {
                "backtests": history,
                "total": len(history),
                "source": "database",
            }
        finally:
            ts_store.close()
    except Exception as e:
        print(f"Failed to fetch history from database: {e}, using in-memory state")

        # Fallback to in-memory state
        history = list(_running_backtests.values())

        # Safe sorting - handle both datetime and string types
        def get_sort_key(x):
            """Get sortable key from started_at, handling both datetime and string."""
            started = x.get("started_at")
            if started is None:
                return datetime.min
            if isinstance(started, str):
                try:
                    return datetime.fromisoformat(started.replace('Z', '+00:00'))
                except:
                    return datetime.min
            return started

        history.sort(key=get_sort_key, reverse=True)

        return {
            "backtests": history[:limit],
            "total": len(history),
            "source": "memory",
        }


@router.delete("/{backtest_id}")
async def delete_backtest(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Delete a backtest and all associated data.

    Args:
        backtest_id: Backtest ID to delete
        current_user: Authenticated user

    Returns:
        Success message
    """
    # Try deleting from database first
    try:
        ts_store = _get_timescale_store()
        try:
            deleted = ts_store.delete_backtest(backtest_id)
            if deleted:
                return {
                    "success": True,
                    "message": f"Backtest {backtest_id} deleted successfully",
                    "source": "database",
                }
        finally:
            ts_store.close()
    except Exception as e:
        print(f"Failed to delete from database: {e}")

    # Also remove from in-memory state if present
    if backtest_id in _running_backtests:
        del _running_backtests[backtest_id]
        _save_backtests(_running_backtests)
        return {
            "success": True,
            "message": f"Backtest {backtest_id} deleted from memory",
            "source": "memory",
        }

    # Not found in either location
    raise HTTPException(
        status_code=404,
        detail=f"Backtest {backtest_id} not found"
    )


@router.delete("/all/confirm")
async def delete_all_backtests(
    current_user: User = Depends(get_current_user),
):
    """
    Delete ALL backtests from database and filesystem.

    WARNING: This is a destructive operation that cannot be undone!

    Args:
        current_user: Authenticated user

    Returns:
        Summary of deleted items
    """
    deleted_count = 0
    deleted_files = []
    errors = []

    # Delete from database
    try:
        ts_store = _get_timescale_store()
        try:
            # Get all backtest IDs first
            history = ts_store.get_backtest_history(limit=10000)
            backtest_ids = [b['backtest_id'] for b in history]

            # Delete each backtest from database
            for backtest_id in backtest_ids:
                try:
                    ts_store.delete_backtest(backtest_id)
                    deleted_count += 1
                except Exception as e:
                    errors.append(f"Failed to delete {backtest_id} from database: {e}")
        finally:
            ts_store.close()
    except Exception as e:
        errors.append(f"Database error: {e}")

    # Delete report files from filesystem
    settings = get_settings()
    reports_dir = settings.project_root / "reports" / "backtests"

    if reports_dir.exists():
        try:
            import shutil
            # Get list of files before deletion for reporting
            for file_path in reports_dir.glob("*"):
                if file_path.is_file():
                    deleted_files.append(str(file_path.name))

            # Remove all files in the directory
            for file_path in reports_dir.glob("*"):
                try:
                    if file_path.is_file():
                        file_path.unlink()
                    elif file_path.is_dir():
                        shutil.rmtree(file_path)
                except Exception as e:
                    errors.append(f"Failed to delete file {file_path}: {e}")

        except Exception as e:
            errors.append(f"Filesystem error: {e}")

    # Clear in-memory state
    _running_backtests.clear()
    _save_backtests(_running_backtests)

    return {
        "success": True,
        "message": f"Deleted {deleted_count} backtests from database and {len(deleted_files)} files from filesystem",
        "deleted_count": deleted_count,
        "deleted_files_count": len(deleted_files),
        "errors": errors if errors else None,
    }


@router.get("/strategies")
async def list_strategies(current_user: User = Depends(get_current_user)):
    """
    List available strategies from backtest.yaml configuration.

    Args:
        current_user: Authenticated user

    Returns:
        List of available strategies with their enabled status
    """
    settings = get_settings()
    config_path = settings.project_root / "config" / "backtest.yaml"

    try:
        # Load backtest configuration
        backtest_config = BacktestConfig(str(config_path))

        # Get all strategies from config (both enabled and disabled)
        all_strategies_config = backtest_config.config.get('strategies', {}).get('enabled', [])

        # Import strategy metadata for descriptions
        try:
            from admin_ui.backend.api.strategies import STRATEGY_METADATA
        except ImportError:
            STRATEGY_METADATA = {}

        # Build list of strategies
        strategies = []
        for strategy_config in all_strategies_config:
            name = strategy_config.get('name')
            enabled = strategy_config.get('enabled', False)

            # Get description from metadata, fallback to generic description
            metadata = STRATEGY_METADATA.get(name, {})
            description = metadata.get('description', f'{name} strategy')

            # Format display name (convert snake_case to Title Case)
            display_name = ' '.join(word.capitalize() for word in name.split('_'))

            strategies.append({
                "name": name,
                "display_name": display_name,
                "description": description,
                "enabled": enabled,
            })

        return {
            "strategies": strategies,
            "count": len(strategies),
        }

    except Exception as e:
        # Fallback to empty list if config can't be loaded
        print(f"Error loading strategies from config: {e}")
        return {
            "strategies": [],
            "count": 0,
            "error": str(e),
        }


def calculate_metrics(trades: list[dict], equity_curve: list[dict]) -> dict[str, Any]:
    """
    Calculate performance metrics from trades and equity curve.

    Args:
        trades: List of trade dictionaries
        equity_curve: List of equity curve points

    Returns:
        Dictionary of performance metrics
    """
    if not trades or not equity_curve:
        return {}

    # Convert string values to floats
    pnls = [float(t.get('pnl', 0)) for t in trades]
    win_trades = [p for p in pnls if p > 0]

    # Get initial and final equity
    initial_equity = float(equity_curve[0].get('portfolio_value', 100000))
    final_equity = float(equity_curve[-1].get('portfolio_value', initial_equity))

    # Calculate returns
    total_return = ((final_equity - initial_equity) / initial_equity) * 100

    # Calculate max drawdown from equity curve
    max_drawdown = 0
    if equity_curve:
        drawdowns = [float(row.get('drawdown', 0)) for row in equity_curve]
        max_drawdown = min(drawdowns) if drawdowns else 0

    # Calculate win rate
    win_rate = len(win_trades) / len(trades) if trades else 0

    # Calculate Sharpe ratio (simplified - using trade returns)
    if len(pnls) > 1:
        import statistics
        mean_return = statistics.mean(pnls)
        std_return = statistics.stdev(pnls)
        sharpe_ratio = (mean_return / std_return) if std_return > 0 else 0
    else:
        sharpe_ratio = 0

    return {
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "sharpe_ratio": sharpe_ratio,
        "total_trades": len(trades),
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
