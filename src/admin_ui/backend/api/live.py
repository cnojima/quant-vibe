"""
Live trading monitoring API endpoints.

Provides endpoints to view live trading status, positions, orders, and events.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Query, HTTPException, Body
from pydantic import BaseModel

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.db import timescale

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from quant_vibe.reporting import DailyPerformanceReport
from live_trading_service.state_store import StateStore
from quant_vibe.utils import now_utc

router = APIRouter()


# Pydantic models for account endpoints
class AccountInfo(BaseModel):
    account_hash: str
    account_number: str  # Masked format
    nickname: str
    account_type: str
    is_day_trader: bool
    is_default: bool
    round_trips: int
    created_at: datetime
    updated_at: datetime


class AccountBalance(BaseModel):
    account_hash: str
    timestamp: datetime
    cash_balance: float
    available_funds: float
    buying_power: float
    day_trading_buying_power: float
    liquidation_value: float
    long_option_market_value: float
    short_option_market_value: float
    maintenance_requirement: float
    margin_balance: float
    portfolio_value: float
    total_pnl: float
    daily_pnl: float
    win_rate: Optional[float]
    sharpe_ratio: Optional[float]


@router.get("/status")
async def get_live_status(
    trading_mode: str = Query('paper', pattern='^(real|paper|replay)$'),
    current_user: User = Depends(get_current_user)
):
    """
    Get current live trading engine status.

    Args:
        trading_mode: Trading mode to query ('real', 'paper', or 'replay')
        current_user: Authenticated user

    Returns:
        Live trading engine status
    """
    engine_state = await timescale.fetch_engine_state(trading_mode=trading_mode)

    if not engine_state:
        return {
            "running": False,
            "message": "No engine state found. Engine may not have started yet.",
            "trading_mode": trading_mode,
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
        "data_feed_mode": engine_state.get("data_feed_mode", "live"),
        "trading_mode": trading_mode,
    }


@router.get("/accounts")
async def get_accounts(
    trading_mode: str = Query('paper', pattern='^(real|paper)$'),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get all configured broker accounts.

    Args:
        trading_mode: Trading mode ('real' or 'paper')
        current_user: Authenticated user

    Returns:
        List of broker accounts with metadata
    """
    accounts = await timescale.fetch_broker_accounts(trading_mode=trading_mode)

    # For paper trading, create a default account if none exist
    if trading_mode == 'paper' and len(accounts) == 0:
        import hashlib
        from datetime import datetime

        # Create a default paper trading account
        default_account = {
            'account_hash': hashlib.sha256(b'PAPER_DEFAULT').hexdigest()[:32],
            'account_number': 'PAPER001',
            'nickname': 'Paper Trading Account',
            'account_type': 'MARGIN',
            'is_day_trader': True,  # Paper trading has no PDT restrictions
            'is_closing_only_restricted': False,
            'is_default': True,
            'round_trips': 0
        }

        await timescale.upsert_broker_account(default_account, trading_mode='paper')

        # Also create initial balance for the paper account
        initial_balance = {
            'account_hash': default_account['account_hash'],
            'cash_balance': 100000.0,  # Start with $100k
            'available_funds': 100000.0,
            'buying_power': 400000.0,  # 4x margin for day trading
            'day_trading_buying_power': 400000.0,
            'liquidation_value': 100000.0,
            'portfolio_value': 100000.0,
            'long_option_market_value': 0.0,
            'short_option_market_value': 0.0,
            'maintenance_requirement': 0.0,
            'margin_balance': 0.0,
            'daily_pnl': 0.0,
            'total_pnl': 0.0,
            'win_rate': None,
            'sharpe_ratio': None
        }

        await timescale.store_account_balance(initial_balance, trading_mode='paper')

        # Re-fetch accounts
        accounts = await timescale.fetch_broker_accounts(trading_mode=trading_mode)

    return {
        "accounts": accounts,
        "count": len(accounts),
        "trading_mode": trading_mode
    }


