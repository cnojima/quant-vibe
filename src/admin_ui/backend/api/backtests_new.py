"""
Backtest execution and results API endpoints.

Provides endpoints to run backtests and view results.
This is the new version that uses the backtest service API instead of subprocess.
"""

import os
import json
import httpx
from datetime import datetime
from typing import Any, Optional, List, Dict
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from pydantic import BaseModel


from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings
from quant_vibe.logging import get_logger
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.utils import convert_decimals_to_float, now_utc
from quant_vibe.utils.json_utils import sanitize_for_json
from backtest.config_loader import BacktestConfig


logger = get_logger(__name__)

router = APIRouter()

# Get backtest service URL from environment
BACKTEST_SERVICE_URL = os.getenv("BACKTEST_SERVICE_URL", "http://localhost:8001")


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
    ticker: Optional[str] = "$SPX"
    timeframe: Optional[str] = "5min"
    description: Optional[str] = None


class BacktestStatus(BaseModel):
    """Backtest execution status."""

    backtest_id: str
    status: str  # pending, running, completed, failed, cancelled
    progress: float
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    current_step: Optional[str] = None


class BacktestListResponse(BaseModel):
    """Response for listing backtests."""

    backtests: List[BacktestStatus]
    total: int
    offset: int
    limit: int


@router.post("/run", response_model=BacktestStatus)
async def run_backtest(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
) -> BacktestStatus:
    """
    Run a backtest for the specified strategy.

    This endpoint now delegates to the backtest service API instead of running subprocess.
    """
    try:
        # Prepare request data for backtest service
        service_request = {
            "strategy_name": request.strategy_name,
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "initial_capital": request.initial_capital,
            "params": request.parameters or {},
            "ticker": request.ticker,
            "timeframe": request.timeframe,
            "description": request.description,
        }

        # Make HTTP request to backtest service
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKTEST_SERVICE_URL}/api/backtests",
                json=service_request,
                timeout=30.0,
            )

            if response.status_code != 200:
                error_detail = response.json().get("detail", "Unknown error")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Backtest service error: {error_detail}",
                )

            result = response.json()

            # Return status
            return BacktestStatus(
                backtest_id=result["id"],
                status=result["status"],
                progress=0.0,
                started_at=None,
                completed_at=None,
                error=None,
                current_step="Queued for processing",
            )

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to backtest service: {e}")
        raise HTTPException(
            status_code=503,
            detail="Backtest service is unavailable. Please try again later.",
        )
    except Exception as e:
        logger.error(f"Failed to run backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{backtest_id}/status", response_model=BacktestStatus)
async def get_backtest_status(
    backtest_id: str,
    user: User = Depends(get_current_user),
) -> BacktestStatus:
    """
    Get the status of a running or completed backtest.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BACKTEST_SERVICE_URL}/api/backtests/{backtest_id}",
                timeout=10.0,
            )

            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Backtest not found")
            elif response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Backtest service error: {response.text}",
                )

            data = response.json()

            return BacktestStatus(
                backtest_id=data["id"],
                status=data["status"],
                progress=data.get("progress", 0.0),
                started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
                completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
                error=data.get("error"),
                current_step=data.get("current_step"),
            )

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to backtest service: {e}")
        raise HTTPException(
            status_code=503,
            detail="Backtest service is unavailable",
        )


@router.get("/list", response_model=BacktestListResponse)
async def list_backtests(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
) -> BacktestListResponse:
    """
    List all backtests with optional filtering.
    """
    try:
        params = {}
        if status:
            params["status"] = status
        params["limit"] = limit
        params["offset"] = offset

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BACKTEST_SERVICE_URL}/api/backtests",
                params=params,
                timeout=10.0,
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Backtest service error: {response.text}",
                )

            data = response.json()

            # Convert to BacktestStatus objects
            backtests = []
            for bt in data["backtests"]:
                backtests.append(BacktestStatus(
                    backtest_id=bt["id"],
                    status=bt["status"],
                    progress=bt.get("progress", 0.0),
                    started_at=datetime.fromisoformat(bt["started_at"]) if bt.get("started_at") else None,
                    completed_at=datetime.fromisoformat(bt["completed_at"]) if bt.get("completed_at") else None,
                    error=bt.get("error"),
                    current_step=bt.get("current_step"),
                ))

            return BacktestListResponse(
                backtests=backtests,
                total=data["total"],
                offset=data["offset"],
                limit=data["limit"],
            )

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to backtest service: {e}")
        raise HTTPException(
            status_code=503,
            detail="Backtest service is unavailable",
        )


@router.delete("/cancel/{backtest_id}")
async def cancel_backtest(
    backtest_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """
    Cancel a running backtest.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{BACKTEST_SERVICE_URL}/api/backtests/{backtest_id}",
                timeout=10.0,
            )

            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="Backtest not found")
            elif response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Backtest service error: {response.text}",
                )

            return response.json()

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to backtest service: {e}")
        raise HTTPException(
            status_code=503,
            detail="Backtest service is unavailable",
        )


