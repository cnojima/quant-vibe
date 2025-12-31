"""
Live trading monitoring API endpoints.

Provides endpoints to view live trading status, positions, orders, and events.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.db import timescale

router = APIRouter()


@router.get("/status")
async def get_live_status(current_user: User = Depends(get_current_user)):
    """
    Get current live trading engine status.

    Args:
        current_user: Authenticated user

    Returns:
        Live trading engine status
    """
    engine_state = await timescale.fetch_engine_state()

    if not engine_state:
        return {
            "running": False,
            "message": "No engine state found. Engine may not have started yet.",
        }

    return {
        "running": engine_state.get("state", "").lower() == "running",
        "state": engine_state.get("state"),
        "paper_trading": engine_state.get("paper_trading"),
        "total_bars_processed": engine_state.get("total_bars_processed"),
        "total_signals_generated": engine_state.get("total_signals_generated"),
        "uptime_seconds": engine_state.get("uptime_seconds"),
        "last_update": engine_state.get("timestamp"),
        "metadata": engine_state.get("metadata"),
    }


@router.get("/positions")
async def get_positions(
    status: str = Query("open", regex="^(open|closed|all)$"),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    """
    Get positions.

    Args:
        status: Filter by status (open, closed, all)
        limit: Maximum number of positions to return
        current_user: Authenticated user

    Returns:
        List of positions
    """
    if status == "open":
        positions = await timescale.fetch_active_positions(limit=limit)
    elif status == "closed":
        positions = await timescale.fetch_closed_positions(limit=limit)
    else:  # all
        active = await timescale.fetch_active_positions(limit=limit // 2)
        closed = await timescale.fetch_closed_positions(limit=limit // 2)
        positions = active + closed

    return {
        "positions": positions,
        "count": len(positions),
        "filter": status,
    }


@router.get("/orders")
async def get_orders(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
):
    """
    Get open orders.

    Args:
        limit: Maximum number of orders to return
        current_user: Authenticated user

    Returns:
        List of open orders
    """
    orders = await timescale.fetch_open_orders(limit=limit)

    return {
        "orders": orders,
        "count": len(orders),
    }


@router.get("/events")
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, regex="^(info|warning|error)$"),
    current_user: User = Depends(get_current_user),
):
    """
    Get recent events.

    Args:
        limit: Maximum number of events to return
        event_type: Filter by event type (signal, order, error, etc.)
        severity: Filter by severity (info, warning, error)
        current_user: Authenticated user

    Returns:
        List of recent events
    """
    events = await timescale.fetch_recent_events(
        limit=limit,
        event_type=event_type,
        severity=severity,
    )

    return {
        "events": events,
        "count": len(events),
        "filters": {
            "event_type": event_type,
            "severity": severity,
        },
    }


@router.get("/stats")
async def get_trading_stats(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """
    Get aggregate trading statistics.

    Args:
        start_time: Start of time range (optional)
        end_time: End of time range (optional)
        current_user: Authenticated user

    Returns:
        Trading statistics
    """
    stats = await timescale.fetch_trading_stats(
        start_time=start_time,
        end_time=end_time,
    )

    return {
        "stats": stats,
        "time_range": {
            "start": start_time.isoformat() if start_time else None,
            "end": end_time.isoformat() if end_time else None,
        },
    }
