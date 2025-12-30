"""Unit tests for CentralizedTokenManager."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
from token_service.manager import CentralizedTokenManager, TokenInfo


class TestTokenInfo:
    """Test cases for TokenInfo class."""

    def test_initialization(self):
        """Test TokenInfo initialization."""
        now = datetime.now(timezone.utc)
        token_info = TokenInfo(
            access_token="test_access",
            refresh_token="test_refresh",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800,
            token_type="Bearer",
            scope="api"
        )

        assert token_info.access_token == "test_access"
        assert token_info.refresh_token == "test_refresh"
        assert token_info.access_token_issued == now
        assert token_info.refresh_token_issued == now
        assert token_info.expires_in == 1800
        assert token_info.token_type == "Bearer"
        assert token_info.scope == "api"

    def test_access_token_expires_at(self):
        """Test access_token_expires_at calculation."""
        now = datetime.now(timezone.utc)
        token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800
        )

        expected_expiry = now + timedelta(seconds=1800)
        assert token_info.access_token_expires_at == expected_expiry

    def test_refresh_token_expires_at(self):
        """Test refresh_token_expires_at calculation (7 days)."""
        now = datetime.now(timezone.utc)
        token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800
        )

        expected_expiry = now + timedelta(days=7)
        assert token_info.refresh_token_expires_at == expected_expiry

    def test_is_access_token_expired_false(self):
        """Test is_access_token_expired when token is valid."""
        now = datetime.now(timezone.utc)
        token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800
        )

        assert token_info.is_access_token_expired is False

    def test_is_access_token_expired_true(self):
        """Test is_access_token_expired when token is expired."""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=past,
            refresh_token_issued=past,
            expires_in=1800  # 30 minutes
        )

        assert token_info.is_access_token_expired is True

    def test_is_refresh_token_expired_false(self):
        """Test is_refresh_token_expired when token is valid."""
        now = datetime.now(timezone.utc)
        token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800
        )

        assert token_info.is_refresh_token_expired is False

    def test_is_refresh_token_expired_true(self):
        """Test is_refresh_token_expired when token is expired."""
        past = datetime.now(timezone.utc) - timedelta(days=8)
        token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=past,
            refresh_token_issued=past,
            expires_in=1800
        )

        assert token_info.is_refresh_token_expired is True

    def test_access_token_age_seconds(self):
        """Test access_token_age_seconds calculation."""
        past = datetime.now(timezone.utc) - timedelta(minutes=10)
        token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=past,
            refresh_token_issued=past,
            expires_in=1800
        )

        age = token_info.access_token_age_seconds
        # Should be approximately 600 seconds (10 minutes)
        assert 590 <= age <= 610

    def test_seconds_until_expiration(self):
        """Test seconds_until_expiration calculation."""
        now = datetime.now(timezone.utc)
        token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800
        )

        remaining = token_info.seconds_until_expiration
        # Should be approximately 1800 seconds
        assert 1790 <= remaining <= 1810

    def test_to_dict(self):
        """Test to_dict method."""
        now = datetime.now(timezone.utc)
        token_info = TokenInfo(
            access_token="test_access",
            refresh_token="test_refresh",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800,
            token_type="Bearer",
            scope="api"
        )

        result = token_info.to_dict()

        assert result["access_token"] == "test_access"
        assert result["expires_in"] == 1800
        assert result["token_type"] == "Bearer"
        assert result["scope"] == "api"
        assert "access_token_issued" in result
        assert "access_token_expires_at" in result
        assert "refresh_token_issued" in result
        assert "refresh_token_expires_at" in result
        assert isinstance(result["is_access_token_expired"], bool)
        assert isinstance(result["is_refresh_token_expired"], bool)
        assert isinstance(result["access_token_age_seconds"], float)
        assert isinstance(result["seconds_until_expiration"], float)


class TestCentralizedTokenManager:
    """Test cases for CentralizedTokenManager."""

    @patch('token_service.manager.schwabdev.Client')
    def test_initialization(self, mock_schwabdev, temp_db_path, mock_logger):
        """Test CentralizedTokenManager initialization."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=temp_db_path,
            logger=mock_logger
        )

        assert manager.api_key == "test_key"
        assert manager.api_secret == "test_secret"
        assert manager.callback_url == "https://test.com"
        assert manager.tokens_db_path == temp_db_path
        assert manager.logger == mock_logger
        assert manager.last_refresh is None

        # Verify schwabdev client was initialized
        mock_schwabdev.assert_called_once_with(
            app_key="test_key",
            app_secret="test_secret",
            callback_url="https://test.com",
            tokens_db=temp_db_path
        )

    @patch('token_service.manager.schwabdev.Client')
    def test_initialization_creates_token_directory(self, mock_schwabdev, tmp_path, mock_logger):
        """Test that initialization creates token directory."""
        db_path = tmp_path / "subdir" / "tokens.db"

        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=str(db_path),
            logger=mock_logger
        )

        assert Path(db_path).parent.exists()

    @patch('token_service.manager.schwabdev.Client')
    def test_initialization_failure(self, mock_schwabdev, temp_db_path, mock_logger):
        """Test initialization failure handling."""
        mock_schwabdev.side_effect = Exception("Init failed")

        with pytest.raises(Exception, match="Init failed"):
            CentralizedTokenManager(
                api_key="test_key",
                api_secret="test_secret",
                callback_url="https://test.com",
                tokens_db_path=temp_db_path,
                logger=mock_logger
            )

    @patch('token_service.manager.schwabdev.Client')
    def test_get_token_info_no_database(self, mock_schwabdev, temp_db_path, mock_logger):
        """Test get_token_info when database doesn't exist."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=temp_db_path,
            logger=mock_logger
        )

        token_info = manager.get_token_info()

        assert token_info is None
        mock_logger.warning.assert_called()

    @patch('token_service.manager.schwabdev.Client')
    def test_get_token_info_success(self, mock_schwabdev, sample_token_db, mock_logger):
        """Test get_token_info successfully retrieves token."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=sample_token_db,
            logger=mock_logger
        )

        token_info = manager.get_token_info()

        assert token_info is not None
        assert token_info.access_token == "test_access_token_12345"
        assert token_info.refresh_token == "test_refresh_token_67890"
        assert token_info.expires_in == 1800
        assert token_info.token_type == "Bearer"
        assert token_info.scope == "api"

    @patch('token_service.manager.schwabdev.Client')
    def test_get_token_info_empty_database(self, mock_schwabdev, empty_token_db, mock_logger):
        """Test get_token_info with empty database."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=empty_token_db,
            logger=mock_logger
        )

        token_info = manager.get_token_info()

        assert token_info is None
        mock_logger.warning.assert_called()

    @patch('token_service.manager.schwabdev.Client')
    def test_refresh_token_success(self, mock_schwabdev, temp_db_path, mock_logger):
        """Test successful token refresh."""
        mock_client_instance = Mock()
        mock_schwabdev.return_value = mock_client_instance

        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=temp_db_path,
            logger=mock_logger
        )

        result = manager.refresh_token()

        assert result is True
        assert manager.last_refresh is not None
        assert isinstance(manager.last_refresh, datetime)
        mock_client_instance.update_tokens.assert_called_once()

    @patch('token_service.manager.schwabdev.Client')
    def test_refresh_token_failure(self, mock_schwabdev, temp_db_path, mock_logger):
        """Test token refresh failure."""
        mock_client_instance = Mock()
        mock_client_instance.update_tokens.side_effect = Exception("Refresh failed")
        mock_schwabdev.return_value = mock_client_instance

        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=temp_db_path,
            logger=mock_logger
        )

        result = manager.refresh_token()

        assert result is False
        assert manager.last_refresh is None
        mock_logger.error.assert_called()

    @patch('token_service.manager.schwabdev.Client')
    def test_get_access_token(self, mock_schwabdev, sample_token_db, mock_logger):
        """Test get_access_token method."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=sample_token_db,
            logger=mock_logger
        )

        token = manager.get_access_token()

        assert token == "test_access_token_12345"

    @patch('token_service.manager.schwabdev.Client')
    def test_get_access_token_no_token(self, mock_schwabdev, temp_db_path, mock_logger):
        """Test get_access_token when no token available."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=temp_db_path,
            logger=mock_logger
        )

        token = manager.get_access_token()

        assert token is None

    @patch('token_service.manager.schwabdev.Client')
    def test_needs_refresh_no_token(self, mock_schwabdev, temp_db_path, mock_logger):
        """Test needs_refresh when no token exists."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=temp_db_path,
            logger=mock_logger
        )

        assert manager.needs_refresh() is True

    @patch('token_service.manager.schwabdev.Client')
    def test_needs_refresh_expired_access_token(self, mock_schwabdev, expired_token_db, mock_logger):
        """Test needs_refresh when access token is expired."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=expired_token_db,
            logger=mock_logger
        )

        assert manager.needs_refresh() is True

    @patch('token_service.manager.schwabdev.Client')
    def test_needs_refresh_valid_token(self, mock_schwabdev, sample_token_db, mock_logger):
        """Test needs_refresh when token is valid."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=sample_token_db,
            logger=mock_logger
        )

        # Token was just created, so it should be valid
        assert manager.needs_refresh() is False

    @patch('token_service.manager.schwabdev.Client')
    def test_needs_refresh_with_threshold(self, mock_schwabdev, sample_token_db, mock_logger):
        """Test needs_refresh with custom threshold."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=sample_token_db,
            logger=mock_logger
        )

        # With very high threshold, should need refresh
        assert manager.needs_refresh(threshold_minutes=60) is True

    @patch('token_service.manager.schwabdev.Client')
    def test_get_status_no_token(self, mock_schwabdev, temp_db_path, mock_logger):
        """Test get_status when no token exists."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=temp_db_path,
            logger=mock_logger
        )

        status = manager.get_status()

        assert status["has_token"] is False
        assert "message" in status

    @patch('token_service.manager.schwabdev.Client')
    def test_get_status_with_token(self, mock_schwabdev, sample_token_db, mock_logger):
        """Test get_status with valid token."""
        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=sample_token_db,
            logger=mock_logger
        )

        status = manager.get_status()

        assert status["has_token"] is True
        assert "access_token" in status
        assert "expires_in" in status
        assert "is_access_token_expired" in status
        assert "is_refresh_token_expired" in status

    @patch('token_service.manager.schwabdev.Client')
    def test_get_status_with_last_refresh(self, mock_schwabdev, sample_token_db, mock_logger):
        """Test get_status includes last_refresh information."""
        mock_client_instance = Mock()
        mock_schwabdev.return_value = mock_client_instance

        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=sample_token_db,
            logger=mock_logger
        )

        # Perform refresh
        manager.refresh_token()

        status = manager.get_status()

        assert "last_refresh" in status
        assert "minutes_since_refresh" in status

    @patch('token_service.manager.schwabdev.Client')
    def test_thread_safety(self, mock_schwabdev, sample_token_db, mock_logger):
        """Test thread safety of token operations."""
        import threading

        manager = CentralizedTokenManager(
            api_key="test_key",
            api_secret="test_secret",
            callback_url="https://test.com",
            tokens_db_path=sample_token_db,
            logger=mock_logger
        )

        results = []

        def get_token():
            token = manager.get_access_token()
            results.append(token)

        # Create multiple threads
        threads = [threading.Thread(target=get_token) for _ in range(10)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # All threads should get the same token
        assert len(results) == 10
        assert all(r == results[0] for r in results)