@router.get("/results/{backtest_id}")
async def get_backtest_results(
    backtest_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """
    Get detailed results for a completed backtest.

    First tries to get results from the backtest service, then falls back to database.
    """
    try:
        # Try to get results from backtest service
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BACKTEST_SERVICE_URL}/api/backtests/{backtest_id}/results",
                timeout=10.0,
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code != 404:
                logger.warning(f"Backtest service returned {response.status_code}, falling back to database")

    except httpx.RequestError as e:
        logger.warning(f"Failed to connect to backtest service, falling back to database: {e}")

    # Fall back to getting results directly from database
    try:
        ts_store = _get_timescale_store()
        try:
            # Get backtest run
            backtest_run = ts_store.get_backtest_run(backtest_id)
            if not backtest_run:
                raise HTTPException(status_code=404, detail="Backtest not found")

            # Get trades
            trades_df = ts_store.get_backtest_trades(backtest_id)

            # Get equity curve
            equity_df = ts_store.get_backtest_equity_curve(backtest_id)

            # Convert to JSON-serializable format
            result = {
                "backtest_id": backtest_id,
                "strategy_name": backtest_run.get("strategy_name"),
                "start_date": backtest_run.get("start_date").isoformat() if backtest_run.get("start_date") else None,
                "end_date": backtest_run.get("end_date").isoformat() if backtest_run.get("end_date") else None,
                "initial_capital": float(backtest_run.get("initial_capital", 0)),
                "total_return": float(backtest_run.get("total_return", 0)),
                "sharpe_ratio": float(backtest_run.get("sharpe_ratio", 0)) if backtest_run.get("sharpe_ratio") else None,
                "max_drawdown": float(backtest_run.get("max_drawdown", 0)),
                "win_rate": float(backtest_run.get("win_rate", 0)),
                "total_trades": int(backtest_run.get("total_trades", 0)),
                "profit_factor": float(backtest_run.get("profit_factor", 0)) if backtest_run.get("profit_factor") else None,
                "trades": trades_df.to_dict(orient="records") if not trades_df.empty else [],
                "equity_curve": equity_df.to_dict(orient="records") if not equity_df.empty else [],
            }

            # Convert any remaining Decimal values
            result = convert_decimals_to_float(result)

            return result

        finally:
            ts_store.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backtest results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/{backtest_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    backtest_id: str,
):
    """
    WebSocket endpoint for real-time backtest updates.

    Proxies WebSocket connection to the backtest service.
    """
    await websocket.accept()

    try:
        # Connect to backtest service WebSocket
        async with httpx.AsyncClient() as client:
            service_ws_url = f"ws://localhost:8001/ws/backtests/{backtest_id}"

            # For now, we'll poll the status endpoint instead of true WebSocket proxy
            # A proper implementation would use websockets library to proxy
            while True:
                try:
                    # Get current status
                    response = await client.get(
                        f"{BACKTEST_SERVICE_URL}/api/backtests/{backtest_id}",
                        timeout=5.0,
                    )

                    if response.status_code == 200:
                        data = response.json()

                        # Send update to client
                        await websocket.send_json({
                            "type": "status",
                            "data": data,
                        })

                        # Check if completed
                        if data["status"] in ["completed", "failed", "cancelled"]:
                            break

                    # Wait before next poll
                    import asyncio
                    await asyncio.sleep(1.0)

                except Exception as e:
                    logger.error(f"Error polling backtest status: {e}")
                    break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for backtest {backtest_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()


# Legacy endpoints for backward compatibility
@router.get("/status")
async def get_all_backtest_status(
    user: User = Depends(get_current_user),
) -> List[BacktestStatus]:
    """
    Get status of all backtests (legacy endpoint).

    Redirects to the list endpoint with no filtering.
    """
    result = await list_backtests(limit=100, user=user)
    return result.backtests


@router.get("/history")
async def get_backtest_history(
    limit: int = 50,
    strategy_name: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """
    Get history of recent backtests from database.

    Args:
        limit: Maximum number of backtests to return
        strategy_name: Filter by strategy name (optional)
        user: Authenticated user

    Returns:
        List of past backtests from database
    """
    try:
        ts_store = _get_timescale_store()
        try:
            # Fetch backtest history from database
            history_df = ts_store.get_backtest_history(
                strategy_name=strategy_name,
                limit=limit,
            )

            # Convert DataFrame to list of dictionaries
            history = history_df.to_dict('records') if not history_df.empty else []

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
                           'total_trades', 'final_capital', 'initial_capital']:
                    if key in backtest and backtest[key] is not None:
                        if hasattr(backtest[key], 'item'):
                            backtest[key] = backtest[key].item()
                        elif isinstance(backtest[key], (int, float)):
                            backtest[key] = float(backtest[key]) if '.' in str(backtest[key]) or isinstance(backtest[key], float) else int(backtest[key])

            # Sanitize NaN and Infinity values for JSON serialization
            history = sanitize_for_json(history)

            return {
                "backtests": history,
                "total": len(history),
                "source": "database",
            }
        finally:
            ts_store.close()
    except Exception as e:
        logger.warning(f"Failed to fetch history from database: {e}, returning empty list")
        # Return empty list on error
        return {
            "backtests": [],
            "total": 0,
            "source": "database",
            "error": str(e),
        }


@router.get("/strategies")
async def list_strategies(user: User = Depends(get_current_user)):
    """
    List available strategies from backtest.yaml configuration.

    Args:
        user: Authenticated user

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
        logger.error(f"Error loading strategies from config: {e}")
        return {
            "strategies": [],
            "count": 0,
            "error": str(e),
        }