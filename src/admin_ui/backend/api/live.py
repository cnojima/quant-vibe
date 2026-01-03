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
from quant_vibe.utils import now_utc

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
    status: str = Query("open", pattern="^(open|closed|all)$"),
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
    status: str = Query("all", pattern="^(open|filled|rejected|cancelled|all)$"),
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
    severity: Optional[str] = Query(None, pattern="^(info|warning|error)$"),
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
            from decimal import Decimal

            if trades:
                # Convert Decimal to float for numeric fields
                for trade in trades:
                    for key in ['entry_cost', 'exit_value', 'pnl']:
                        if key in trade and isinstance(trade[key], Decimal):
                            trade[key] = float(trade[key])

                trades_df = pd.DataFrame(trades)
            else:
                trades_df = pd.DataFrame()

            # Generate report
            report_datetime = datetime.combine(report_date, datetime.min.time())
            report = reporter.generate_report(trades_df, report_datetime)

            return {
                "report": report,
                "generated_at": now_utc().isoformat()
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
            from decimal import Decimal

            # Generate reports for last N days
            for i in range(days):
                target_date = date.today() - timedelta(days=i)

                # Load trades for the date
                trades = state_store.get_trades_for_date(target_date)

                if trades:
                    # Convert Decimal to float for numeric fields
                    for trade in trades:
                        for key in ['entry_cost', 'exit_value', 'pnl']:
                            if key in trade and isinstance(trade[key], Decimal):
                                trade[key] = float(trade[key])

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


@router.get("/strategies/active")
async def get_active_strategies(current_user: User = Depends(get_current_user)):
    """
    Get list of active trading strategies from live trading config.

    Args:
        current_user: Authenticated user

    Returns:
        List of active strategies with their parameters
    """
    try:
        import yaml
        from pathlib import Path

        # Load live trading config
        config_path = Path(__file__).parent.parent.parent.parent.parent / "config" / "live_trading.yaml"

        if not config_path.exists():
            raise HTTPException(status_code=404, detail="Live trading config not found")

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        strategies = config.get("strategies", {}).get("enabled", [])
        active_strategies = [s for s in strategies if s.get("enabled", False)]

        # Get stats per strategy
        stats_by_strategy = {}
        try:
            state_store = StateStore()
            try:
                # Get all closed positions to calculate stats per strategy
                closed_positions = await timescale.fetch_closed_positions(limit=1000)

                # Group by strategy
                from collections import defaultdict
                strategy_stats = defaultdict(lambda: {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "total_pnl": 0.0,
                })

                for pos in closed_positions:
                    strategy = pos.get("strategy", "unknown")
                    pnl = pos.get("realized_pnl", 0) or 0

                    strategy_stats[strategy]["total_trades"] += 1
                    strategy_stats[strategy]["total_pnl"] += pnl

                    if pnl > 0:
                        strategy_stats[strategy]["winning_trades"] += 1
                    elif pnl < 0:
                        strategy_stats[strategy]["losing_trades"] += 1

                # Calculate win rate for each
                for strat, stats in strategy_stats.items():
                    if stats["total_trades"] > 0:
                        stats["win_rate"] = stats["winning_trades"] / stats["total_trades"]
                    else:
                        stats["win_rate"] = 0.0

                stats_by_strategy = dict(strategy_stats)

            finally:
                state_store.close()
        except Exception as e:
            # If stats fetch fails, just continue without stats
            pass

        # Enrich strategies with stats
        enriched_strategies = []
        for strat in active_strategies:
            strat_name = strat.get("name", "unknown")
            strat_data = {
                "name": strat_name,
                "enabled": strat.get("enabled", False),
                "params": strat.get("params", {}),
                "stats": stats_by_strategy.get(strat_name, {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "total_pnl": 0.0,
                    "win_rate": 0.0,
                })
            }
            enriched_strategies.append(strat_data)

        return {
            "strategies": enriched_strategies,
            "count": len(enriched_strategies),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch active strategies: {str(e)}")


@router.post("/strategies/reload")
async def reload_strategies(current_user: User = Depends(get_current_user)):
    """
    Reload strategies from configuration without restarting the engine.

    This publishes a reload command to Redis, which the live trading engine
    will pick up and process. Active positions are preserved.

    Args:
        current_user: Authenticated user

    Returns:
        Success message
    """
    try:
        from quant_vibe.messaging import RedisMessageBroker

        # Publish reload command to Redis
        broker = RedisMessageBroker()
        broker.publish(
            topic="control.live_trading",
            data={
                "command": "reload_strategies",
                "timestamp": now_utc().isoformat(),
                "user": current_user.username,
            }
        )
        broker.close()

        return {
            "success": True,
            "message": "Strategy reload command sent to live trading engine",
            "note": "Check live trading logs for reload confirmation",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send reload command: {str(e)}")


@router.get("/trades/visualization")
async def get_trades_visualization(
    days: int = Query(7, ge=1, le=90, description="Number of days to retrieve"),
    current_user: User = Depends(get_current_user),
):
    """
    Get trades data for visualization with equity curve and underlying price.

    Args:
        days: Number of days to retrieve (1-90)
        current_user: Authenticated user

    Returns:
        Trades, equity curve, and underlying price data for charting
    """
    try:
        import pandas as pd
        from datetime import timedelta, timezone
        from decimal import Decimal
        from quant_vibe.data.timescale_store import TimescaleStore

        # Calculate date range (timezone-aware UTC)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Load trades from state store
        state_store = StateStore()
        ts_store = TimescaleStore()

        try:
            # Get all closed positions in date range
            closed_positions = await timescale.fetch_closed_positions(limit=10000)

            # Filter by date range and convert to trades format
            trades = []
            for pos in closed_positions:
                exit_time = pos.get('exit_time')
                if exit_time:
                    exit_dt = exit_time if isinstance(exit_time, datetime) else datetime.fromisoformat(str(exit_time))
                    # Ensure timezone-aware comparison
                    if exit_dt.tzinfo is None:
                        exit_dt = exit_dt.replace(tzinfo=timezone.utc)
                    if start_date <= exit_dt <= end_date:
                        # Parse legs JSON if needed
                        legs = pos.get('legs', [])
                        if isinstance(legs, str):
                            import json
                            legs = json.loads(legs)

                        trades.append({
                            'position_id': pos.get('position_id'),
                            'strategy': pos.get('strategy', pos.get('strategy_name', 'unknown')),
                            'entry_time': pos.get('entry_time'),
                            'exit_time': exit_time,
                            'entry_cost': float(pos.get('entry_cost', 0)) if pos.get('entry_cost') else 0,
                            'exit_value': float(pos.get('exit_value', 0)) if pos.get('exit_value') else 0,
                            'pnl': float(pos.get('realized_pnl', 0)) if pos.get('realized_pnl') else 0,
                            'exit_reason': pos.get('exit_reason'),
                            'spread_type': pos.get('spread_type'),
                            'legs': legs,
                            'metadata': pos.get('metadata', {})
                        })

            # Sort trades by entry time
            trades.sort(key=lambda t: t['entry_time'] if t['entry_time'] else datetime.min.replace(tzinfo=timezone.utc))

            # Build equity curve from trades
            initial_capital = 800000.0  # TODO: Get from config
            equity_curve = []
            current_equity = initial_capital

            # Add starting point
            if len(trades) > 0:
                equity_curve.append({
                    'timestamp': start_date.isoformat(),
                    'value': current_equity
                })

            # Add points at each trade exit
            for trade in trades:
                if trade['exit_time']:
                    current_equity += trade['pnl']
                    equity_curve.append({
                        'timestamp': trade['exit_time'].isoformat() if isinstance(trade['exit_time'], datetime) else str(trade['exit_time']),
                        'value': current_equity
                    })

            # Add ending point
            if len(trades) > 0:
                equity_curve.append({
                    'timestamp': end_date.isoformat(),
                    'value': current_equity
                })

            # Fetch underlying price data (SPX)
            underlying_data = []
            try:
                # Get SPX price from options_bars (derived from ATM options)
                underlying_df = ts_store.get_underlying_price_from_options(
                    underlying_ticker='SPX',
                    start_time=start_date,
                    end_time=end_date
                )

                if underlying_df is not None and not underlying_df.empty:
                    # Resample to 5-minute bars for performance
                    underlying_df = underlying_df.resample('5min').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum'
                    }).dropna()

                    underlying_data = [
                        {
                            'timestamp': idx.isoformat(),
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': int(row['volume']) if not pd.isna(row['volume']) else 0
                        }
                        for idx, row in underlying_df.iterrows()
                    ]
            except Exception as e:
                print(f"Warning: Failed to fetch underlying data: {e}")
                # Continue without underlying data

            return {
                'trades': trades,
                'equity_curve': equity_curve,
                'underlying_data': underlying_data,
                'initial_capital': initial_capital,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total_trades': len(trades)
            }

        finally:
            state_store.close()
            ts_store.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch trades visualization data: {str(e)}")
