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
from admin_ui.backend.redis_client import get_redis
from backtest.config_loader import BacktestConfig
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.utils.backtest_helpers import _convert_decimals_to_float
from quant_vibe.services.backtest_service import BacktestService

router = APIRouter()

# Global backtest service instance
_backtest_service: Optional[BacktestService] = None


def get_backtest_service() -> BacktestService:
    """Get or create BacktestService singleton."""
    global _backtest_service
    if _backtest_service is None:
        settings = get_settings()
        redis_client = get_redis()

        # Build database connection string
        db_url = (
            f"postgresql://{settings.timescale_user}:{settings.timescale_password}@"
            f"{settings.timescale_host}:{settings.timescale_port}/{settings.timescale_db}"
        )

        _backtest_service = BacktestService(
            redis_client=redis_client,
            db_connection_string=db_url,
            data_cache_ttl=3600,  # 1 hour
            results_base_dir=str(settings.project_root / "reports" / "backtests"),
        )
    return _backtest_service

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
    Background task to run a backtest using BacktestService.

    Args:
        backtest_id: Unique ID for this backtest run
        request: Backtest parameters
    """
    service = get_backtest_service()

    try:
        # Extract parameters
        min_dte = request.parameters.get("min_dte", 0) if request.parameters else 0
        max_dte = request.parameters.get("max_dte", 60) if request.parameters else 60
        timeframe = request.parameters.get("timeframe", "5min") if request.parameters else "5min"
        max_trades_daily = request.parameters.get("max_trades_daily") if request.parameters else None

        # Build strategy parameters (filter out backtest-level params)
        strategy_params = {}
        if request.parameters:
            # Copy all params except the ones we use at backtest level
            backtest_level_params = {"min_dte", "max_dte", "timeframe"}
            strategy_params = {
                k: v for k, v in request.parameters.items()
                if k not in backtest_level_params
            }

        # Add max_trades_daily if provided
        if max_trades_daily is not None:
            strategy_params["max_trades_daily"] = max_trades_daily

        # Create backtest with our provided ID
        from quant_vibe.utils.timestamp_utils import to_utc

        await service.create_backtest(
            strategy_name=request.strategy_name,
            start_date=to_utc(request.start_date),
            end_date=to_utc(request.end_date),
            initial_capital=request.initial_capital or 100000.0,
            parameters=strategy_params,
            min_dte=min_dte,
            max_dte=max_dte,
            timeframe=timeframe,
            ticker="SPX",
            backtest_id=backtest_id,  # Pass our ID directly
        )

        # Update legacy state tracking for backward compatibility
        _running_backtests[backtest_id] = {
            "backtest_id": backtest_id,
            "status": "running",
            "started_at": now_utc(),
            "progress": 0,
            "message": "Starting backtest...",
            "request": request.dict(),
        }
        _save_backtests(_running_backtests)

        # Run the backtest
        await service.run_backtest(backtest_id)

        # Update legacy state from service state
        service_state = service.running_backtests[backtest_id]
        _running_backtests[backtest_id]["status"] = service_state["status"]
        _running_backtests[backtest_id]["completed_at"] = now_utc()
        _running_backtests[backtest_id]["progress"] = service_state["progress"]
        _running_backtests[backtest_id]["message"] = service_state["message"]
        _save_backtests(_running_backtests)

    except Exception as e:
        # Update both service and legacy state
        if backtest_id in service.running_backtests:
            service.running_backtests[backtest_id]["status"] = "failed"
            service.running_backtests[backtest_id]["error"] = str(e)

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
        "progress": 0,
        "message": "Initializing backtest...",
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

    Checks service state, in-memory state, and database.

    Args:
        backtest_id: Backtest ID
        current_user: Authenticated user

    Returns:
        Backtest status
    """
    # First check service state (for running backtests with real-time progress)
    service = get_backtest_service()
    try:
        service_status = await service.get_status(backtest_id)
        return service_status
    except ValueError:
        pass  # Not found in service, try legacy state

    # Then check in-memory state (for legacy/compatibility)
    if backtest_id in _running_backtests:
        return _running_backtests[backtest_id]

    # Finally check database (for completed backtests)
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
                        print("⚠️  No start/end date found in backtest_run")
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

                print("✅ Returning backtest results:")
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


