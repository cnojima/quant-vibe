"""Unit tests for TokenServiceClient."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
from token_service.client import (
    TokenServiceClient,
    TokenNotFoundError,
    TokenExpiredError,
    get_token
)


class TestTokenServiceClient:
    """Test cases for TokenServiceClient."""

    def test_initialization_default(self):
        """Test client initialization with defaults."""
        client = TokenServiceClient()

        assert client.base_url == "http://localhost:8001"
        assert client.timeout == 10

    def test_initialization_custom(self):
        """Test client initialization with custom values."""
        logger = Mock()
        client = TokenServiceClient(
            base_url="http://custom:9000",
            timeout=30,
            logger=logger
        )

        assert client.base_url == "http://custom:9000"
        assert client.timeout == 30
        assert client.logger == logger

    def test_initialization_strips_trailing_slash(self):
        """Test that trailing slash is removed from base_url."""
        client = TokenServiceClient(base_url="http://localhost:8001/")

        assert client.base_url == "http://localhost:8001"

    @patch('token_service.client.requests.get')
    def test_health_check_success(self, mock_get):
        """Test successful health check."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "healthy",
            "service": "token_service"
        }
        mock_get.return_value = mock_response

        client = TokenServiceClient()
        result = client.health_check()

        assert result["status"] == "healthy"
        assert result["service"] == "token_service"
        mock_get.assert_called_once_with(
            "http://localhost:8001/health",
            timeout=10
        )

    @patch('token_service.client.requests.get')
    def test_health_check_failure(self, mock_get):
        """Test health check failure."""
        mock_get.side_effect = requests.RequestException("Connection failed")

        client = TokenServiceClient()

        with pytest.raises(requests.RequestException):
            client.health_check()

    @patch('token_service.client.requests.get')
    def test_get_token_status_success(self, mock_get):
        """Test successful token status retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "has_token": True,
            "is_access_token_expired": False,
            "seconds_until_expiration": 1500
        }
        mock_get.return_value = mock_response

        client = TokenServiceClient()
        result = client.get_token_status()

        assert result["has_token"] is True
        assert result["is_access_token_expired"] is False
        mock_get.assert_called_once_with(
            "http://localhost:8001/token/status",
            timeout=10
        )

    @patch('token_service.client.requests.get')
    def test_get_token_status_failure(self, mock_get):
        """Test token status retrieval failure."""
        mock_get.side_effect = requests.RequestException("Request failed")

        client = TokenServiceClient()

        with pytest.raises(requests.RequestException):
            client.get_token_status()

    @patch('token_service.client.requests.get')
    def test_get_access_token_success(self, mock_get):
        """Test successful access token retrieval."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token_12345",
            "token_type": "Bearer",
            "expires_in": 1800
        }
        mock_get.return_value = mock_response

        client = TokenServiceClient()
        token = client.get_access_token()

        assert token == "test_token_12345"
        mock_get.assert_called_once_with(
            "http://localhost:8001/token/access",
            timeout=10
        )

    @patch('token_service.client.requests.get')
    def test_get_access_token_not_found(self, mock_get):
        """Test access token not found (404)."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        client = TokenServiceClient()

        with pytest.raises(TokenNotFoundError, match="No token found"):
            client.get_access_token()

    @patch('token_service.client.requests.get')
    def test_get_access_token_expired(self, mock_get):
        """Test access token expired (401)."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        client = TokenServiceClient()

        with pytest.raises(TokenExpiredError, match="Access token is expired"):
            client.get_access_token()

    @patch('token_service.client.requests.get')
    def test_get_access_token_server_error(self, mock_get):
        """Test access token with server error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.HTTPError("Server error")
        mock_get.return_value = mock_response

        client = TokenServiceClient()

        with pytest.raises(requests.HTTPError):
            client.get_access_token()

    @patch('token_service.client.requests.get')
    def test_get_token_with_metadata_success(self, mock_get):
        """Test successful token retrieval with metadata."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token",
            "token_type": "Bearer",
            "expires_in": 1800,
            "issued_at": "2025-01-01T00:00:00Z",
            "expires_at": "2025-01-01T00:30:00Z"
        }
        mock_get.return_value = mock_response

        client = TokenServiceClient()
        result = client.get_token_with_metadata()

        assert result["access_token"] == "test_token"
        assert result["token_type"] == "Bearer"
        assert result["expires_in"] == 1800

    @patch('token_service.client.requests.get')
    def test_get_token_with_metadata_not_found(self, mock_get):
        """Test token with metadata not found."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        client = TokenServiceClient()

        with pytest.raises(TokenNotFoundError):
            client.get_token_with_metadata()

    @patch('token_service.client.requests.get')
    def test_get_token_with_metadata_expired(self, mock_get):
        """Test token with metadata expired."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        client = TokenServiceClient()

        with pytest.raises(TokenExpiredError):
            client.get_token_with_metadata()

    @patch('token_service.client.requests.post')
    def test_refresh_token_success(self, mock_post):
        """Test successful token refresh."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Token refreshed"
        }
        mock_post.return_value = mock_response

        client = TokenServiceClient()
        result = client.refresh_token()

        assert result is True
        mock_post.assert_called_once_with(
            "http://localhost:8001/token/refresh",
            timeout=10
        )

    @patch('token_service.client.requests.post')
    def test_refresh_token_failure(self, mock_post):
        """Test token refresh failure."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_post.return_value = mock_response

        client = TokenServiceClient()
        result = client.refresh_token()

        assert result is False

    @patch('token_service.client.requests.post')
    def test_refresh_token_exception(self, mock_post):
        """Test token refresh with exception."""
        mock_post.side_effect = requests.RequestException("Connection failed")

        client = TokenServiceClient()
        result = client.refresh_token()

        assert result is False

    @patch('token_service.client.requests.get')
    def test_is_token_valid_true(self, mock_get):
        """Test is_token_valid returns True for valid token."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "has_token": True,
            "is_access_token_expired": False
        }
        mock_get.return_value = mock_response

        client = TokenServiceClient()
        result = client.is_token_valid()

        assert result is True

    @patch('token_service.client.requests.get')
    def test_is_token_valid_false_no_token(self, mock_get):
        """Test is_token_valid returns False when no token."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "has_token": False
        }
        mock_get.return_value = mock_response

        client = TokenServiceClient()
        result = client.is_token_valid()

        assert result is False

    @patch('token_service.client.requests.get')
    def test_is_token_valid_false_expired(self, mock_get):
        """Test is_token_valid returns False when token expired."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "has_token": True,
            "is_access_token_expired": True
        }
        mock_get.return_value = mock_response

        client = TokenServiceClient()
        result = client.is_token_valid()

        assert result is False

    @patch('token_service.client.requests.get')
    def test_is_token_valid_exception(self, mock_get):
        """Test is_token_valid returns False on exception."""
        mock_get.side_effect = requests.RequestException("Error")

        client = TokenServiceClient()
        result = client.is_token_valid()

        assert result is False

    @patch('token_service.client.requests.get')
    def test_custom_base_url(self, mock_get):
        """Test client with custom base URL."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_response

        client = TokenServiceClient(base_url="http://custom-host:9000")
        client.health_check()

        mock_get.assert_called_once_with(
            "http://custom-host:9000/health",
            timeout=10
        )

    @patch('token_service.client.requests.get')
    def test_custom_timeout(self, mock_get):
        """Test client with custom timeout."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_get.return_value = mock_response

        client = TokenServiceClient(timeout=30)
        client.health_check()

        mock_get.assert_called_once_with(
            "http://localhost:8001/health",
            timeout=30
        )


class TestConvenienceFunction:
    """Test cases for get_token convenience function."""

    @patch('token_service.client.TokenServiceClient.get_access_token')
    def test_get_token_success(self, mock_get_access_token):
        """Test get_token convenience function success."""
        mock_get_access_token.return_value = "test_token_12345"

        token = get_token()

        assert token == "test_token_12345"

    @patch('token_service.client.TokenServiceClient.get_access_token')
    def test_get_token_not_found(self, mock_get_access_token):
        """Test get_token returns None when token not found."""
        mock_get_access_token.side_effect = TokenNotFoundError("Not found")

        token = get_token()

        assert token is None

    @patch('token_service.client.TokenServiceClient.get_access_token')
    def test_get_token_expired(self, mock_get_access_token):
        """Test get_token returns None when token expired."""
        mock_get_access_token.side_effect = TokenExpiredError("Expired")

        token = get_token()

        assert token is None

    @patch('token_service.client.TokenServiceClient.get_access_token')
    def test_get_token_custom_url(self, mock_get_access_token):
        """Test get_token with custom base URL."""
        mock_get_access_token.return_value = "test_token"

        token = get_token(base_url="http://custom:9000")

        assert token == "test_token"


class TestExceptions:
    """Test exception classes."""

    def test_token_not_found_error(self):
        """Test TokenNotFoundError exception."""
        error = TokenNotFoundError("Token not found")
        assert str(error) == "Token not found"
        assert isinstance(error, Exception)

    def test_token_expired_error(self):
        """Test TokenExpiredError exception."""
        error = TokenExpiredError("Token expired")
        assert str(error) == "Token expired"
        assert isinstance(error, Exception)
