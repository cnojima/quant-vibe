"""Pytest fixtures for token_service tests."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest
import sqlite3
from datetime import datetime, timezone
from unittest.mock import Mock


@pytest.fixture
def temp_db_path(tmp_path):
    """Create temporary database path."""
    db_path = tmp_path / "test_tokens.db"
    return str(db_path)


@pytest.fixture
def mock_schwabdev_client():
    """Create a mock schwabdev client."""
    client = Mock()
    client.update_tokens = Mock()
    return client


@pytest.fixture
def sample_token_db(tmp_path):
    """Create a sample schwabdev token database with test data."""
    db_path = tmp_path / "tokens.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create schwabdev table (same schema as schwabdev library)
    cursor.execute("""
        CREATE TABLE schwabdev (
            access_token_issued TEXT,
            refresh_token_issued TEXT,
            access_token TEXT,
            refresh_token TEXT,
            id_token TEXT,
            expires_in INTEGER,
            token_type TEXT,
            scope TEXT
        )
    """)

    # Insert sample token
    now_utc = datetime.now(timezone.utc)
    cursor.execute("""
        INSERT INTO schwabdev VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_utc.isoformat(),  # access_token_issued
        now_utc.isoformat(),  # refresh_token_issued
        "test_access_token_12345",  # access_token
        "test_refresh_token_67890",  # refresh_token
        "test_id_token",  # id_token
        1800,  # expires_in (30 minutes)
        "Bearer",  # token_type
        "api",  # scope
    ))

    conn.commit()
    conn.close()

    return str(db_path)


@pytest.fixture
def expired_token_db(tmp_path):
    """Create a token database with expired tokens."""
    db_path = tmp_path / "expired_tokens.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE schwabdev (
            access_token_issued TEXT,
            refresh_token_issued TEXT,
            access_token TEXT,
            refresh_token TEXT,
            id_token TEXT,
            expires_in INTEGER,
            token_type TEXT,
            scope TEXT
        )
    """)

    # Insert expired token (issued 2 hours ago)
    from datetime import timedelta
    past_time = datetime.now(timezone.utc) - timedelta(hours=2)

    cursor.execute("""
        INSERT INTO schwabdev VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        past_time.isoformat(),
        past_time.isoformat(),
        "expired_access_token",
        "expired_refresh_token",
        "expired_id_token",
        1800,  # expires_in (30 minutes)
        "Bearer",
        "api",
    ))

    conn.commit()
    conn.close()

    return str(db_path)


@pytest.fixture
def empty_token_db(tmp_path):
    """Create an empty token database."""
    db_path = tmp_path / "empty_tokens.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE schwabdev (
            access_token_issued TEXT,
            refresh_token_issued TEXT,
            access_token TEXT,
            refresh_token TEXT,
            id_token TEXT,
            expires_in INTEGER,
            token_type TEXT,
            scope TEXT
        )
    """)

    conn.commit()
    conn.close()

    return str(db_path)


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = Mock()
    logger.info = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.debug = Mock()
    return logger