@router.post("/{backtest_id}/cancel")
async def cancel_backtest(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Cancel a running backtest.

    Args:
        backtest_id: Backtest ID to cancel
        current_user: Authenticated user

    Returns:
        Cancellation status
    """
    service = get_backtest_service()

    try:
        cancelled = await service.cancel_backtest(backtest_id)
        if cancelled:
            return {
                "success": True,
                "message": f"Backtest {backtest_id} cancelled",
            }
        else:
            return {
                "success": False,
                "message": f"Backtest {backtest_id} is not running",
            }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
                # Also clean up from service if present
                service = get_backtest_service()
                if backtest_id in service.running_backtests:
                    del service.running_backtests[backtest_id]

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


# ==================== Analysis Endpoints ====================


@router.post("/{backtest_id}/analyze")
async def analyze_backtest(
    backtest_id: str,
    outlier_std_devs: float = 2.0,
    current_user: User = Depends(get_current_user),
):
    """
    Trigger analysis for a completed backtest.

    This endpoint analyzes trade performance, identifies outlier wins/losses,
    extracts patterns, and generates actionable recommendations.

    Args:
        backtest_id: Backtest identifier
        outlier_std_devs: Standard deviation threshold for outlier detection (default: 2.0)

    Returns:
        Complete analysis result with structured findings and narrative summaries
    """
    from quant_vibe.analytics.backtest_analyzer import BacktestAnalyzer

    try:
        # Verify backtest exists
        ts_store = _get_timescale_store()
        backtest_run = ts_store.get_backtest_run(backtest_id)
        if not backtest_run:
            raise HTTPException(
                status_code=404,
                detail=f"Backtest {backtest_id} not found"
            )

        # Check if backtest is completed
        if backtest_run.get("status") != "completed":
            raise HTTPException(
                status_code=400,
                detail=f"Backtest {backtest_id} is not completed (status: {backtest_run.get('status')})"
            )

        # Run analysis
        analyzer = BacktestAnalyzer(backtest_id)
        result = await analyzer.analyze(outlier_std_devs)

        # Save to database
        analysis_id = ts_store.save_backtest_analysis(
            backtest_id=result.backtest_id,
            total_trades=result.total_trades,
            outlier_threshold_pct=result.outlier_threshold_pct,
            num_big_winners=result.num_big_winners,
            num_big_losers=result.num_big_losers,
            findings=result.findings.model_dump(mode='json'),
            summary_markdown=result.summary_markdown,
            recommendations_markdown=result.recommendations_markdown,
            analyzer_version=result.analyzer_version,
        )

        # Add analysis_id to result
        result.analysis_id = analysis_id

        return result.model_dump(mode='json')

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.get("/{backtest_id}/analysis")
async def get_backtest_analysis(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Get saved analysis results for a backtest.

    Args:
        backtest_id: Backtest identifier

    Returns:
        Analysis results if available, 404 if not found
    """
    ts_store = _get_timescale_store()

    try:
        analysis = ts_store.get_backtest_analysis(backtest_id)

        if not analysis:
            raise HTTPException(
                status_code=404,
                detail=f"No analysis found for backtest {backtest_id}. Run analysis first."
            )

        return analysis

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve analysis: {str(e)}"
        )


@router.delete("/{backtest_id}/analysis")
async def delete_backtest_analysis(
    backtest_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    Delete analysis results for a backtest.

    Note: Analysis is also automatically deleted when the backtest is deleted
    due to CASCADE delete constraint.

    Args:
        backtest_id: Backtest identifier

    Returns:
        Deletion status
    """
    ts_store = _get_timescale_store()

    try:
        deleted_count = ts_store.delete_backtest_analysis(backtest_id)

        return {
            "status": "deleted",
            "backtest_id": backtest_id,
            "deleted_count": deleted_count,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete analysis: {str(e)}"
        )
