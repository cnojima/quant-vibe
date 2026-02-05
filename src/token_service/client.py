"""HTTP client for accessing the Token Management Service.

Provides methods to interact with the token service, including
lockout status checking to prevent API calls when tokens are invalid.
"""

from typing import Optional, Dict, Any

import requests
from quant_vibe.logging import get_logger


class TokenServiceClient:
    """Client for interacting with the Token Management Service.

    Includes lockout awareness to prevent API calls when the token
    service is in lockout state due to invalid/revoked tokens.
    """

    def __init__(self, base_url: str = "http://localhost:8100", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.logger = get_logger(app_name='token_service')
        self._cached_lockout_status: Optional[bool] = None

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

    def get_access_token(self, check_lockout: bool = True) -> Optional[str]:
        """Get current access token.

        Args:
            check_lockout: If True, check lockout status first and raise
                          TokenLockoutError if service is locked out.

        Returns:
            The access token string, or None if not available.

        Raises:
            TokenLockoutError: If service is in lockout state (when check_lockout=True)
            TokenNotFoundError: If no token exists
            TokenExpiredError: If token is expired
        """
        if check_lockout and self.is_locked_out():
            raise TokenLockoutError("Token service is in lockout state - manual re-authentication required")
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
        """Check if token is valid (exists, not expired, and not locked out)."""
        try:
            # Check lockout first
            if self.is_locked_out():
                return False

            status = self.get_token_status()
            return status.get("has_token", False) and not status.get("is_access_token_expired", True)
        except Exception as e:
            self.logger.error(f"Failed to check token validity: {e}")
            return False

    def is_locked_out(self) -> bool:
        """Check if token service is in lockout state.

        Returns:
            True if service is locked out, False otherwise.
            Returns False if unable to check (service unavailable).
        """
        try:
            response = self._request("GET", "/token/lockout-status")
            response.raise_for_status()
            is_locked = response.json().get("is_locked_out", False)
            self._cached_lockout_status = is_locked
            return is_locked
        except requests.RequestException as e:
            self.logger.warning(f"Failed to check lockout status: {e}")
            # Return cached status if available, otherwise assume not locked out
            if self._cached_lockout_status is not None:
                return self._cached_lockout_status
            return False

    def get_lockout_status(self) -> Dict[str, Any]:
        """Get detailed lockout status.

        Returns:
            Dictionary with lockout state details including:
            - is_locked_out: bool
            - lockout_triggered_at: ISO timestamp or None
            - consecutive_failures: int
            - last_error_type: str or None
            - last_error_message: str or None
            - requires_reauth: bool

        Raises:
            requests.RequestException: If request fails
        """
        try:
            response = self._request("GET", "/token/lockout-status")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Failed to get lockout status: {e}")
            raise

    def clear_lockout(self) -> Dict[str, Any]:
        """Clear lockout state via API.

        Note: This only clears the lockout flag. Tokens must still be
        re-obtained via OAuth flow before service can resume.

        Returns:
            Response from the clear-lockout endpoint

        Raises:
            requests.RequestException: If request fails
        """
        try:
            response = self._request("POST", "/token/clear-lockout")
            response.raise_for_status()
            self._cached_lockout_status = False
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Failed to clear lockout: {e}")
            raise


class TokenNotFoundError(Exception):
    """Raised when no token is found in the token service."""


class TokenExpiredError(Exception):
    """Raised when token is expired."""


class TokenLockoutError(Exception):
    """Raised when token service is in lockout state.

    This indicates that the tokens are fundamentally invalid (expired
    refresh token, revoked access) and manual re-authentication is required.
    """


def get_token(base_url: str = "http://localhost:8100") -> Optional[str]:
    """Convenience function to get access token.

    Returns None if token is not available or service is locked out.
    """
    client = TokenServiceClient(base_url)
    try:
        return client.get_access_token()
    except (TokenNotFoundError, TokenExpiredError, TokenLockoutError):
        return None
