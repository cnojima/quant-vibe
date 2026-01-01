"""
Live trading monitoring API endpoints.

Provides endpoints to view live trading status, positions, orders, and events.
"""

from datetime import datetime, date
from typing import Optional
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Query, HTTPException

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.db import timescale

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from quant_vibe.reporting import DailyPerformanceReport
from live_trading_service.state_store import StateStore

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
    status: str = Query("all", regex="^(open|filled|rejected|cancelled|all)$"),
    current_user: User = Depends(get_current_user),
):
    """
    Get orders with optional status filter.

    Args:
        limit: Maximum number of orders to return
        status: Filter by status (open, filled, rejected, cancelled, all)
        current_user: Authenticated user

    Returns:
        List of orders
    """
    orders = await timescale.fetch_open_orders(limit=limit, status_filter=status)

    return {
        "orders": orders,
        "count": len(orders),
        "filter": status,
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


@router.get("/daily-report")
async def get_daily_report(
    report_date: Optional[date] = Query(None, description="Report date (YYYY-MM-DD), defaults to today"),
    current_user: User = Depends(get_current_user),
):
    """
    Get daily performance report.

    Args:
        report_date: Date for the report (defaults to today)
        current_user: Authenticated user

    Returns:
        Daily performance report with P&L, win rate, and metrics
    """
    if report_date is None:
        report_date = date.today()

    try:
        # Initialize reporter
        reporter = DailyPerformanceReport(
            target_daily_income=1780.0,
            initial_capital=800000.0,
            max_daily_drawdown_pct=0.02
        )

        # Load trades from StateStore
        state_store = StateStore()
        try:
            trades = state_store.get_trades_for_date(report_date)

            import pandas as pd
            if trades:
                trades_df = pd.DataFrame(trades)
            else:
                trades_df = pd.DataFrame()

            # Generate report
            report_datetime = datetime.combine(report_date, datetime.min.time())
            report = reporter.generate_report(trades_df, report_datetime)

            return {
                "report": report,
                "generated_at": datetime.now().isoformat()
            }

        finally:
            state_store.close()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/daily-reports/recent")
async def get_recent_daily_reports(
    days: int = Query(7, ge=1, le=30, description="Number of days to retrieve"),
    current_user: User = Depends(get_current_user),
):
    """
    Get recent daily reports.

    Args:
        days: Number of recent days to retrieve (1-30)
        current_user: Authenticated user

    Returns:
        List of daily reports
    """
    try:
        import pandas as pd
        from datetime import timedelta

        reports = []
        reporter = DailyPerformanceReport(
            target_daily_income=1780.0,
            initial_capital=800000.0,
            max_daily_drawdown_pct=0.02
        )

        state_store = StateStore()
        try:
            # Generate reports for last N days
            for i in range(days):
                target_date = date.today() - timedelta(days=i)

                # Load trades for the date
                trades = state_store.get_trades_for_date(target_date)

                if trades:
                    trades_df = pd.DataFrame(trades)
                else:
                    trades_df = pd.DataFrame()

                # Generate report
                report_datetime = datetime.combine(target_date, datetime.min.time())
                report = reporter.generate_report(trades_df, report_datetime)

                reports.append(report)

        finally:
            state_store.close()

        return {
            "reports": reports,
            "count": len(reports),
            "days": days
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch reports: {str(e)}")
