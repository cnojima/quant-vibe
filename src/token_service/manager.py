"""Centralized OAuth token manager for Schwab API."""

import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

import schwabdev
from quant_vibe.logging import get_logger
from quant_vibe.utils.timestamp_utils import now_utc


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
    """Centralized token manager for Schwab API OAuth tokens."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        callback_url: str,
        tokens_db_path: str
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
        """Refresh OAuth token using schwabdev client."""
        with self._lock:
            if not self.client:
                self.logger.error(
                    f"Cannot refresh token - schwabdev client not initialized\n"
                    f"Initialization error: {self._client_init_error}\n"
                    "Please complete OAuth authentication first"
                )
                return False

            try:
                self.logger.info("Refreshing Schwab OAuth token...")
                self.client.update_tokens()
                self.last_refresh = now_utc()
                self.logger.info("Token refresh successful")
                return True
            except Exception as e:
                self.logger.error(f"Token refresh failed: {e}", exc_info=True)
                return False

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
        """Get comprehensive token status."""
        token_info = self.get_token_info()

        if not token_info:
            status = {"has_token": False, "message": "No token found in database"}
            if self._client_init_error:
                status["client_init_error"] = self._client_init_error
                status["requires_oauth"] = True
            return status

        status = {"has_token": True, **token_info.to_dict()}

        if self.last_refresh:
            status["last_refresh"] = self.last_refresh.isoformat()
            status["minutes_since_refresh"] = (now_utc() - self.last_refresh).total_seconds() / 60.0

        if self._client_init_error:
            status["client_init_error"] = self._client_init_error

        return status
