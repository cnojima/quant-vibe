"""Centralized OAuth token manager for Schwab API.

Includes lockout protection to prevent excessive API calls when tokens
are fundamentally invalid (expired refresh token, revoked access).
"""

import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import schwabdev
from quant_vibe.logging import get_logger
from quant_vibe.utils.timestamp_utils import now_utc
from token_service.errors import TokenLockoutError, classify_error, is_non_retryable


class TokenInfo:
    """Token information with metadata."""

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        access_token_issued: datetime,
        refresh_token_issued: datetime,
        expires_in: int,
        token_type: str = "Bearer",
        scope: str = "",
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.access_token_issued = access_token_issued
        self.refresh_token_issued = refresh_token_issued
        self.expires_in = expires_in
        self.token_type = token_type
        self.scope = scope

    @property
    def access_token_expires_at(self) -> datetime:
        """Calculate access token expiration time."""
        return self.access_token_issued + timedelta(seconds=self.expires_in)

    @property
    def refresh_token_expires_at(self) -> datetime:
        """Calculate refresh token expiration time (7 days from issuance)."""
        return self.refresh_token_issued + timedelta(days=7)

    @property
    def is_access_token_expired(self) -> bool:
        return now_utc() >= self.access_token_expires_at

    @property
    def is_refresh_token_expired(self) -> bool:
        return now_utc() >= self.refresh_token_expires_at

    @property
    def access_token_age_seconds(self) -> float:
        return (now_utc() - self.access_token_issued).total_seconds()

    @property
    def seconds_until_expiration(self) -> float:
        return (self.access_token_expires_at - now_utc()).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "access_token": self.access_token,
            "access_token_issued": self.access_token_issued.isoformat(),
            "access_token_expires_at": self.access_token_expires_at.isoformat(),
            "refresh_token_issued": self.refresh_token_issued.isoformat(),
            "refresh_token_expires_at": self.refresh_token_expires_at.isoformat(),
            "is_access_token_expired": self.is_access_token_expired,
            "is_refresh_token_expired": self.is_refresh_token_expired,
            "access_token_age_seconds": self.access_token_age_seconds,
            "seconds_until_expiration": self.seconds_until_expiration,
            "expires_in": self.expires_in,
            "token_type": self.token_type,
            "scope": self.scope,
        }


