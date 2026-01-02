"""HTTP client for accessing the Token Management Service."""

from typing import Optional, Dict, Any
import logging

import requests


class TokenServiceClient:
    """Client for interacting with the Token Management Service.

    This client provides a simple interface for other services to:
    - Get current access token
    - Check token status
    - Trigger manual token refresh

    Usage:
        >>> client = TokenServiceClient("http://localhost:8100")
        >>> token = client.get_access_token()
        >>> print(token)
        "eyJhbGc..."
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8100",
        timeout: int = 10,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize token service client.

        Args:
            base_url: Base URL of token service (e.g., "http://localhost:8100")
            timeout: Request timeout in seconds
            logger: Logger instance (creates new one if not provided)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

    def health_check(self) -> Dict[str, Any]:
        """Check if token service is healthy.

        Returns:
            Health status dictionary

        Raises:
            requests.RequestException: If request fails
        """
        try:
            response = requests.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Health check failed: {e}")
            raise

    def get_token_status(self) -> Dict[str, Any]:
        """Get comprehensive token status.

        Returns:
            Token status dictionary with expiration info, age, etc.

        Raises:
            requests.RequestException: If request fails
        """
        try:
            response = requests.get(
                f"{self.base_url}/token/status",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Failed to get token status: {e}")
            raise

    def get_access_token(self) -> Optional[str]:
        """Get current access token.

        Returns:
            Access token string or None if not available

        Raises:
            requests.RequestException: If request fails
            TokenExpiredError: If token is expired
            TokenNotFoundError: If no token available
        """
        try:
            response = requests.get(
                f"{self.base_url}/token/access",
                timeout=self.timeout
            )

            if response.status_code == 404:
                self.logger.error("No token found in token service")
                raise TokenNotFoundError("No token found in database")

            if response.status_code == 401:
                self.logger.error("Token is expired")
                raise TokenExpiredError("Access token is expired")

            response.raise_for_status()
            data = response.json()
            return data.get("access_token")

        except requests.RequestException as e:
            self.logger.error(f"Failed to get access token: {e}")
            raise

    def get_token_with_metadata(self) -> Dict[str, Any]:
        """Get access token with metadata.

        Returns:
            Dictionary with access_token, token_type, expires_in, etc.

        Raises:
            requests.RequestException: If request fails
            TokenExpiredError: If token is expired
            TokenNotFoundError: If no token available
        """
        try:
            response = requests.get(
                f"{self.base_url}/token/access",
                timeout=self.timeout
            )

            if response.status_code == 404:
                raise TokenNotFoundError("No token found in database")

            if response.status_code == 401:
                raise TokenExpiredError("Access token is expired")

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            self.logger.error(f"Failed to get token with metadata: {e}")
            raise

    def refresh_token(self) -> bool:
        """Manually trigger token refresh.

        Returns:
            True if refresh successful, False otherwise

        Raises:
            requests.RequestException: If request fails
        """
        try:
            response = requests.post(
                f"{self.base_url}/token/refresh",
                timeout=self.timeout
            )

            if response.status_code == 200:
                self.logger.info("Token refresh successful")
                return True
            else:
                self.logger.error(f"Token refresh failed: {response.text}")
                return False

        except requests.RequestException as e:
            self.logger.error(f"Failed to refresh token: {e}")
            return False

    def is_token_valid(self) -> bool:
        """Check if token is valid (exists and not expired).

        Returns:
            True if token is valid, False otherwise
        """
        try:
            status = self.get_token_status()
            return (
                status.get("has_token", False)
                and not status.get("is_access_token_expired", True)
            )
        except Exception as e:
            self.logger.error(f"Failed to check token validity: {e}")
            return False


class TokenNotFoundError(Exception):
    """Raised when no token is found in the token service."""
    pass


class TokenExpiredError(Exception):
    """Raised when token is expired."""
    pass


# Convenience function
def get_token(base_url: str = "http://localhost:8100") -> Optional[str]:
    """Convenience function to get access token.

    Args:
        base_url: Base URL of token service

    Returns:
        Access token string or None if not available

    Example:
        >>> from token_service.client import get_token
        >>> token = get_token()
        >>> print(token)
    """
    client = TokenServiceClient(base_url)
    try:
        return client.get_access_token()
    except (TokenNotFoundError, TokenExpiredError):
        return None
