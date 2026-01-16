"""
TimescaleDB database connection and query utilities.

Provides async connection pool and query methods for:
- Live trading engine state
- Positions and orders
- Events and logs
"""

import json
from datetime import datetime
from typing import Any, Optional

import asyncpg

from admin_ui.backend.config import get_settings

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def init_db_pool() -> None:
    """Initialize the database connection pool."""
    global _pool

    if _pool is not None:
        return

    settings = get_settings()

    _pool = await asyncpg.create_pool(
        host=settings.timescale_host,
        port=settings.timescale_port,
        database=settings.timescale_db,
        user=settings.timescale_user,
        password=settings.timescale_password,
        min_size=2,
        max_size=10,
        command_timeout=60,
    )


async def close_db_pool() -> None:
    """Close the database connection pool."""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Get the database connection pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db_pool() first.")
    return _pool


def _get_table_name(base_table: str, trading_mode: str = 'paper') -> str:
    """
    Get the full table name including schema for a trading mode.

    Args:
        base_table: Base table name (e.g., 'positions', 'orders', 'engine_state')
        trading_mode: Trading mode ('real', 'paper', or 'replay')

    Returns:
        Full table name with schema (e.g., 'real_trading.positions')
    """
    schema_map = {
        'real': 'real_trading',
        'paper': 'paper_trading',
        'replay': 'replay_trading',
    }
    schema = schema_map.get(trading_mode, 'public')

    # Map base table names to actual table names
    # In new schemas, tables don't have 'live_' prefix
    if schema == 'public':
        # Old schema uses live_ prefix
        return f'live_{base_table}'
    else:
        # New schemas use clean names
        return f'{schema}.{base_table}'


async def fetch_engine_state(trading_mode: str = 'paper') -> Optional[dict[str, Any]]:
    """
    Fetch the latest live trading engine state.

    Args:
        trading_mode: Trading mode schema ('real', 'paper', or 'replay')

    Returns:
        Dict with engine state or None if no state found
    """
    pool = get_pool()
    table_name = _get_table_name('engine_state', trading_mode)

    query = f"""
        SELECT
            timestamp,
            state,
            metadata,
            (metadata->>'paper_trading')::boolean as paper_trading,
            (metadata->>'total_bars_processed')::integer as total_bars_processed,
            (metadata->>'total_signals_generated')::integer as total_signals_generated,
            (metadata->>'uptime_seconds')::numeric as uptime_seconds
        FROM {table_name}
        ORDER BY timestamp DESC
        LIMIT 1
    """
    # return {
    #     "running": engine_state.get("state", "").lower() == "running",
    #     "state": engine_state.get("state"),
    #     "paper_trading": engine_state.get("paper_trading"),
    #     "total_bars_processed": engine_state.get("total_bars_processed"),
    #     "total_signals_generated": engine_state.get("total_signals_generated"),
    #     "uptime_seconds": engine_state.get("uptime_seconds"),
    #     "last_update": engine_state.get("timestamp"),
    #     "metadata": engine_state.get("metadata"),
    #     "data_feed_mode": engine_state.get("data_feed_mode", "live"),
    # }

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query)
        if row:
            result = dict(row)
            # Handle None values gracefully
            result['paper_trading'] = result.get('paper_trading', True)
            result['total_bars_processed'] = result.get('total_bars_processed', 0)
            result['total_signals_generated'] = result.get('total_signals_generated', 0)
            result['uptime_seconds'] = result.get('uptime_seconds', 0.0)
            result['last_update'] = result.get('timestamp')

            if result['metadata'] and isinstance(result['metadata'], str):
                result['metadata'] = json.loads(result['metadata'])
            result['data_feed_mode'] = result['metadata'].get('data_feed_mode', 'live') if isinstance(result['metadata'], dict) else 'live'
            return result
        return None


