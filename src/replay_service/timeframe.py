"""Timeframe parsing utilities for replay service."""

from datetime import datetime, timedelta, time
from typing import Tuple
import zoneinfo

from quant_vibe.utils import to_utc


# Market hours: 9:30 AM - 4:00 PM ET
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
ET_TIMEZONE = zoneinfo.ZoneInfo("America/New_York")


def parse_timeframe(timeframe_str: str) -> Tuple[datetime, datetime]:
    """Parse a timeframe string into start/end datetime range.

    Supported formats:
    - "today" - Market hours today (9:30 AM - 4:00 PM ET)
    - "yesterday" - Market hours previous trading day
    - "last_1h" or "1h" - Most recent 1 hour of data
    - "last_30m" or "30m" - Most recent 30 minutes
    - "2025-01-03" - Specific date (market hours)
    - "2025-01-03T14:00:00/2025-01-03T15:30:00" - Exact range (ISO 8601)

    Args:
        timeframe_str: Timeframe specification string

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC

    Raises:
        ValueError: If timeframe string is invalid
    """
    timeframe_str = timeframe_str.strip().lower()

    # Get current time in ET
    now_et = datetime.now(ET_TIMEZONE)

    # Handle relative timeframes
    if timeframe_str == "today":
        start_dt = datetime.combine(now_et.date(), MARKET_OPEN, tzinfo=ET_TIMEZONE)
        end_dt = datetime.combine(now_et.date(), MARKET_CLOSE, tzinfo=ET_TIMEZONE)

    elif timeframe_str == "yesterday":
        yesterday = now_et.date() - timedelta(days=1)
        start_dt = datetime.combine(yesterday, MARKET_OPEN, tzinfo=ET_TIMEZONE)
        end_dt = datetime.combine(yesterday, MARKET_CLOSE, tzinfo=ET_TIMEZONE)

    elif timeframe_str.startswith("last_") or timeframe_str.endswith(("h", "m")):
        # Parse "last_1h", "1h", "last_30m", "30m"
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

    elif "/" in timeframe_str:
        # ISO 8601 range: "2025-01-03T14:00:00/2025-01-03T15:30:00"
        start_str, end_str = timeframe_str.split("/")
        start_dt = datetime.fromisoformat(start_str)
        end_dt = datetime.fromisoformat(end_str)

        # If naive, assume ET timezone
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=ET_TIMEZONE)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=ET_TIMEZONE)

    elif len(timeframe_str) == 10 and timeframe_str.count("-") == 2:
        # Specific date: "2025-01-03"
        date = datetime.fromisoformat(timeframe_str).date()
        start_dt = datetime.combine(date, MARKET_OPEN, tzinfo=ET_TIMEZONE)
        end_dt = datetime.combine(date, MARKET_CLOSE, tzinfo=ET_TIMEZONE)

    else:
        raise ValueError(
            f"Invalid timeframe '{timeframe_str}'. "
            f"Supported: 'today', 'yesterday', 'last_1h', '1h', '30m', "
            f"'2025-01-03', '2025-01-03T14:00:00/2025-01-03T15:30:00'"
        )

    # Convert to UTC
    start_utc = to_utc(start_dt)
    end_utc = to_utc(end_dt)

    if start_utc >= end_utc:
        raise ValueError(f"Start time {start_utc} must be before end time {end_utc}")

    return start_utc, end_utc
