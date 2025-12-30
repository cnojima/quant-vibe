"""
Schwab token management API endpoints.

Provides endpoints to view and refresh Schwab API tokens.
Now proxies to the centralized token_service when available.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings

# Import token service client
try:
    from token_service.client import TokenServiceClient
    TOKEN_SERVICE_AVAILABLE = True
except ImportError:
    TOKEN_SERVICE_AVAILABLE = False
    TokenServiceClient = None

router = APIRouter()

# Check for token service URL from environment
USE_TOKEN_SERVICE = os.getenv("USE_TOKEN_SERVICE", "true").lower() == "true"
TOKEN_SERVICE_URL = os.getenv("TOKEN_SERVICE_URL", "http://token_service:8001")


def get_token_from_db() -> Optional[dict]:
    """
    Read token information from schwabdev_tokens.db.

    Returns:
        Dict with token info or None if not found
    """
    settings = get_settings()
    token_db_path = settings.tokens_dir / "schwabdev_tokens.db"

    if not token_db_path.exists():
        return None

    try:
        conn = sqlite3.connect(str(token_db_path))
        cursor = conn.cursor()

        # Check if schwabdev table exists (correct table name)
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='schwabdev'
        """)

        if not cursor.fetchone():
            # Table doesn't exist - schwabdev hasn't been initialized yet
            conn.close()
            return None

        # Query the schwabdev table (actual schema)
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
            access_issued_dt = datetime.fromisoformat(access_token_issued.replace("Z", "+00:00"))
            refresh_issued_dt = datetime.fromisoformat(refresh_token_issued.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            # If parsing fails, return minimal info
            return {
                "has_token": True,
                "message": "Token found but timestamp format is unexpected",
            }

        # Calculate expiration times
        # Access tokens typically expire in expires_in seconds (usually 1800 = 30 minutes)
        # Refresh tokens typically expire in 7 days
        now = datetime.now(timezone.utc)

        if expires_in:
            access_expires_dt = access_issued_dt + timedelta(seconds=expires_in)
        else:
            # Default to 30 minutes if not specified
            access_expires_dt = access_issued_dt + timedelta(minutes=30)

        # Refresh token expires 7 days from issuance (Schwab default)
        refresh_expires_dt = refresh_issued_dt + timedelta(days=7)

        # Calculate age
        access_age_seconds = (now - access_issued_dt).total_seconds()

        return {
            "has_token": True,
            "access_token_issued": access_issued_dt.isoformat(),
            "refresh_token_issued": refresh_issued_dt.isoformat(),
            "access_token_expires_at": access_expires_dt.isoformat(),
            "refresh_token_expires_at": refresh_expires_dt.isoformat(),
            "access_token_expired": access_expires_dt < now,
            "refresh_token_expired": refresh_expires_dt < now,
            "access_token_age_seconds": access_age_seconds,
            "access_token_age_minutes": access_age_seconds / 60,
            "expires_in": expires_in,
            "token_type": token_type,
            "scope": scope,
        }

    except sqlite3.Error as e:
        # SQLite error - log it but don't fail
        print(f"SQLite error reading token database: {e}")
        return None
    except Exception as e:
        # Unexpected error - log it but don't fail
        print(f"Unexpected error reading token database: {e}")
        return None


@router.get("/status")
async def get_token_status(current_user: User = Depends(get_current_user)):
    """
    Get Schwab token status.

    Proxies to token_service if available, otherwise reads from database directly.

    Args:
        current_user: Authenticated user

    Returns:
        Token status information
    """
    # Try to use token service first
    if USE_TOKEN_SERVICE and TOKEN_SERVICE_AVAILABLE:
        try:
            client = TokenServiceClient(TOKEN_SERVICE_URL)
            status = client.get_token_status()
            status["source"] = "token_service"
            return status
        except Exception as e:
            # Fall back to local database
            print(f"Token service unavailable, falling back to database: {e}")

    # Fallback: Read from database directly (legacy mode)
    settings = get_settings()
    token_db_path = settings.tokens_dir / "schwabdev_tokens.db"

    # Check if token database exists
    if not token_db_path.exists():
        return {
            "has_token": False,
            "database_exists": False,
            "source": "local_database",
            "message": "Token database not found. Schwab authentication has not been initialized.",
            "instructions": [
                "1. Run the token service to initialize Schwab OAuth",
                "2. Or run the streaming service to initialize Schwab OAuth",
                "3. Follow the authentication flow to obtain tokens",
                "4. Tokens will be stored in tokens/schwabdev_tokens.db",
            ],
        }

    token_info = get_token_from_db()

    if not token_info:
        return {
            "has_token": False,
            "database_exists": True,
            "source": "local_database",
            "message": "Token database exists but contains no valid tokens.",
            "instructions": [
                "1. Restart the token service to re-authenticate",
                "2. Or restart the streaming service to re-authenticate",
                "3. Or manually delete the database and re-authenticate",
            ],
        }

    token_info["source"] = "local_database"
    return token_info


@router.post("/refresh")
async def refresh_token(current_user: User = Depends(get_current_user)):
    """
    Manually refresh the Schwab token.

    Proxies to token_service if available, otherwise uses schwabdev client directly.

    Args:
        current_user: Authenticated user

    Returns:
        Refresh operation result with updated token status
    """
    # Try to use token service first
    if USE_TOKEN_SERVICE and TOKEN_SERVICE_AVAILABLE:
        try:
            client = TokenServiceClient(TOKEN_SERVICE_URL)
            if client.refresh_token():
                updated_status = client.get_token_status()
                return {
                    "success": True,
                    "message": "Token refreshed successfully via token service",
                    "token_status": updated_status,
                    "source": "token_service",
                }
            else:
                print("Token service refresh returned false, falling back to local refresh")
        except Exception as e:
            # Fall back to local refresh
            print(f"Token service unavailable, falling back to local refresh: {e}")

    # Fallback: Use schwabdev directly (legacy mode)
    settings = get_settings()
    token_db_path = settings.tokens_dir / "schwabdev_tokens.db"

    # Check if token database exists
    if not token_db_path.exists():
        return {
            "success": False,
            "message": "Token database not found. Please authenticate first.",
            "source": "local_database",
        }

    try:
        import schwabdev

        # Get Schwab credentials from environment
        app_key = os.getenv("SCHWAB_API_KEY")
        app_secret = os.getenv("SCHWAB_API_SECRET")

        if not app_key or not app_secret:
            return {
                "success": False,
                "message": "Schwab API credentials not found in environment variables",
                "required_vars": ["SCHWAB_API_KEY", "SCHWAB_API_SECRET"],
                "source": "local_database",
            }

        # Initialize schwabdev client
        # The client will automatically load tokens from the database
        client = schwabdev.Client(
            app_key,
            app_secret,
            os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1"),
            tokens_db=str(token_db_path),
        )

        # Refresh the token
        print(f"[{datetime.now()}] Admin UI: Refreshing Schwab OAuth token...")
        client.update_tokens()
        print(f"[{datetime.now()}] Admin UI: Token refresh successful")

        # Get updated token status
        updated_status = get_token_from_db()

        return {
            "success": True,
            "message": "Token refreshed successfully via local database",
            "token_status": updated_status,
            "source": "local_database",
        }

    except ImportError as e:
        return {
            "success": False,
            "message": f"schwabdev library not available: {str(e)}",
            "note": "Install schwabdev: pip install schwabdev",
            "source": "local_database",
        }
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Token refresh error: {error_trace}")

        return {
            "success": False,
            "message": f"Token refresh failed: {str(e)}",
            "error_type": type(e).__name__,
            "source": "local_database",
        }


@router.get("/oauth-url")
async def get_oauth_url(current_user: User = Depends(get_current_user)):
    """
    Get the Schwab OAuth authorization URL for re-authentication.

    Args:
        current_user: Authenticated user

    Returns:
        OAuth URL to redirect user to
    """
    # TODO: Generate actual OAuth URL using schwabdev
    # This would be similar to the initial auth flow

    settings = get_settings()

    return {
        "oauth_url": "https://api.schwabapi.com/v1/oauth/authorize",
        "message": "OAuth URL generation to be implemented",
        "instructions": [
            "1. Visit the OAuth URL",
            "2. Log in with your Schwab credentials",
            "3. Authorize the application",
            "4. Copy the callback URL with the code parameter",
            "5. Provide the code to the /oauth-callback endpoint",
        ],
    }


@router.post("/oauth-callback")
async def handle_oauth_callback(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """
    Handle OAuth callback with authorization code.

    Args:
        code: Authorization code from Schwab OAuth flow
        current_user: Authenticated user

    Returns:
        Token exchange result
    """
    # TODO: Implement OAuth callback handling
    # This would exchange the code for access/refresh tokens

    return {
        "success": False,
        "message": "OAuth callback handling to be implemented",
        "code_received": bool(code),
    }
