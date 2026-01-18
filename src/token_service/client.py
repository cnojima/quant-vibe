"""HTTP client for accessing the Token Management Service."""

from typing import Optional, Dict, Any

import requests
from quant_vibe.logging import get_logger


class TokenServiceClient:
    """Client for interacting with the Token Management Service."""

    def __init__(self, base_url: str = "http://localhost:8100", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.logger = get_logger(app_name='token_service')

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request to token service."""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)
        return requests.request(method, url, **kwargs)

    def health_check(self) -> Dict[str, Any]:
        """Check if token service is healthy."""
        try:
            response = self._request("GET", "/health")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Health check failed: {e}")
            raise

    def get_token_status(self) -> Dict[str, Any]:
        """Get comprehensive token status."""
        try:
            response = self._request("GET", "/token/status")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Failed to get token status: {e}")
            raise

    def get_access_token(self) -> Optional[str]:
        """Get current access token."""
        return self._get_token_response().get("access_token")

    def get_token_with_metadata(self) -> Dict[str, Any]:
        """Get access token with metadata."""
        return self._get_token_response()

    def _get_token_response(self) -> Dict[str, Any]:
        """Get token response from service."""
        try:
            response = self._request("GET", "/token/access")

            if response.status_code == 404:
                self.logger.error("No token found in token service")
                raise TokenNotFoundError("No token found in database")

            if response.status_code == 401:
                self.logger.error("Token is expired")
                raise TokenExpiredError("Access token is expired")

            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Failed to get access token: {e}")
            raise

    def refresh_token(self) -> bool:
        """Manually trigger token refresh."""
        try:
            response = self._request("POST", "/token/refresh")
            if response.status_code == 200:
                self.logger.info("Token refresh successful")
                return True

            self.logger.error(f"Token refresh failed: {response.text}")
            return False
        except requests.RequestException as e:
            self.logger.error(f"Failed to refresh token: {e}")
            return False

    def is_token_valid(self) -> bool:
        """Check if token is valid (exists and not expired)."""
        try:
            status = self.get_token_status()
            return status.get("has_token", False) and not status.get("is_access_token_expired", True)
        except Exception as e:
            self.logger.error(f"Failed to check token validity: {e}")
            return False


class TokenNotFoundError(Exception):
    """Raised when no token is found in the token service."""


class TokenExpiredError(Exception):
    """Raised when token is expired."""


def get_token(base_url: str = "http://localhost:8100") -> Optional[str]:
    """Convenience function to get access token."""
    client = TokenServiceClient(base_url)
    try:
        return client.get_access_token()
    except (TokenNotFoundError, TokenExpiredError):
        return None
