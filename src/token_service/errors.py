"""Token service error classification and custom exceptions.

Provides error classification to distinguish between retryable and non-retryable
errors, enabling proper lockout behavior when tokens are fundamentally invalid.
"""

from typing import Tuple


class TokenLockoutError(Exception):
    """Raised when token service is in lockout state.

    Lockout occurs when:
    - Consecutive refresh failures exceed threshold, OR
    - A non-retryable error (invalid token, revoked access) is detected

    Recovery requires manual re-authentication via OAuth flow.
    """
    pass


class TokenRefreshError(Exception):
    """Base exception for token refresh errors."""
    pass


class RetryableTokenError(TokenRefreshError):
    """Error that may succeed on retry (network issues, rate limits)."""
    pass


class NonRetryableTokenError(TokenRefreshError):
    """Error that will not succeed on retry (invalid/revoked token)."""
    pass


# Error patterns for classification
# Checked against lowercase error message strings

NON_RETRYABLE_PATTERNS: Tuple[str, ...] = (
    # HTTP status codes indicating permanent failure
    "400",  # Bad Request - invalid refresh token
    "401",  # Unauthorized - token revoked or invalid
    "403",  # Forbidden - access denied

    # OAuth error codes from Schwab
    "invalid_grant",
    "invalid_token",
    "invalid_request",
    "invalid_client",
    "unauthorized_client",

    # Descriptive error messages
    "expired",
    "revoked",
    "invalid refresh token",
    "refresh token expired",
    "access denied",
    "authentication required",
    "eoferror",  # schwabdev raises this when refresh token is expired
)

RETRYABLE_PATTERNS: Tuple[str, ...] = (
    # HTTP status codes for transient errors
    "429",  # Too Many Requests - rate limited
    "500",  # Internal Server Error
    "502",  # Bad Gateway
    "503",  # Service Unavailable
    "504",  # Gateway Timeout

    # Network/connection issues
    "connection",
    "timeout",
    "timed out",
    "network",
    "temporary",
    "retry",
    "unavailable",
    "reset by peer",
    "broken pipe",
    "ssl",
    "certificate",
)


def classify_error(exception: Exception) -> str:
    """Classify an exception as retryable or non-retryable.

    Since the schwabdev library swallows detailed HTTP status codes,
    we classify errors by pattern matching on the exception message.

    Args:
        exception: The exception to classify

    Returns:
        "non_retryable" if the error indicates a permanent failure
        "retryable" if the error might succeed on retry
    """
    # Get the full exception chain as lowercase string
    error_str = str(exception).lower()
    exception_type = type(exception).__name__.lower()

    # Combine message and type for matching
    full_error = f"{exception_type}: {error_str}"

    # Check non-retryable patterns first (more specific)
    for pattern in NON_RETRYABLE_PATTERNS:
        if pattern in full_error:
            return "non_retryable"

    # Check retryable patterns
    for pattern in RETRYABLE_PATTERNS:
        if pattern in full_error:
            return "retryable"

    # Default to retryable (safer - allows recovery from unknown errors)
    # but log that we're making an assumption
    return "retryable"


def is_non_retryable(exception: Exception) -> bool:
    """Check if an exception is non-retryable.

    Convenience function for quick checks.

    Args:
        exception: The exception to check

    Returns:
        True if the error is non-retryable (lockout should trigger)
    """
    return classify_error(exception) == "non_retryable"
