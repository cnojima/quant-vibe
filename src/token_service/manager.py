"""Centralized OAuth token manager for Schwab API."""

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import logging

import schwabdev


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
        """Initialize token info.

        Args:
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            access_token_issued: When access token was issued
            refresh_token_issued: When refresh token was issued
            expires_in: Access token expiration time in seconds
            token_type: Token type (usually "Bearer")
            scope: Token scope
        """
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
        """Check if access token is expired."""
        return datetime.now(timezone.utc) >= self.access_token_expires_at

    @property
    def is_refresh_token_expired(self) -> bool:
        """Check if refresh token is expired."""
        return datetime.now(timezone.utc) >= self.refresh_token_expires_at

    @property
    def access_token_age_seconds(self) -> float:
        """Get access token age in seconds."""
        return (datetime.now(timezone.utc) - self.access_token_issued).total_seconds()

    @property
    def seconds_until_expiration(self) -> float:
        """Get seconds until access token expires."""
        return (self.access_token_expires_at - datetime.now(timezone.utc)).total_seconds()

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

    Manages token lifecycle:
    - Token storage and retrieval
    - Automatic token refresh
    - Token expiry monitoring
    - Thread-safe access

    Thread Safety:
        All public methods are thread-safe using a lock to protect
        concurrent access to the schwabdev client and token state.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        callback_url: str,
        tokens_db_path: str,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize centralized token manager.

        Args:
            api_key: Schwab API key
            api_secret: Schwab app secret
            callback_url: OAuth callback URL
            tokens_db_path: Path to schwabdev tokens database
            logger: Logger instance (creates new one if not provided)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.callback_url = callback_url
        self.tokens_db_path = tokens_db_path
        self.logger = logger or logging.getLogger(__name__)

        # Ensure token directory exists
        Path(tokens_db_path).parent.mkdir(parents=True, exist_ok=True)

        # Thread safety
        self._lock = threading.Lock()

        # Initialize schwabdev client
        self.logger.info("Initializing schwabdev client...")
        try:
            self.client = schwabdev.Client(
                app_key=api_key,
                app_secret=api_secret,
                callback_url=callback_url,
                tokens_db=tokens_db_path,
            )
            self.logger.info("✓ Schwabdev client initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize schwabdev client: {e}")
            raise

        # Last refresh time
        self.last_refresh: Optional[datetime] = None

    def get_token_info(self) -> Optional[TokenInfo]:
        """Get current token information from database.

        Returns:
            TokenInfo object or None if no token found

        Thread Safety:
            This method is thread-safe.
        """
        with self._lock:
            return self._read_token_from_db()

    def _read_token_from_db(self) -> Optional[TokenInfo]:
        """Read token from schwabdev database.

        Returns:
            TokenInfo object or None if no token found

        Note:
            This method is NOT thread-safe. Use get_token_info() instead.
        """
        if not Path(self.tokens_db_path).exists():
            self.logger.warning(f"Token database not found: {self.tokens_db_path}")
            return None

        try:
            conn = sqlite3.connect(self.tokens_db_path)
            cursor = conn.cursor()

            # Check if schwabdev table exists
            cursor.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='schwabdev'
            """)

            if not cursor.fetchone():
                conn.close()
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
            conn.close()

            if not row:
                self.logger.warning("No tokens found in database")
                return None

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

            # Parse timestamps (schwabdev stores as ISO format strings)
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
                expires_in=expires_in or 1800,  # Default 30 minutes
                token_type=token_type or "Bearer",
                scope=scope or "",
            )

        except sqlite3.Error as e:
            self.logger.error(f"SQLite error reading token database: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error reading token database: {e}")
            return None

    def refresh_token(self) -> bool:
        """Refresh OAuth token using schwabdev client.

        Returns:
            True if refresh successful, False otherwise

        Thread Safety:
            This method is thread-safe.
        """
        with self._lock:
            try:
                self.logger.info("Refreshing Schwab OAuth token...")
                self.client.update_tokens()
                self.last_refresh = datetime.now(timezone.utc)
                self.logger.info("✓ Token refresh successful")
                return True

            except Exception as e:
                self.logger.error(f"Token refresh failed: {e}", exc_info=True)
                return False

    def get_access_token(self) -> Optional[str]:
        """Get current access token.

        Returns:
            Access token string or None if not available

        Thread Safety:
            This method is thread-safe.
        """
        token_info = self.get_token_info()
        if not token_info:
            return None
        return token_info.access_token

    def needs_refresh(self, threshold_minutes: int = 5) -> bool:
        """Check if token needs refresh.

        Args:
            threshold_minutes: Refresh if token expires within this many minutes

        Returns:
            True if token should be refreshed

        Thread Safety:
            This method is thread-safe.
        """
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

        # Check if token expires soon
        seconds_remaining = token_info.seconds_until_expiration
        minutes_remaining = seconds_remaining / 60.0

        if minutes_remaining <= threshold_minutes:
            self.logger.info(
                f"Token expires in {minutes_remaining:.1f} minutes - refresh needed"
            )
            return True

        return False

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive token status.

        Returns:
            Dictionary with token status information

        Thread Safety:
            This method is thread-safe.
        """
        token_info = self.get_token_info()

        if not token_info:
            return {
                "has_token": False,
                "message": "No token found in database",
            }

        status = {
            "has_token": True,
            **token_info.to_dict(),
        }

        if self.last_refresh:
            status["last_refresh"] = self.last_refresh.isoformat()
            status["minutes_since_refresh"] = (
                datetime.now(timezone.utc) - self.last_refresh
            ).total_seconds() / 60.0

        return status
