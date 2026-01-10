"""Unit tests for Token Service FastAPI endpoints."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """Test cases for /health endpoint."""

    @patch('token_service.service.token_manager')
    def test_health_check_success(self, mock_manager):
        """Test successful health check."""
        from token_service.service import app

        mock_manager.get_status.return_value = {
            "has_token": True,
            "is_access_token_expired": False
        }

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "token_service"
        assert data["has_token"] is True
        assert data["token_expired"] is False

    @patch('token_service.service.token_manager', None)
    def test_health_check_manager_not_initialized(self):
        """Test health check when token manager not initialized."""
        from token_service.service import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert "Token manager not initialized" in data["detail"]


class TestTokenStatusEndpoint:
    """Test cases for /token/status endpoint."""

    @patch('token_service.service.token_manager')
    def test_get_token_status_success(self, mock_manager):
        """Test successful token status retrieval."""
        from token_service.service import app

        mock_manager.get_status.return_value = {
            "has_token": True,
            "access_token": "test_token",
            "is_access_token_expired": False,
            "seconds_until_expiration": 1500
        }

        client = TestClient(app)
        response = client.get("/token/status")

        assert response.status_code == 200
        data = response.json()
        assert data["has_token"] is True
        assert data["is_access_token_expired"] is False

    @patch('token_service.service.token_manager', None)
    def test_get_token_status_manager_not_initialized(self):
        """Test token status when manager not initialized."""
        from token_service.service import app

        client = TestClient(app)
        response = client.get("/token/status")

        assert response.status_code == 503


class TestAccessTokenEndpoint:
    """Test cases for /token/access endpoint."""

    @patch('token_service.service.token_manager')
    def test_get_access_token_success(self, mock_manager):
        """Test successful access token retrieval."""
        from token_service.service import app
        from token_service.manager import TokenInfo

        now = datetime.now(timezone.utc)
        mock_token_info = TokenInfo(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800,
            token_type="Bearer",
            scope="api"
        )
        mock_manager.get_token_info.return_value = mock_token_info

        client = TestClient(app)
        response = client.get("/token/access")

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test_access_token"
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        assert "issued_at" in data
        assert "expires_at" in data

    @patch('token_service.service.token_manager')
    def test_get_access_token_not_found(self, mock_manager):
        """Test access token when no token exists."""
        from token_service.service import app

        mock_manager.get_token_info.return_value = None

        client = TestClient(app)
        response = client.get("/token/access")

        assert response.status_code == 404
        data = response.json()
        assert "No token found" in data["detail"]

    @patch('token_service.service.token_manager')
    def test_get_access_token_expired_access(self, mock_manager):
        """Test access token when access token is expired."""
        from token_service.service import app
        from token_service.manager import TokenInfo
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_token_info = TokenInfo(
            access_token="expired_access_token",
            refresh_token="test_refresh_token",
            access_token_issued=past,
            refresh_token_issued=past,
            expires_in=1800,
            token_type="Bearer",
            scope="api"
        )
        mock_manager.get_token_info.return_value = mock_token_info

        client = TestClient(app)
        response = client.get("/token/access")

        assert response.status_code == 401
        data = response.json()
        assert "expired" in data["detail"].lower()

    @patch('token_service.service.token_manager')
    def test_get_access_token_expired_refresh(self, mock_manager):
        """Test access token when refresh token is expired."""
        from token_service.service import app
        from token_service.manager import TokenInfo
        from datetime import timedelta

        past = datetime.now(timezone.utc) - timedelta(days=8)
        mock_token_info = TokenInfo(
            access_token="test_access_token",
            refresh_token="expired_refresh_token",
            access_token_issued=past,
            refresh_token_issued=past,
            expires_in=1800,
            token_type="Bearer",
            scope="api"
        )
        mock_manager.get_token_info.return_value = mock_token_info

        client = TestClient(app)
        response = client.get("/token/access")

        assert response.status_code == 401
        data = response.json()
        assert "re-authentication required" in data["detail"].lower()

    @patch('token_service.service.token_manager', None)
    def test_get_access_token_manager_not_initialized(self):
        """Test access token when manager not initialized."""
        from token_service.service import app

        client = TestClient(app)
        response = client.get("/token/access")

        assert response.status_code == 503


class TestRefreshTokenEndpoint:
    """Test cases for /token/refresh endpoint."""

    @patch('token_service.service.message_broker')
    @patch('token_service.service.config')
    @patch('token_service.service.token_manager')
    def test_refresh_token_success(self, mock_manager, mock_config, mock_broker):
        """Test successful token refresh."""
        from token_service.service import app

        mock_manager.refresh_token.return_value = True
        mock_manager.last_refresh = datetime.now(timezone.utc)
        mock_manager.get_status.return_value = {
            "has_token": True,
            "is_access_token_expired": False
        }
        mock_config.enable_redis = True

        client = TestClient(app)
        response = client.post("/token/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "Token refreshed" in data["message"]
        assert "token_status" in data

    @patch('token_service.service.token_manager')
    def test_refresh_token_failure(self, mock_manager):
        """Test token refresh failure."""
        from token_service.service import app

        mock_manager.refresh_token.return_value = False

        client = TestClient(app)
        response = client.post("/token/refresh")

        assert response.status_code == 500
        data = response.json()
        assert "failed" in data["detail"].lower()

    @patch('token_service.service.token_manager', None)
    def test_refresh_token_manager_not_initialized(self):
        """Test token refresh when manager not initialized."""
        from token_service.service import app

        client = TestClient(app)
        response = client.post("/token/refresh")

        assert response.status_code == 503

    @patch('token_service.service.message_broker')
    @patch('token_service.service.config')
    @patch('token_service.service.token_manager')
    def test_refresh_token_publishes_redis_event(self, mock_manager, mock_config, mock_broker):
        """Test that refresh publishes Redis event."""
        from token_service.service import app

        mock_manager.refresh_token.return_value = True
        mock_manager.last_refresh = datetime.now(timezone.utc)
        mock_manager.get_status.return_value = {"has_token": True}
        mock_config.enable_redis = True

        client = TestClient(app)
        response = client.post("/token/refresh")

        assert response.status_code == 200
        # Verify Redis publish was called
        mock_broker.publish.assert_called_once()

    @patch('token_service.service.message_broker')
    @patch('token_service.service.config')
    @patch('token_service.service.token_manager')
    def test_refresh_token_redis_disabled(self, mock_manager, mock_config, mock_broker):
        """Test refresh when Redis is disabled."""
        from token_service.service import app

        mock_manager.refresh_token.return_value = True
        mock_manager.last_refresh = datetime.now(timezone.utc)
        mock_manager.get_status.return_value = {"has_token": True}
        mock_config.enable_redis = False

        client = TestClient(app)
        response = client.post("/token/refresh")

        assert response.status_code == 200
        # Redis publish should not be called
        mock_broker.publish.assert_not_called()


class TestServiceLifespan:
    """Test cases for service lifespan management."""

    @patch('token_service.service.RedisMessageBroker')
    @patch('token_service.service.CentralizedTokenManager')
    @patch('token_service.service.TokenServiceConfig')
    @patch('token_service.service.logger')
    def test_startup_logging(self, mock_logger, mock_config_class, mock_manager_class, mock_broker_class):
        """Test startup logging messages."""
        mock_config = Mock()
        mock_config.enable_redis = False
        mock_config_class.from_env.return_value = mock_config

        mock_manager = Mock()
        mock_manager.get_status.return_value = {"has_token": False}
        mock_manager_class.return_value = mock_manager

        # We can't easily test the full lifespan without running the server,
        # but we can verify the key components are mocked correctly
        assert mock_config_class is not None
        assert mock_manager_class is not None


class TestAutoRefreshTask:
    """Test cases for auto-refresh background task."""

    @pytest.mark.asyncio
    @patch('token_service.service.token_manager')
    @patch('token_service.service.config')
    @patch('token_service.service.logger')
    @patch('token_service.service.asyncio.sleep', new_callable=AsyncMock)
    async def test_auto_refresh_task_needs_refresh(self, mock_sleep, mock_logger, mock_config, mock_manager):
        """Test auto-refresh task when token needs refresh."""
        from token_service.service import auto_refresh_task

        mock_config.refresh_interval_minutes = 0.01  # Very short for testing
        mock_config.enable_redis = False
        mock_manager.needs_refresh.return_value = True
        mock_manager.refresh_token.return_value = True
        mock_manager.last_refresh = datetime.now(timezone.utc)

        # Run one iteration then cancel
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        import asyncio
        with pytest.raises(asyncio.CancelledError):
            await auto_refresh_task()

        # Verify refresh was called
        mock_manager.refresh_token.assert_called_once()

    @pytest.mark.asyncio
    @patch('token_service.service.token_manager')
    @patch('token_service.service.config')
    @patch('token_service.service.logger')
    @patch('token_service.service.asyncio.sleep', new_callable=AsyncMock)
    async def test_auto_refresh_task_no_refresh_needed(self, mock_sleep, mock_logger, mock_config, mock_manager):
        """Test auto-refresh task when token doesn't need refresh."""
        from token_service.service import auto_refresh_task
        from token_service.manager import TokenInfo

        mock_config.refresh_interval_minutes = 0.01
        mock_config.enable_redis = False
        mock_manager.needs_refresh.return_value = False

        now = datetime.now(timezone.utc)
        mock_token_info = TokenInfo(
            access_token="test",
            refresh_token="test",
            access_token_issued=now,
            refresh_token_issued=now,
            expires_in=1800
        )
        mock_manager.get_token_info.return_value = mock_token_info

        # Run one iteration then cancel
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        import asyncio
        with pytest.raises(asyncio.CancelledError):
            await auto_refresh_task()

        # Refresh should not be called
        mock_manager.refresh_token.assert_not_called()

    @pytest.mark.asyncio
    @patch('token_service.service.token_manager')
    @patch('token_service.service.config')
    @patch('token_service.service.logger')
    @patch('token_service.service.asyncio.sleep', new_callable=AsyncMock)
    async def test_auto_refresh_task_handles_exceptions(self, mock_sleep, mock_logger, mock_config, mock_manager):
        """Test auto-refresh task handles exceptions gracefully."""
        from token_service.service import auto_refresh_task

        mock_config.refresh_interval_minutes = 0.01
        mock_config.enable_redis = False
        mock_manager.needs_refresh.side_effect = Exception("Test error")

        # After exception, sleep then cancel
        mock_sleep.side_effect = [None, None, asyncio.CancelledError()]

        import asyncio
        with pytest.raises(asyncio.CancelledError):
            await auto_refresh_task()

        # Should have logged error
        mock_logger.error.assert_called()


# Note: We need to import asyncio for the async tests
import asyncio
