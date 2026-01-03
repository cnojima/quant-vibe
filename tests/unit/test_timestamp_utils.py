"""
Unit tests for timestamp utilities.
"""

import pytest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from quant_vibe.utils.timestamp_utils import (
    now_utc,
    to_utc,
    from_timestamp,
    ensure_utc_aware,
    is_utc_aware,
    UTC,
    EST,
)


def test_now_utc_returns_utc_aware():
    """Test that now_utc() returns UTC-aware datetime"""
    ts = now_utc()
    assert ts.tzinfo is not None
    assert ts.tzinfo == UTC
    assert is_utc_aware(ts)


def test_to_utc_naive_datetime():
    """Test converting naive datetime to UTC (assumes naive is UTC)"""
    naive = datetime(2025, 12, 23, 14, 30, 0)
    utc_dt = to_utc(naive)

    assert utc_dt.tzinfo == UTC
    assert utc_dt.year == 2025
    assert utc_dt.month == 12
    assert utc_dt.day == 23
    assert utc_dt.hour == 14
    assert utc_dt.minute == 30


def test_to_utc_est_datetime():
    """Test converting EST datetime to UTC"""
    # 9:30 AM EST = 2:30 PM UTC (EST is UTC-5)
    est_time = datetime(2025, 12, 23, 9, 30, 0, tzinfo=EST)
    utc_dt = to_utc(est_time)

    assert utc_dt.tzinfo == UTC
    assert utc_dt.hour == 14  # 9:30 AM EST = 14:30 UTC
    assert utc_dt.minute == 30


def test_to_utc_already_utc():
    """Test that UTC-aware datetime is returned as-is"""
    utc_time = datetime(2025, 12, 23, 14, 30, 0, tzinfo=UTC)
    result = to_utc(utc_time)

    assert result is utc_time  # Should be same object
    assert result.tzinfo == UTC


def test_from_timestamp():
    """Test converting Unix timestamp to UTC datetime"""
    # 2023-12-23 14:30:00 UTC
    ts = 1703344200.0
    dt = from_timestamp(ts)

    assert dt.tzinfo == UTC
    assert dt.year == 2023
    assert dt.month == 12
    assert dt.day == 23


def test_ensure_utc_aware_raises_on_naive():
    """Test that ensure_utc_aware raises ValueError for naive datetime"""
    naive = datetime(2025, 12, 23, 14, 30, 0)

    with pytest.raises(ValueError, match="is naive"):
        ensure_utc_aware(naive)


def test_ensure_utc_aware_converts_est():
    """Test that ensure_utc_aware converts EST to UTC"""
    est_time = datetime(2025, 12, 23, 9, 30, 0, tzinfo=EST)
    utc_dt = ensure_utc_aware(est_time)

    assert utc_dt.tzinfo == UTC
    assert utc_dt.hour == 14  # Converted to UTC


def test_ensure_utc_aware_passes_utc():
    """Test that ensure_utc_aware accepts UTC-aware datetime"""
    utc_time = datetime(2025, 12, 23, 14, 30, 0, tzinfo=UTC)
    result = ensure_utc_aware(utc_time)

    assert result == utc_time
    assert result.tzinfo == UTC


def test_is_utc_aware():
    """Test is_utc_aware() detection"""
    utc_time = datetime(2025, 12, 23, 14, 30, 0, tzinfo=UTC)
    est_time = datetime(2025, 12, 23, 9, 30, 0, tzinfo=EST)
    naive = datetime(2025, 12, 23, 14, 30, 0)

    assert is_utc_aware(utc_time) is True
    assert is_utc_aware(est_time) is False  # Aware but not UTC
    assert is_utc_aware(naive) is False


def test_timestamp_roundtrip():
    """Test converting datetime to timestamp and back"""
    original = now_utc()
    ts = original.timestamp()
    recovered = from_timestamp(ts)

    # Should be equal (within microsecond precision)
    assert abs((recovered - original).total_seconds()) < 0.001
