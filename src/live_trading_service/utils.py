"""Utilities for live trading engine."""

import logging
import sys
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logging(
    log_dir: str = "logs/live_trading",
    log_level: str = "INFO",
    console_output: bool = True
) -> logging.Logger:
    """
    Set up comprehensive logging for live trading.

    This is a legacy wrapper - new code should use setup_normalized_logging.

    Args:
        log_dir: Directory to store log files
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_output: Whether to also output to console

    Returns:
        Configured logger instance
    """
    # Use unified normalized logging for consistent EST timestamps
    from quant_vibe.config.logging_config import setup_normalized_logging

    return setup_normalized_logging(
        app_name="live_trading",
        log_level=log_level,
        log_dir=log_dir,
    )


def format_currency(value: float) -> str:
    """Format a value as currency."""
    return f"${value:,.2f}"


def format_percentage(value: float) -> str:
    """Format a value as percentage."""
    return f"{value:.2f}%"


def get_market_hours(timezone: str = "America/New_York"):
    """
    Get market open and close times.

    Returns:
        Tuple of (market_open, market_close) as time objects
    """
    from datetime import time
    return time(9, 30), time(16, 0)


def is_market_open(current_time: Optional[datetime] = None) -> bool:
    """
    Check if market is currently open.

    Args:
        current_time: Time to check (defaults to now)

    Returns:
        True if market is open
    """
    import pytz
    from datetime import datetime

    if current_time is None:
        current_time = datetime.now()

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
    """
    Generate a unique position ID.

    This function creates a globally unique position ID using a combination of:
    - Strategy prefix (e.g., "BVP", "COIN", "BB")
    - Timestamp (YYYYMMDD_HHMMSS)
    - Optional counter (for strategies that track daily trades)
    - Optional UUID suffix (for guaranteed uniqueness)

    Args:
        strategy_prefix: Short strategy identifier (e.g., "BVP", "COIN", "BB")
        current_time: Current datetime
        counter: Optional trade counter for the day (1-based)
        include_uuid: If True, append a short UUID for guaranteed uniqueness

    Returns:
        Unique position ID string

    Examples:
        >>> from datetime import datetime
        >>> dt = datetime(2026, 1, 2, 15, 30, 45)
        >>> generate_position_id("BVP", dt)
        'BVP_20260102_153045'
        >>> generate_position_id("COIN", dt, counter=3)
        'COIN_20260102_153045_3'
        >>> generate_position_id("BB", dt, include_uuid=True)
        'BB_20260102_153045_a1b2c3d4'

    Note:
        - Timestamp format ensures chronological sorting
        - Counter is optional and should only be used if strategy tracks daily trades
        - UUID suffix provides guaranteed uniqueness if needed (e.g., for testing)
        - Maximum ID length: ~50 characters with UUID, ~25 without
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
    """Enumeration of trading engine states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


class EventType:
    """Types of events in the trading system."""
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

    # Alert events
    ALERT_CRITICAL = "alert_critical"
    ALERT_WARNING = "alert_warning"
    ALERT_INFO = "alert_info"