async def fetch_active_positions(
    limit: int = 100,
    trading_mode: str = 'paper',
    account_hash: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Fetch active (open) positions.

    Args:
        limit: Maximum number of positions to return
        trading_mode: Trading mode schema ('real', 'paper', or 'replay')
        account_hash: Optional account hash to filter by

    Returns:
        List of position dictionaries
    """
    pool = get_pool()
    table_name = _get_table_name('positions', trading_mode)

    # Build WHERE clause
    where_clauses = ["status = 'open'"]
    params = []
    param_idx = 1

    if account_hash:
        where_clauses.append(f"account_hash = ${param_idx}")
        params.append(account_hash)
        param_idx += 1

    where_sql = " AND ".join(where_clauses)
    params.append(limit)

    query = f"""
        SELECT
            position_id,
            strategy_name,
            spread_type,
            entry_time,
            entry_cost,
            current_value,
            (COALESCE(current_value, 0) - entry_cost) as unrealized_pnl,
            legs,
            metadata,
            account_hash
        FROM {table_name}
        WHERE {where_sql}
        ORDER BY entry_time DESC
        LIMIT ${param_idx}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        result = []
        for row in rows:
            pos = dict(row)
            # Parse JSONB fields if they're strings
            if isinstance(pos.get('legs'), str):
                pos['legs'] = json.loads(pos['legs'])
            if isinstance(pos.get('metadata'), str):
                pos['metadata'] = json.loads(pos['metadata'])
            result.append(pos)
        return result


async def fetch_closed_positions(
    limit: int = 100,
    trading_mode: str = 'paper',
    account_hash: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Fetch closed positions.

    Args:
        limit: Maximum number of positions to return
        trading_mode: Trading mode schema ('real', 'paper', or 'replay')
        account_hash: Optional account hash to filter by

    Returns:
        List of position dictionaries
    """
    pool = get_pool()
    table_name = _get_table_name('positions', trading_mode)

    # Build WHERE clause
    where_clauses = ["status = 'closed'"]
    params = []
    param_idx = 1

    if account_hash:
        where_clauses.append(f"account_hash = ${param_idx}")
        params.append(account_hash)
        param_idx += 1

    where_sql = " AND ".join(where_clauses)
    params.append(limit)

    query = f"""
        SELECT
            position_id,
            strategy_name,
            spread_type,
            entry_time,
            entry_cost,
            exit_time,
            exit_value,
            (COALESCE(exit_value, 0) - entry_cost) as realized_pnl,
            exit_reason,
            legs,
            metadata,
            account_hash
        FROM {table_name}
        WHERE {where_sql}
        ORDER BY exit_time DESC
        LIMIT ${param_idx}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        result = []
        for row in rows:
            pos = dict(row)
            # Parse JSONB fields if they're strings
            if isinstance(pos.get('legs'), str):
                pos['legs'] = json.loads(pos['legs'])
            if isinstance(pos.get('metadata'), str):
                pos['metadata'] = json.loads(pos['metadata'])
            result.append(pos)
        return result


async def fetch_open_orders(
    limit: int = 100,
    status_filter: Optional[str] = None,
    trading_mode: str = 'paper',
    account_hash: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    Fetch orders with optional status filter.

    Args:
        limit: Maximum number of orders to return
        status_filter: Filter by status ('open', 'filled', 'rejected', 'all')
                      'open' = pending/submitted/accepted
                      None = same as 'open' (default for backwards compatibility)
        trading_mode: Trading mode schema ('real', 'paper', or 'replay')
        account_hash: Optional account hash to filter by

    Returns:
        List of order dictionaries
    """
    pool = get_pool()
    table_name = _get_table_name('orders', trading_mode)

    # Build WHERE clause based on filters
    where_clauses = []
    params = []
    param_idx = 1

    # Status filter
    if status_filter == 'all':
        # Show all orders
        pass
    elif status_filter == 'open' or status_filter is None:
        # Default: show open orders
        where_clauses.append("status IN ('pending', 'submitted', 'accepted')")
    elif status_filter in ('filled', 'rejected', 'cancelled'):
        where_clauses.append(f"status = '{status_filter}'")
    else:
        # Invalid filter, default to open
        where_clauses.append("status IN ('pending', 'submitted', 'accepted')")

    # Account filter
    if account_hash:
        where_clauses.append(f"account_hash = ${param_idx}")
        params.append(account_hash)
        param_idx += 1

    # Build final WHERE clause
    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    params.append(limit)

    query = f"""
        SELECT
            order_id,
            position_id,
            strategy_name,
            order_type,
            action_type,
            status,
            submitted_time,
            symbol,
            quantity,
            expected_price as limit_price,
            filled_price,
            metadata,
            account_hash
        FROM {table_name}
        {where_clause}
        ORDER BY submitted_time DESC
        LIMIT ${param_idx}
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        result = []
        for row in rows:
            order = dict(row)
            # Parse JSONB metadata field if it's a string
            if isinstance(order.get('metadata'), str):
                order['metadata'] = json.loads(order['metadata'])
            result.append(order)
        return result


async def fetch_recent_events(
    limit: int = 100,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    trading_mode: str = 'paper',
) -> list[dict[str, Any]]:
    """
    Fetch recent events from the live trading system.

    Args:
        limit: Maximum number of events to return
        event_type: Filter by event type (e.g., 'signal', 'order', 'error')
        severity: Filter by severity (e.g., 'info', 'warning', 'error')
        trading_mode: Trading mode schema ('real', 'paper', or 'replay')

    Returns:
        List of event dictionaries
    """
    pool = get_pool()
    table_name = _get_table_name('events', trading_mode)

    # Build query dynamically based on filters
    where_clauses = []
    params = []
    param_idx = 1

    if event_type:
        where_clauses.append(f"event_type = ${param_idx}")
        params.append(event_type)
        param_idx += 1

    if severity:
        where_clauses.append(f"severity = ${param_idx}")
        params.append(severity)
        param_idx += 1

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query = f"""
        SELECT
            timestamp,
            event_type,
            severity,
            message,
            details as metadata
        FROM {table_name}
        {where_sql}
        ORDER BY timestamp DESC
        LIMIT ${param_idx}
    """

    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        result = []
        for row in rows:
            event = dict(row)
            # Parse JSONB metadata field if it's a string (aliased as metadata from details)
            if isinstance(event.get('metadata'), str):
                event['metadata'] = json.loads(event['metadata'])
            result.append(event)
        return result


async def clear_live_events(trading_mode: str = 'paper') -> int:
    """
    Clear all events from the events table.

    Args:
        trading_mode: Trading mode schema ('real', 'paper', or 'replay')

    Returns:
        Number of events deleted
    """
    pool = get_pool()
    table_name = _get_table_name('events', trading_mode)

    query = f"DELETE FROM {table_name}"

    async with pool.acquire() as conn:
        result = await conn.execute(query)
        # Parse the result string (e.g., "DELETE 42") to get the count
        deleted_count = int(result.split()[-1]) if result.startswith("DELETE") else 0
        return deleted_count


async def fetch_trading_stats(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    trading_mode: str = 'paper',
) -> dict[str, Any]:
    """
    Calculate aggregate trading statistics.

    Args:
        start_time: Start of time range (optional)
        end_time: End of time range (optional)
        trading_mode: Trading mode schema ('real', 'paper', or 'replay')

    Returns:
        Dict with trading statistics
    """
    pool = get_pool()
    table_name = _get_table_name('positions', trading_mode)

    # Build time filters
    where_clauses = ["status = 'closed'"]
    params = []
    param_idx = 1

    if start_time:
        where_clauses.append(f"exit_time >= ${param_idx}")
        params.append(start_time)
        param_idx += 1

    if end_time:
        where_clauses.append(f"exit_time <= ${param_idx}")
        params.append(end_time)
        param_idx += 1

    where_sql = " AND ".join(where_clauses)

    query = f"""
        WITH pnl_calc AS (
            SELECT
                (COALESCE(exit_value, 0) - entry_cost) as realized_pnl
            FROM {table_name}
            WHERE {where_sql}
        )
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl,
            MAX(realized_pnl) as max_win,
            MIN(realized_pnl) as max_loss,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) as avg_loss
        FROM pnl_calc
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
        if row:
            stats = dict(row)
            # Calculate win rate as ratio (0-1)
            total = stats.get("total_trades", 0)
            winning = stats.get("winning_trades", 0)
            stats["win_rate"] = (winning / total) if total > 0 else 0.0
            return stats
        return {}


async def test_connection() -> bool:
    """
    Test database connectivity.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False


# =====================================================
# Account Management Functions
# =====================================================

async def fetch_broker_accounts(trading_mode: str = 'paper') -> list[dict[str, Any]]:
    """
    Fetch all broker accounts for a trading mode.

    Args:
        trading_mode: Trading mode ('real' or 'paper')

    Returns:
        List of account records
    """
    pool = get_pool()
    schema = 'real_trading' if trading_mode == 'real' else 'paper_trading'

    query = f"""
        SELECT
            account_hash,
            account_number,
            nickname,
            account_type,
            is_day_trader,
            is_closing_only_restricted,
            is_default,
            round_trips,
            created_at,
            updated_at
        FROM {schema}.broker_accounts
        ORDER BY is_default DESC, created_at DESC
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]


async def fetch_account_balance(
    account_hash: str,
    trading_mode: str = 'paper'
) -> Optional[dict[str, Any]]:
    """
    Fetch the latest balance for an account.

    Args:
        account_hash: Account hash identifier
        trading_mode: Trading mode ('real' or 'paper')

    Returns:
        Latest balance record or None
    """
    pool = get_pool()
    schema = 'real_trading' if trading_mode == 'real' else 'paper_trading'

    query = f"""
        SELECT
            account_hash,
            timestamp,
            cash_balance,
            available_funds,
            buying_power,
            day_trading_buying_power,
            liquidation_value,
            long_option_market_value,
            short_option_market_value,
            maintenance_requirement,
            margin_balance,
            portfolio_value,
            total_pnl,
            daily_pnl,
            win_rate,
            sharpe_ratio
        FROM {schema}.account_balance
        WHERE account_hash = $1
        ORDER BY timestamp DESC
        LIMIT 1
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, account_hash)
        return dict(row) if row else None


async def store_account_balance(
    balance_data: dict[str, Any],
    trading_mode: str = 'paper'
) -> None:
    """
    Store account balance snapshot.

    Args:
        balance_data: Balance data to store
        trading_mode: Trading mode ('real' or 'paper')
    """
    pool = get_pool()
    schema = 'real_trading' if trading_mode == 'real' else 'paper_trading'

    query = f"""
        INSERT INTO {schema}.account_balance (
            account_hash,
            timestamp,
            cash_balance,
            available_funds,
            buying_power,
            day_trading_buying_power,
            liquidation_value,
            long_option_market_value,
            short_option_market_value,
            maintenance_requirement,
            margin_balance,
            portfolio_value,
            total_pnl,
            daily_pnl,
            win_rate,
            sharpe_ratio,
            is_snapshot
        ) VALUES (
            $1, NOW(), $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
        )
    """

    async with pool.acquire() as conn:
        await conn.execute(
            query,
            balance_data['account_hash'],
            balance_data.get('cash_balance', 0),
            balance_data.get('available_funds', 0),
            balance_data.get('buying_power', 0),
            balance_data.get('day_trading_buying_power', 0),
            balance_data.get('liquidation_value', 0),
            balance_data.get('long_option_market_value', 0),
            balance_data.get('short_option_market_value', 0),
            balance_data.get('maintenance_requirement', 0),
            balance_data.get('margin_balance', 0),
            balance_data.get('portfolio_value', 0),
            balance_data.get('total_pnl', 0),
            balance_data.get('daily_pnl', 0),
            balance_data.get('win_rate'),
            balance_data.get('sharpe_ratio'),
            balance_data.get('is_snapshot', False)
        )


async def set_default_account(
    account_hash: str,
    trading_mode: str = 'paper'
) -> bool:
    """
    Set an account as the default for a trading mode.

    Args:
        account_hash: Account hash to set as default
        trading_mode: Trading mode ('real' or 'paper')

    Returns:
        True if successful, False if account not found
    """
    pool = get_pool()
    schema = 'real_trading' if trading_mode == 'real' else 'paper_trading'

    async with pool.acquire() as conn:
        # Check if account exists
        exists = await conn.fetchval(
            f"SELECT 1 FROM {schema}.broker_accounts WHERE account_hash = $1",
            account_hash
        )

        if not exists:
            return False

        # Transaction to update default status
        async with conn.transaction():
            # Clear current default
            await conn.execute(
                f"UPDATE {schema}.broker_accounts SET is_default = FALSE WHERE is_default = TRUE"
            )

            # Set new default
            await conn.execute(
                f"UPDATE {schema}.broker_accounts SET is_default = TRUE WHERE account_hash = $1",
                account_hash
            )

        return True


async def upsert_broker_account(
    account_data: dict[str, Any],
    trading_mode: str = 'paper'
) -> None:
    """
    Insert or update broker account information.

    Args:
        account_data: Account data to store
        trading_mode: Trading mode ('real' or 'paper')
    """
    pool = get_pool()
    schema = 'real_trading' if trading_mode == 'real' else 'paper_trading'

    query = f"""
        INSERT INTO {schema}.broker_accounts (
            account_hash,
            account_number,
            nickname,
            account_type,
            is_day_trader,
            is_closing_only_restricted,
            round_trips,
            created_at,
            updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, NOW(), NOW()
        )
        ON CONFLICT (account_hash) DO UPDATE SET
            account_number = EXCLUDED.account_number,
            account_type = EXCLUDED.account_type,
            is_day_trader = EXCLUDED.is_day_trader,
            is_closing_only_restricted = EXCLUDED.is_closing_only_restricted,
            round_trips = EXCLUDED.round_trips,
            updated_at = NOW()
    """

    async with pool.acquire() as conn:
        await conn.execute(
            query,
            account_data['account_hash'],
            account_data['account_number'],
            account_data['nickname'],
            account_data['account_type'],
            account_data.get('is_day_trader', False),
            account_data.get('is_closing_only_restricted', False),
            account_data.get('round_trips', 0)
        )


async def store_order(
    order_data: dict[str, Any],
    trading_mode: str = 'paper'
) -> None:
    """
    Store an order from Schwab API sync.

    Args:
        order_data: Order data to store
        trading_mode: Trading mode ('real' or 'paper')
    """
    pool = get_pool()
    table_name = _get_table_name('orders', trading_mode)

    # This is a simplified version - expand based on actual order structure
    query = f"""
        INSERT INTO {table_name} (
            order_id,
            account_hash,
            status,
            order_type,
            created_at
        ) VALUES (
            $1, $2, $3, $4, $5
        )
        ON CONFLICT (order_id) DO UPDATE SET
            status = EXCLUDED.status
    """

    async with pool.acquire() as conn:
        await conn.execute(
            query,
            order_data['order_id'],
            order_data.get('account_hash'),
            order_data.get('status', 'UNKNOWN'),
            order_data.get('order_type', 'UNKNOWN'),
            order_data.get('entered_time', datetime.now())
        )
