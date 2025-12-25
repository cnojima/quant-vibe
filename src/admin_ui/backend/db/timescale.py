"""
TimescaleDB database connection and query utilities.

Provides async connection pool and query methods for:
- Live trading engine state
- Positions and orders
- Events and logs
"""

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


async def fetch_engine_state() -> Optional[dict[str, Any]]:
    """
    Fetch the latest live trading engine state.

    Returns:
        Dict with engine state or None if no state found
    """
    pool = get_pool()

    query = """
        SELECT
            timestamp,
            state,
            paper_trading,
            total_bars_processed,
            total_signals_generated,
            uptime_seconds,
            metadata
        FROM live_engine_state
        ORDER BY timestamp DESC
        LIMIT 1
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query)
        if row:
            return dict(row)
        return None


async def fetch_active_positions(limit: int = 100) -> list[dict[str, Any]]:
    """
    Fetch active (open) positions.

    Args:
        limit: Maximum number of positions to return

    Returns:
        List of position dictionaries
    """
    pool = get_pool()

    query = """
        SELECT
            position_id,
            strategy_name,
            entry_time,
            entry_cost,
            current_value,
            unrealized_pnl,
            legs,
            metadata
        FROM live_positions
        WHERE status = 'open'
        ORDER BY entry_time DESC
        LIMIT $1
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, limit)
        return [dict(row) for row in rows]


async def fetch_closed_positions(limit: int = 100) -> list[dict[str, Any]]:
    """
    Fetch closed positions.

    Args:
        limit: Maximum number of positions to return

    Returns:
        List of position dictionaries
    """
    pool = get_pool()

    query = """
        SELECT
            position_id,
            strategy_name,
            entry_time,
            entry_cost,
            exit_time,
            exit_value,
            realized_pnl,
            exit_reason,
            legs,
            metadata
        FROM live_positions
        WHERE status = 'closed'
        ORDER BY exit_time DESC
        LIMIT $1
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, limit)
        return [dict(row) for row in rows]


async def fetch_open_orders(limit: int = 100) -> list[dict[str, Any]]:
    """
    Fetch open orders.

    Args:
        limit: Maximum number of orders to return

    Returns:
        List of order dictionaries
    """
    pool = get_pool()

    query = """
        SELECT
            order_id,
            position_id,
            order_type,
            status,
            submitted_time,
            symbol,
            quantity,
            limit_price,
            metadata
        FROM live_orders
        WHERE status IN ('pending', 'submitted', 'accepted')
        ORDER BY submitted_time DESC
        LIMIT $1
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, limit)
        return [dict(row) for row in rows]


async def fetch_recent_events(
    limit: int = 100,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Fetch recent events from the live trading system.

    Args:
        limit: Maximum number of events to return
        event_type: Filter by event type (e.g., 'signal', 'order', 'error')
        severity: Filter by severity (e.g., 'info', 'warning', 'error')

    Returns:
        List of event dictionaries
    """
    pool = get_pool()

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
            metadata
        FROM live_events
        {where_sql}
        ORDER BY timestamp DESC
        LIMIT ${param_idx}
    """

    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def fetch_trading_stats(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict[str, Any]:
    """
    Calculate aggregate trading statistics.

    Args:
        start_time: Start of time range (optional)
        end_time: End of time range (optional)

    Returns:
        Dict with trading statistics
    """
    pool = get_pool()

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
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losing_trades,
            SUM(realized_pnl) as total_pnl,
            AVG(realized_pnl) as avg_pnl,
            MAX(realized_pnl) as max_win,
            MIN(realized_pnl) as max_loss,
            AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
            AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END) as avg_loss
        FROM live_positions
        WHERE {where_sql}
    """

    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params)
        if row:
            stats = dict(row)
            # Calculate win rate
            total = stats.get("total_trades", 0)
            winning = stats.get("winning_trades", 0)
            stats["win_rate"] = (winning / total * 100) if total > 0 else 0.0
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
