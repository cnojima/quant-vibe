"""Utilities for live trading engine."""

import logging
import sys
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