@router.get("/accounts/{account_hash}/balance")
async def get_account_balance(
    account_hash: str,
    trading_mode: str = Query('paper', pattern='^(real|paper)$'),
    realtime: bool = Query(False, description="Fetch real-time balance from Schwab API"),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get account balance and portfolio value.

    Args:
        account_hash: Account hash identifier
        trading_mode: Trading mode ('real' or 'paper')
        realtime: If True, fetch real-time data from Schwab API
        current_user: Authenticated user

    Returns:
        Account balance information
    """
    if realtime and trading_mode == 'real':
        # Fetch real-time balance from Schwab API
        try:
            from quant_vibe.data.schwab_dev_client import SchwabDevClient

            # Initialize Schwab client using the wrapper
            try:
                schwab_dev = SchwabDevClient()
                schwab_client = schwab_dev.client
            except Exception as e:
                print(f"Failed to initialize Schwab client: {e}")
                schwab_client = None

            if schwab_client:
                # Get account details from Schwab
                response = schwab_client.account_details(
                    account_hash,
                    fields=None  # Get all fields including balances
                )
                response.raise_for_status()
                account_details = response.json()

                if account_details and 'securitiesAccount' in account_details:
                    balances = account_details['securitiesAccount'].get('currentBalances', {})

                    # Store the real-time balance in database
                    balance_data = {
                        'account_hash': account_hash,
                        'cash_balance': balances.get('cashBalance', 0),
                        'available_funds': balances.get('availableFunds', 0),
                        'buying_power': balances.get('buyingPower', 0),
                        'day_trading_buying_power': balances.get('dayTradingBuyingPower', 0),
                        'liquidation_value': balances.get('liquidationValue', 0),
                        'long_option_market_value': balances.get('longOptionMarketValue', 0),
                        'short_option_market_value': balances.get('shortOptionMarketValue', 0),
                        'maintenance_requirement': balances.get('maintenanceRequirement', 0),
                        'margin_balance': balances.get('marginBalance', 0),
                        'portfolio_value': balances.get('liquidationValue', 0),  # Same as liquidation value
                    }

                    # Store in database
                    await timescale.store_account_balance(balance_data, trading_mode=trading_mode)

                    return {
                        "balance": balance_data,
                        "source": "schwab_api",
                        "timestamp": now_utc().isoformat(),
                        "trading_mode": trading_mode
                    }

        except Exception as e:
            # Fall back to database if API fails
            print(f"Failed to fetch real-time balance: {e}")

    # Get latest balance from database
    balance = await timescale.fetch_account_balance(
        account_hash=account_hash,
        trading_mode=trading_mode
    )

    if not balance:
        raise HTTPException(status_code=404, detail=f"No balance found for account {account_hash}")

    return {
        "balance": balance,
        "source": "database",
        "trading_mode": trading_mode
    }


@router.post("/accounts/{account_hash}/set-default")
async def set_default_account(
    account_hash: str,
    trading_mode: str = Query('paper', pattern='^(real|paper)$'),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Set an account as the default for the trading mode.

    Args:
        account_hash: Account hash to set as default
        trading_mode: Trading mode ('real' or 'paper')
        current_user: Authenticated user

    Returns:
        Success message
    """
    success = await timescale.set_default_account(
        account_hash=account_hash,
        trading_mode=trading_mode
    )

    if not success:
        raise HTTPException(status_code=404, detail=f"Account {account_hash} not found")

    return {
        "success": True,
        "message": f"Account {account_hash} set as default for {trading_mode} trading",
        "trading_mode": trading_mode
    }


@router.post("/accounts/{account_hash}/sync-orders")
async def sync_account_orders(
    account_hash: str,
    days_back: int = Query(30, ge=1, le=90, description="Number of days to sync"),
    trading_mode: str = Query('paper', pattern='^(real|paper)$'),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Synchronize orders from Schwab API for the specified account.

    Args:
        account_hash: Account hash to sync orders for
        days_back: Number of days to look back for orders
        trading_mode: Trading mode ('real' or 'paper')
        current_user: Authenticated user

    Returns:
        Synchronization results
    """
    if trading_mode != 'real':
        raise HTTPException(status_code=400, detail="Order sync only available for real trading mode")

    try:
        from quant_vibe.data.schwab_dev_client import SchwabDevClient
        from datetime import timedelta

        # Initialize Schwab client using the wrapper
        try:
            schwab_dev = SchwabDevClient()
            schwab_client = schwab_dev.client
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to initialize Schwab client: {str(e)}")

        # Calculate date range
        end_time = now_utc()
        start_time = end_time - timedelta(days=days_back)

        # Fetch orders from Schwab API
        response = schwab_client.account_orders_all(
            fromEnteredTime=start_time,
            toEnteredTime=end_time
        )
        response.raise_for_status()
        orders = response.json()

        # Process and store orders
        processed_count = 0
        for order in orders:
            # Store order in database with account_hash
            order_data = {
                'account_hash': account_hash,
                'order_id': order.get('orderId'),
                'status': order.get('status'),
                'order_type': order.get('orderType'),
                'entered_time': order.get('enteredTime'),
                'filled_quantity': order.get('filledQuantity', 0),
                'price': order.get('price', 0),
                # Add more fields as needed
            }

            await timescale.store_order(order_data, trading_mode=trading_mode)
            processed_count += 1

        return {
            "success": True,
            "orders_synced": processed_count,
            "date_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "trading_mode": trading_mode
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync orders: {str(e)}")


@router.post("/accounts/refresh")
async def refresh_accounts(
    trading_mode: str = Query('paper', pattern='^(real|paper)$'),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Refresh account information from Schwab API.

    Args:
        trading_mode: Trading mode ('real' or 'paper')
        current_user: Authenticated user

    Returns:
        List of refreshed accounts
    """
    if trading_mode != 'real':
        # For paper trading, just return existing accounts
        accounts = await timescale.fetch_broker_accounts(trading_mode='paper')
        return {
            "accounts": accounts,
            "count": len(accounts),
            "source": "database",
            "trading_mode": trading_mode
        }

    try:
        from live_trading_service.order_manager import OrderManager
        from quant_vibe.data.schwab_dev_client import SchwabDevClient

        # Initialize Schwab client using the wrapper
        try:
            schwab_dev = SchwabDevClient()
            schwab_client = schwab_dev.client
        except Exception as e:
            return {
                "accounts": [],
                "count": 0,
                "source": "error",
                "message": f"Failed to initialize Schwab client: {str(e)}",
                "trading_mode": trading_mode
            }

        # Initialize OrderManager with Schwab client
        order_manager = OrderManager(
            paper_trading=False,
            schwab_client=schwab_client
        )

        # Get linked accounts using the Schwab client directly
        response = schwab_client.linked_accounts()
        response.raise_for_status()
        linked_accounts = response.json()

        accounts_processed = []
        for acc in linked_accounts:
            account_data = {
                'account_hash': acc['hashValue'],
                'account_number': acc['accountNumber'][-4:] if 'accountNumber' in acc else 'XXXX',
                'nickname': acc.get('nickname', f"Account {acc['accountNumber'][-4:]}"),
                'account_type': acc.get('accountType', 'UNKNOWN'),
                'is_day_trader': False,  # Will be updated from account details
                'is_closing_only_restricted': False,
                'round_trips': 0
            }

            # Get detailed account info
            try:
                details_response = schwab_client.account_details(acc['hashValue'])
                details_response.raise_for_status()
                details = details_response.json()

                if details and 'securitiesAccount' in details:
                    sec_acc = details['securitiesAccount']
                    account_data.update({
                        'account_type': sec_acc.get('type', 'UNKNOWN'),
                        'is_day_trader': sec_acc.get('isDayTrader', False),
                        'is_closing_only_restricted': sec_acc.get('isClosingOnlyRestricted', False),
                        'round_trips': sec_acc.get('roundTrips', 0)
                    })
            except Exception as e:
                print(f"Failed to get details for account {acc['hashValue']}: {e}")

            # Store/update in database
            await timescale.upsert_broker_account(account_data, trading_mode='real')
            accounts_processed.append(account_data)

        return {
            "accounts": accounts_processed,
            "count": len(accounts_processed),
            "source": "schwab_api",
            "trading_mode": trading_mode
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh accounts: {str(e)}")


@router.get("/positions")
async def get_positions(
    trading_mode: str = Query('paper', pattern='^(real|paper|replay)$'),
    status: str = Query("open", pattern="^(open|closed|all)$"),
    limit: int = Query(100, ge=1, le=1000),
    account_hash: Optional[str] = Query(None, description="Filter by account hash"),
    current_user: User = Depends(get_current_user),
):
    """
    Get positions.

    Args:
        trading_mode: Trading mode to query ('real', 'paper', or 'replay')
        status: Filter by status (open, closed, all)
        limit: Maximum number of positions to return
        account_hash: Optional account hash to filter by
        current_user: Authenticated user

    Returns:
        List of positions
    """
    if status == "open":
        positions = await timescale.fetch_active_positions(
            limit=limit,
            trading_mode=trading_mode,
            account_hash=account_hash
        )
    elif status == "closed":
        positions = await timescale.fetch_closed_positions(
            limit=limit,
            trading_mode=trading_mode,
            account_hash=account_hash
        )
    else:  # all
        active = await timescale.fetch_active_positions(
            limit=limit // 2,
            trading_mode=trading_mode,
            account_hash=account_hash
        )
        closed = await timescale.fetch_closed_positions(
            limit=limit // 2,
            trading_mode=trading_mode,
            account_hash=account_hash
        )
        positions = active + closed

    return {
        "positions": positions,
        "count": len(positions),
        "filter": status,
        "trading_mode": trading_mode,
        "account_hash": account_hash,
    }


@router.get("/orders")
async def get_orders(
    trading_mode: str = Query('paper', pattern='^(real|paper|replay)$'),
    limit: int = Query(100, ge=1, le=1000),
    status: str = Query("all", pattern="^(open|filled|rejected|cancelled|all)$"),
    account_hash: Optional[str] = Query(None, description="Filter by account hash"),
    current_user: User = Depends(get_current_user),
):
    """
    Get orders with optional status filter.

    Args:
        trading_mode: Trading mode to query ('real', 'paper', or 'replay')
        limit: Maximum number of orders to return
        status: Filter by status (open, filled, rejected, cancelled, all)
        account_hash: Optional account hash to filter by
        current_user: Authenticated user

    Returns:
        List of orders
    """
    orders = await timescale.fetch_open_orders(
        limit=limit,
        status_filter=status,
        trading_mode=trading_mode,
        account_hash=account_hash
    )

    return {
        "orders": orders,
        "count": len(orders),
        "filter": status,
        "trading_mode": trading_mode,
        "account_hash": account_hash,
    }


@router.get("/events")
async def get_events(
    trading_mode: str = Query('paper', pattern='^(real|paper|replay)$'),
    limit: int = Query(100, ge=1, le=1000),
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, pattern="^(info|warning|error)$"),
    current_user: User = Depends(get_current_user),
):
    """
    Get recent events.

    Args:
        trading_mode: Trading mode to query ('real', 'paper', or 'replay')
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
        trading_mode=trading_mode,
    )

    return {
        "events": events,
        "count": len(events),
        "trading_mode": trading_mode,
        "filters": {
            "event_type": event_type,
            "severity": severity,
        },
    }


@router.delete("/events")
async def clear_events(current_user: User = Depends(get_current_user)):
    """
    Clear all events from the live_events table.

    Args:
        current_user: Authenticated user

    Returns:
        Success message with count of deleted events
    """
    deleted_count = await timescale.clear_live_events()

    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"Successfully cleared {deleted_count} events",
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
    account_hash: Optional[str] = Query(None, description="Account hash to filter trades for a specific account"),
    trading_mode: str = Query('paper', pattern='^(real|paper)$'),
    current_user: User = Depends(get_current_user),
):
    """
    Get daily performance report.

    Args:
        report_date: Date for the report (defaults to today)
        account_hash: Optional account hash to filter trades for a specific account
        trading_mode: Trading mode to query ('real' or 'paper')
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

        # Load trades from StateStore with proper trading mode
        state_store = StateStore(trading_mode=trading_mode)
        try:
            trades = state_store.get_trades_for_date(report_date, account_hash=account_hash)

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
    account_hash: Optional[str] = Query(None, description="Account hash to filter trades for a specific account"),
    trading_mode: str = Query('paper', pattern='^(real|paper)$'),
    current_user: User = Depends(get_current_user),
):
    """
    Get recent daily reports.

    Args:
        days: Number of recent days to retrieve (1-30)
        account_hash: Optional account hash to filter trades for a specific account
        trading_mode: Trading mode to query ('real' or 'paper')
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

        state_store = StateStore(trading_mode=trading_mode)
        try:
            from decimal import Decimal

            # Generate reports for last N days
            for i in range(days):
                target_date = date.today() - timedelta(days=i)

                # Load trades for the date
                trades = state_store.get_trades_for_date(target_date, account_hash=account_hash)

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
async def get_active_strategies(
    trading_mode: str = Query('paper', pattern='^(real|paper|replay)$'),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of active trading strategies from live trading config.

    Args:
        trading_mode: Trading mode to query ('real', 'paper', or 'replay')
        current_user: Authenticated user

    Returns:
        List of active strategies with their parameters
    """
    try:
        import yaml
        from pathlib import Path

        # Load live trading config based on trading mode
        config_filename = f"live_trading_{trading_mode}.yaml"
        config_path = Path(__file__).parent.parent.parent.parent.parent / "config" / config_filename

        if not config_path.exists():
            raise HTTPException(status_code=404, detail=f"Live trading config not found: {config_filename}")

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
                closed_positions = await timescale.fetch_closed_positions(limit=1000, trading_mode=trading_mode)

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
        except Exception:
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


@router.post("/data-feed/toggle-mode")
async def toggle_data_feed_mode(
    trading_mode: str = Query('paper', pattern='^(real|paper)$'),
    current_user: User = Depends(get_current_user)
):
    """
    Toggle data feed mode between 'live' and 'replay'.

    This updates the live_trading_{mode}.yaml config and requires the engine to be restarted
    or the data feed to be reconnected for the change to take effect.

    Args:
        trading_mode: Trading mode ('real' or 'paper')
        current_user: Authenticated user

    Returns:
        Success message with new mode
    """
    try:
        import yaml
        from pathlib import Path

        # Load live trading config based on trading mode
        config_filename = f"live_trading_{trading_mode}.yaml"
        config_path = Path(__file__).parent.parent.parent.parent.parent / "config" / config_filename

        if not config_path.exists():
            raise HTTPException(status_code=404, detail=f"Live trading config not found: {config_filename}")

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Get current mode
        current_mode = config.get("data_feed", {}).get("mode", "live")

        # Toggle mode
        new_mode = "replay" if current_mode == "live" else "live"

        # Update config
        if "data_feed" not in config:
            config["data_feed"] = {}
        config["data_feed"]["mode"] = new_mode

        # Save config
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return {
            "success": True,
            "message": f"Config updated: Data feed mode changed from '{current_mode}' to '{new_mode}' in {config_filename}",
            "previous_mode": current_mode,
            "new_mode": new_mode,
            "note": f"⚠️ RESTART REQUIRED: The {trading_mode} trading engine must be restarted for this change to take effect. Current running engine is still using '{current_mode}' mode.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle data feed mode: {str(e)}")


@router.post("/reconcile")
async def trigger_reconciliation(
    trading_mode: str = Query('real', pattern='^(real|paper)$'),
    account_hash: Optional[str] = Query(None, description="Specific account hash to reconcile"),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger manual position reconciliation with broker.

    This endpoint sends a control message to the live trading engine
    to perform reconciliation. The engine must be running to respond.

    Args:
        trading_mode: Trading mode to reconcile ('real' or 'paper')
        account_hash: Optional specific account hash to reconcile (uses engine config if not provided)
        current_user: Authenticated user

    Returns:
        Status message indicating reconciliation was triggered
    """
    if trading_mode == 'paper':
        return {
            "success": True,
            "message": "Paper trading mode - no broker reconciliation needed",
            "status": "paper_trading"
        }

    try:
        # Send control message to engine via Redis
        from quant_vibe.messaging import RedisMessageBroker
        from quant_vibe.messaging.topics import Topic

        broker = RedisMessageBroker()

        # Publish reconciliation command to control topic
        message = {
            "command": "reconcile",
            "trading_mode": trading_mode,
            "account_hash": account_hash,  # Pass specific account if provided
            "requested_by": "admin_ui",
            "timestamp": datetime.utcnow().isoformat()
        }

        # Publish to control.live_trading topic
        success = broker.publish(Topic.CONTROL_LIVE_TRADING, message)

        if success:
            return {
                "success": True,
                "message": f"Reconciliation request sent to {trading_mode} trading engine. Check engine logs for results.",
                "status": "requested"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to publish message to Redis"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send reconciliation request: {str(e)}"
        )


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