class CentralizedTokenManager:
    """Centralized token manager for Schwab API OAuth tokens.

    Includes lockout protection to prevent excessive API calls when tokens
    are fundamentally invalid. Lockout triggers on:
    - Consecutive refresh failures exceeding threshold
    - Non-retryable errors (invalid/revoked tokens)
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        callback_url: str,
        tokens_db_path: str,
        max_consecutive_failures: int = 5,
        lockout_on_non_retryable: bool = True,
        refresh_max_retries: int = 3,
        refresh_backoff_base: float = 2.0,
        refresh_max_backoff: float = 30.0,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.callback_url = callback_url
        self.tokens_db_path = tokens_db_path
        self.logger = get_logger(app_name='token_service')
        self._lock = threading.Lock()
        self.client = None
        self._client_init_error = None
        self.last_refresh: Optional[datetime] = None

        # Lockout configuration
        self._max_consecutive_failures = max_consecutive_failures
        self._lockout_on_non_retryable = lockout_on_non_retryable

        # Retry configuration
        self._refresh_max_retries = refresh_max_retries
        self._refresh_backoff_base = refresh_backoff_base
        self._refresh_max_backoff = refresh_max_backoff

        # Lockout state
        self._consecutive_failures: int = 0
        self._lockout_triggered: bool = False
        self._lockout_triggered_at: Optional[datetime] = None
        self._last_error_type: Optional[str] = None
        self._last_error_message: Optional[str] = None

        # Ensure token directory exists
        Path(tokens_db_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize schwabdev client
        self._initialize_client()

    def _initialize_client(self):
        """Initialize schwabdev client."""
        self.logger.info("Initializing schwabdev client...")

        if not Path(self.tokens_db_path).exists():
            self.logger.warning(
                f"Tokens database not found at: {self.tokens_db_path}\n"
                "OAuth authentication required. Use Admin UI or run:\n"
                "  python scripts/authorize_schwab.py"
            )
            self._client_init_error = "no_token_db"
            return

        try:
            self.client = schwabdev.Client(
                app_key=self.api_key,
                app_secret=self.api_secret,
                callback_url=self.callback_url,
                tokens_db=self.tokens_db_path,
            )
            self.logger.info("Schwabdev client initialized successfully")
        except EOFError:
            self.logger.warning(
                "Interactive OAuth required - refresh token expired\n"
                "Use Admin UI to re-authenticate or run:\n"
                "  python scripts/authorize_schwab.py"
            )
            self._client_init_error = "refresh_token_expired"
        except Exception as e:
            self.logger.warning(f"Failed to initialize schwabdev client: {e}")
            self._client_init_error = str(e)

    def get_token_info(self) -> Optional[TokenInfo]:
        """Get current token information from database."""
        with self._lock:
            return self._read_token_from_db()

    def _read_token_from_db(self) -> Optional[TokenInfo]:
        """Read token from schwabdev database (not thread-safe)."""
        if not Path(self.tokens_db_path).exists():
            self.logger.warning(f"Token database not found: {self.tokens_db_path}")
            return None

        try:
            with sqlite3.connect(self.tokens_db_path) as conn:
                cursor = conn.cursor()

                # Check if schwabdev table exists
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schwabdev'"
                )
                if not cursor.fetchone():
                    self.logger.warning("Token database exists but schwabdev table not found")
                    return None

                # Query the schwabdev table
                cursor.execute("""
                    SELECT access_token_issued, refresh_token_issued,
                           access_token, refresh_token, id_token,
                           expires_in, token_type, scope
                    FROM schwabdev
                    ORDER BY access_token_issued DESC
                    LIMIT 1
                """)

                row = cursor.fetchone()
                if not row:
                    self.logger.warning("No tokens found in database")
                    return None

                return self._parse_token_row(row)

        except sqlite3.Error as e:
            self.logger.error(f"SQLite error reading token database: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error reading token database: {e}")

        return None

    def _parse_token_row(self, row) -> Optional[TokenInfo]:
        """Parse database row into TokenInfo."""
        (
            access_token_issued,
            refresh_token_issued,
            access_token,
            refresh_token,
            id_token,
            expires_in,
            token_type,
            scope,
        ) = row

        try:
            access_issued_dt = datetime.fromisoformat(
                access_token_issued.replace("Z", "+00:00")
            )
            refresh_issued_dt = datetime.fromisoformat(
                refresh_token_issued.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError) as e:
            self.logger.error(f"Failed to parse token timestamps: {e}")
            return None

        return TokenInfo(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_issued=access_issued_dt,
            refresh_token_issued=refresh_issued_dt,
            expires_in=expires_in or 1800,
            token_type=token_type or "Bearer",
            scope=scope or "",
        )

    def refresh_token(self) -> bool:
        """Refresh OAuth token with exponential backoff and lockout protection.

        Implements retry logic with exponential backoff for transient errors.
        Triggers lockout on non-retryable errors or consecutive failures.

        Returns:
            True if refresh succeeded, False otherwise

        Raises:
            TokenLockoutError: If service is in lockout state
        """
        # Check lockout state first (outside lock to allow status checks)
        if self._lockout_triggered:
            self.logger.error(
                f"Token refresh blocked - service is in LOCKOUT state "
                f"(triggered at {self._lockout_triggered_at})"
            )
            raise TokenLockoutError(
                f"Service is in lockout state since {self._lockout_triggered_at}. "
                "Manual re-authentication required."
            )

        with self._lock:
            if not self.client:
                self.logger.error(
                    f"Cannot refresh token - schwabdev client not initialized\n"
                    f"Initialization error: {self._client_init_error}\n"
                    "Please complete OAuth authentication first"
                )
                return False

            last_exception = None
            attempts_made = 0

            for attempt in range(self._refresh_max_retries):
                attempts_made = attempt + 1
                try:
                    self.logger.info(
                        f"Refreshing Schwab OAuth token "
                        f"(attempt {attempts_made}/{self._refresh_max_retries})..."
                    )
                    self.client.update_tokens()

                    # Success - reset failure tracking
                    self._consecutive_failures = 0
                    self._last_error_type = None
                    self._last_error_message = None
                    self.last_refresh = now_utc()

                    self.logger.info("Token refresh successful")
                    return True

                except Exception as e:
                    last_exception = e
                    error_type = classify_error(e)
                    self._last_error_type = error_type
                    self._last_error_message = str(e)

                    self.logger.warning(
                        f"Token refresh attempt {attempts_made} failed: {e} "
                        f"(classified as {error_type})"
                    )

                    # Non-retryable errors should not retry
                    if error_type == "non_retryable":
                        self.logger.error(
                            f"Non-retryable error detected - stopping retry attempts: {e}"
                        )
                        break

                    # Calculate backoff for retryable errors (skip on last attempt)
                    if attempt < self._refresh_max_retries - 1:
                        backoff = min(
                            self._refresh_backoff_base ** attempt,
                            self._refresh_max_backoff
                        )
                        self.logger.info(f"Waiting {backoff:.1f}s before retry...")
                        time.sleep(backoff)

            # All retries exhausted or non-retryable error encountered
            self._consecutive_failures += 1
            self.logger.error(
                f"Token refresh failed after {attempts_made} attempt(s). "
                f"Consecutive failures: {self._consecutive_failures}/{self._max_consecutive_failures}"
            )

            # Check if lockout should be triggered
            self._check_and_trigger_lockout()

            return False

    def _check_and_trigger_lockout(self) -> None:
        """Check conditions and trigger lockout if necessary."""
        should_lockout = False
        reason = ""

        # Lockout on consecutive failures threshold
        if self._consecutive_failures >= self._max_consecutive_failures:
            should_lockout = True
            reason = (
                f"Exceeded {self._max_consecutive_failures} consecutive failures "
                f"(last error: {self._last_error_message})"
            )

        # Immediate lockout on non-retryable errors
        if self._lockout_on_non_retryable and self._last_error_type == "non_retryable":
            should_lockout = True
            reason = f"Non-retryable error: {self._last_error_message}"

        if should_lockout:
            self._trigger_lockout(reason)

    def _trigger_lockout(self, reason: str) -> None:
        """Trigger lockout state and cleanup.

        This deletes the tokens database and invalidates the client to
        prevent any further API calls with invalid tokens.

        Args:
            reason: Human-readable reason for the lockout
        """
        self.logger.critical(f"LOCKOUT TRIGGERED: {reason}")

        self._lockout_triggered = True
        self._lockout_triggered_at = now_utc()

        # Delete tokens database to prevent stale token usage
        self._delete_tokens_db()

        # Invalidate the schwabdev client
        self.client = None
        self._client_init_error = f"lockout: {reason}"

        self.logger.critical(
            "Token service is now in LOCKOUT state. "
            "Manual re-authentication required via Admin UI or scripts/authorize_schwab.py"
        )

    def _delete_tokens_db(self) -> None:
        """Delete the tokens database file to prevent stale token usage."""
        try:
            tokens_path = Path(self.tokens_db_path)
            if tokens_path.exists():
                tokens_path.unlink()
                self.logger.info(f"Deleted tokens database: {self.tokens_db_path}")
            else:
                self.logger.info("Tokens database already deleted or does not exist")
        except Exception as e:
            self.logger.error(f"Failed to delete tokens database: {e}")

    def is_locked_out(self) -> bool:
        """Check if service is in lockout state.

        Returns:
            True if service is locked out, False otherwise
        """
        return self._lockout_triggered

    def clear_lockout(self) -> None:
        """Clear lockout state for manual recovery.

        Note: This only clears the lockout flag. Tokens must still be
        re-obtained via OAuth flow before service can resume normal operation.
        """
        self.logger.info("Clearing lockout state...")
        self._lockout_triggered = False
        self._lockout_triggered_at = None
        self._consecutive_failures = 0
        self._last_error_type = None
        self._last_error_message = None
        self._client_init_error = None

        # Attempt to reinitialize client (will fail if tokens db doesn't exist)
        self._initialize_client()

        self.logger.info(
            "Lockout cleared. Please complete OAuth re-authentication "
            "before service can resume normal operation."
        )

    def get_access_token(self) -> Optional[str]:
        """Get current access token."""
        token_info = self.get_token_info()
        return token_info.access_token if token_info else None

    def needs_refresh(self, threshold_minutes: int = 5) -> bool:
        """Check if token needs refresh."""
        token_info = self.get_token_info()

        if not token_info:
            self.logger.warning("No token found - refresh needed")
            return True

        if token_info.is_access_token_expired:
            self.logger.warning("Access token is expired - refresh needed")
            return True

        if token_info.is_refresh_token_expired:
            self.logger.error("Refresh token is expired - re-authentication required!")
            return True

        minutes_remaining = token_info.seconds_until_expiration / 60.0
        if minutes_remaining <= threshold_minutes:
            self.logger.info(f"Token expires in {minutes_remaining:.1f} minutes - refresh needed")
            return True

        return False

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive token status including lockout state."""
        token_info = self.get_token_info()

        if not token_info:
            status = {"has_token": False, "message": "No token found in database"}
            if self._client_init_error:
                status["client_init_error"] = self._client_init_error
                status["requires_oauth"] = True
        else:
            status = {"has_token": True, **token_info.to_dict()}

        if self.last_refresh:
            status["last_refresh"] = self.last_refresh.isoformat()
            status["minutes_since_refresh"] = (now_utc() - self.last_refresh).total_seconds() / 60.0

        if self._client_init_error:
            status["client_init_error"] = self._client_init_error

        # Add lockout information
        status["is_locked_out"] = self._lockout_triggered
        if self._lockout_triggered:
            status["lockout_triggered_at"] = (
                self._lockout_triggered_at.isoformat()
                if self._lockout_triggered_at else None
            )
        status["consecutive_failures"] = self._consecutive_failures
        status["last_error_type"] = self._last_error_type
        status["last_error_message"] = self._last_error_message

        return status

    def get_lockout_status(self) -> Dict[str, Any]:
        """Get detailed lockout status.

        Returns:
            Dictionary with lockout state details
        """
        return {
            "is_locked_out": self._lockout_triggered,
            "lockout_triggered_at": (
                self._lockout_triggered_at.isoformat()
                if self._lockout_triggered_at else None
            ),
            "consecutive_failures": self._consecutive_failures,
            "max_consecutive_failures": self._max_consecutive_failures,
            "last_error_type": self._last_error_type,
            "last_error_message": self._last_error_message,
            "lockout_on_non_retryable": self._lockout_on_non_retryable,
            "requires_reauth": self._lockout_triggered,
        }
