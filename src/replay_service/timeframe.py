"""Timeframe parsing utilities for replay service."""

from datetime import datetime, timedelta, time
from typing import Tuple
from zoneinfo import ZoneInfo

from quant_vibe.utils.timestamp_utils import to_utc

# Market hours constants
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
ET_TIMEZONE = ZoneInfo("America/New_York")


def parse_timeframe(timeframe_str: str) -> Tuple[datetime, datetime]:
    """Parse a timeframe string into start/end datetime range.

    Supported formats:
    - "today" - Market hours today
    - "yesterday" - Market hours previous trading day
    - "last_1h" or "1h" - Most recent 1 hour
    - "last_30m" or "30m" - Most recent 30 minutes
    - "2025-01-03" - Specific date (market hours)
    - "2025-01-03T14:00:00/2025-01-03T15:30:00" - Exact range

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC

    Raises:
        ValueError: If timeframe string is invalid
    """
    timeframe_str = timeframe_str.strip().lower()
    now_et = datetime.now(ET_TIMEZONE)

    if timeframe_str == "today":
        start_dt, end_dt = _get_market_hours(now_et.date())
    elif timeframe_str == "yesterday":
        yesterday = now_et.date() - timedelta(days=1)
        start_dt, end_dt = _get_market_hours(yesterday)
    elif timeframe_str.startswith("last_") or _is_relative_time(timeframe_str):
        start_dt, end_dt = _parse_relative_timeframe(timeframe_str, now_et)
    elif "/" in timeframe_str:
        start_dt, end_dt = _parse_iso_range(timeframe_str)
    elif _is_date_string(timeframe_str):
        date = datetime.fromisoformat(timeframe_str).date()
        start_dt, end_dt = _get_market_hours(date)
    else:
        raise ValueError(
            f"Invalid timeframe '{timeframe_str}'. "
            f"Supported: 'today', 'yesterday', 'last_1h', '1h', '30m', "
            f"'2025-01-03', '2025-01-03T14:00:00/2025-01-03T15:30:00'"
        )

    # Convert to UTC and validate
    start_utc = to_utc(start_dt)
    end_utc = to_utc(end_dt)

    if start_utc >= end_utc:
        raise ValueError(f"Start time {start_utc} must be before end time {end_utc}")

    return start_utc, end_utc


def _get_market_hours(date) -> Tuple[datetime, datetime]:
    """Get market open and close times for a given date."""
    start = datetime.combine(date, MARKET_OPEN, tzinfo=ET_TIMEZONE)
    end = datetime.combine(date, MARKET_CLOSE, tzinfo=ET_TIMEZONE)
    return start, end


def _is_relative_time(s: str) -> bool:
    """Check if string represents a relative time format."""
    return s.endswith(("h", "m"))


def _is_date_string(s: str) -> bool:
    """Check if string represents a date in YYYY-MM-DD format."""
    return len(s) == 10 and s.count("-") == 2


def _parse_relative_timeframe(timeframe_str: str, now_et: datetime) -> Tuple[datetime, datetime]:
    """Parse relative timeframe like 'last_1h' or '30m'."""
    timeframe_str = timeframe_str.replace("last_", "")

    if timeframe_str.endswith("h"):
        hours = int(timeframe_str[:-1])
        delta = timedelta(hours=hours)
    elif timeframe_str.endswith("m"):
        minutes = int(timeframe_str[:-1])
        delta = timedelta(minutes=minutes)
    else:
        raise ValueError(f"Invalid time unit in '{timeframe_str}'. Use 'h' or 'm'")

    end_dt = now_et
    start_dt = end_dt - delta
    return start_dt, end_dt


def _parse_iso_range(timeframe_str: str) -> Tuple[datetime, datetime]:
    """Parse ISO 8601 datetime range."""
    start_str, end_str = timeframe_str.split("/")
    start_dt = datetime.fromisoformat(start_str)
    end_dt = datetime.fromisoformat(end_str)

    # Add ET timezone if naive
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=ET_TIMEZONE)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=ET_TIMEZONE)

    return start_dt, end_dt