"""Utilities for live trading engine."""

import uuid
from datetime import datetime, time
from typing import Optional
import pytz

from quant_vibe.utils import now_utc


def format_currency(value: float) -> str:
    """Format a value as currency."""
    return f"${value:,.2f}"


def format_percentage(value: float) -> str:
    """Format a value as percentage."""
    return f"{value:.2f}%"


def get_market_hours(timezone: str = "America/New_York") -> tuple[time, time]:
    """Get market open and close times."""
    return time(9, 30), time(16, 0)


def is_market_open(current_time: Optional[datetime] = None) -> bool:
    """Check if market is currently open."""
    if current_time is None:
        current_time = now_utc()

    # Convert to ET
    et_tz = pytz.timezone('America/New_York')
    if current_time.tzinfo is None:
        current_time = pytz.UTC.localize(current_time)
    current_time_et = current_time.astimezone(et_tz)

    # Check if weekday (Mon-Fri)
    if current_time_et.weekday() >= 5:
        return False

    # Check if within market hours
    market_open, market_close = get_market_hours()
    current_time_only = current_time_et.time()

    return market_open <= current_time_only <= market_close


def generate_position_id(
    strategy_prefix: str,
    current_time: datetime,
    counter: Optional[int] = None,
    include_uuid: bool = False
) -> str:
    """Generate a unique position ID.

    Creates a globally unique position ID using:
    - Strategy prefix (e.g., "BVP", "COIN", "BB")
    - Timestamp (YYYYMMDD_HHMMSS)
    - Optional counter (for strategies that track daily trades)
    - Optional UUID suffix (for guaranteed uniqueness)

    Args:
        strategy_prefix: Short strategy identifier
        current_time: Current datetime
        counter: Optional trade counter for the day
        include_uuid: If True, append a short UUID

    Returns:
        Unique position ID string

    Examples:
        >>> dt = datetime(2026, 1, 2, 15, 30, 45)
        >>> generate_position_id("BVP", dt)
        'BVP_20260102_153045'
    """
    # Base format: PREFIX_YYYYMMDD_HHMMSS
    timestamp_str = current_time.strftime("%Y%m%d_%H%M%S")
    position_id = f"{strategy_prefix}_{timestamp_str}"

    # Add counter if provided
    if counter is not None:
        position_id = f"{position_id}_{counter}"

    # Add UUID suffix if requested
    if include_uuid:
        uuid_suffix = uuid.uuid4().hex[:8]
        position_id = f"{position_id}_{uuid_suffix}"

    return position_id


class TradingState:
    """Trading engine states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


class EventType:
    """Trading system event types."""
    # Engine events
    ENGINE_STARTED = "engine_started"
    ENGINE_STOPPED = "engine_stopped"
    ENGINE_PAUSED = "engine_paused"
    ENGINE_RESUMED = "engine_resumed"
    ENGINE_ERROR = "engine_error"

    # Data events
    DATA_RECEIVED = "data_received"
    DATA_STALE = "data_stale"
    DATA_ERROR = "data_error"

    # Strategy events
    STRATEGY_SIGNAL = "strategy_signal"
    STRATEGY_ENTRY = "strategy_entry"
    STRATEGY_EXIT = "strategy_exit"
    STRATEGY_ERROR = "strategy_error"
    STRATEGY_RELOAD = "strategy_reload"

    # Order events
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIALLY_FILLED = "order_partially_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    ORDER_ERROR = "order_error"

    # Position events
    POSITION_OPENED = "position_opened"
    POSITION_UPDATED = "position_updated"
    POSITION_CLOSED = "position_closed"

    # Risk events
    RISK_LIMIT_BREACHED = "risk_limit_breached"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    POSITION_LIMIT = "position_limit"

    # Reconciliation events
    RECONCILIATION = "reconciliation"

    # Alert events
    ALERT_CRITICAL = "alert_critical"
    ALERT_WARNING = "alert_warning"
    ALERT_INFO = "alert_info"