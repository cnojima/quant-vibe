"""
Timestamp utilities for enforcing UTC-aware datetimes.

This module provides a single source of truth for creating timestamps
to prevent naive/aware datetime mixing bugs.

All timestamps in the system MUST be:
1. Timezone-aware (not naive)
2. In UTC timezone
3. Created via these utility functions

Usage:
    from quant_vibe.utils.timestamp_utils import now_utc, to_utc

    # Create current timestamp
    ts = now_utc()  # Always UTC-aware

    # Convert naive datetime to UTC
    naive_dt = datetime(2025, 12, 23, 14, 30)
    utc_dt = to_utc(naive_dt)  # Assumes naive is UTC, adds timezone info
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


UTC = ZoneInfo("UTC")
EST = ZoneInfo("America/New_York")


def now_utc() -> datetime:
    """
    Get current timestamp as UTC-aware datetime.

    Returns:
        datetime: Current time in UTC timezone (always aware)

    Example:
        >>> ts = now_utc()
        >>> ts.tzinfo  # ZoneInfo(key='UTC')
        >>> ts.tzinfo is None  # False (never naive)
    """
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    """
    Convert datetime to UTC-aware datetime.

    Args:
        dt: Datetime to convert (can be naive or aware)

    Returns:
        datetime: UTC-aware datetime

    Behavior:
        - If naive: Assumes UTC and adds timezone info
        - If aware (non-UTC): Converts to UTC
        - If already UTC-aware: Returns as-is

    Example:
        >>> naive = datetime(2025, 12, 23, 14, 30)
        >>> to_utc(naive)  # 2025-12-23 14:30:00+00:00

        >>> est_time = datetime(2025, 12, 23, 9, 30, tzinfo=EST)
        >>> to_utc(est_time)  # 2025-12-23 14:30:00+00:00 (converted)
    """
    if dt.tzinfo is None:
        # Naive datetime - assume UTC and add timezone info
        return dt.replace(tzinfo=UTC)
    elif dt.tzinfo != UTC:
        # Aware but not UTC - convert to UTC
        return dt.astimezone(UTC)
    else:
        # Already UTC-aware
        return dt


def from_timestamp(ts: float) -> datetime:
    """
    Convert Unix timestamp to UTC-aware datetime.

    Args:
        ts: Unix timestamp (seconds since epoch)

    Returns:
        datetime: UTC-aware datetime

    Example:
        >>> from_timestamp(1703344200.0)
        datetime.datetime(2023, 12, 23, 14, 30, tzinfo=ZoneInfo('UTC'))
    """
    return datetime.fromtimestamp(ts, tz=UTC)


def ensure_utc_aware(dt: datetime) -> datetime:
    """
    Ensure datetime is UTC-aware, raising error if not convertible.

    Args:
        dt: Datetime to validate

    Returns:
        datetime: UTC-aware datetime

    Raises:
        ValueError: If datetime cannot be safely converted to UTC

    Use this when you need strict validation (e.g., Pydantic validators)

    Example:
        >>> ensure_utc_aware(now_utc())  # Raises ValueError
        >>> ensure_utc_aware(now_utc())  # OK
    """
    if dt.tzinfo is None:
        raise ValueError(
            f"Datetime {dt} is naive (no timezone). "
            "Use now_utc() or to_utc() to create timezone-aware datetimes."
        )

    if dt.tzinfo != UTC:
        # Convert to UTC
        return dt.astimezone(UTC)

    return dt


def is_utc_aware(dt: datetime) -> bool:
    """
    Check if datetime is UTC-aware.

    Args:
        dt: Datetime to check

    Returns:
        bool: True if datetime is UTC-aware, False otherwise

    Example:
        >>> is_utc_aware(now_utc())  # True
        >>> is_utc_aware(now_utc())  # False
    """
    return dt.tzinfo is not None and dt.tzinfo == UTC
