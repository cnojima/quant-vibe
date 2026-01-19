"""
Schwab token management API endpoints.

Provides endpoints to view and refresh Schwab API tokens.
Now proxies to the centralized token_service when available.
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings
from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc

logger = get_logger(__name__)

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
TOKEN_SERVICE_URL = os.getenv("TOKEN_SERVICE_URL", "http://token_service:8100")


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
        logger.error(f"SQLite error reading token database: {e}")
        return None
    except Exception as e:
        # Unexpected error - log it but don't fail
        logger.error(f"Unexpected error reading token database: {e}")
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
            logger.warning(f"Token service unavailable, falling back to database: {e}")

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
                # Token service refresh failed - return error immediately
                error_status = client.get_token_status()
                return {
                    "success": False,
                    "message": "Token refresh failed via token service. Check token_service logs for details.",
                    "token_status": error_status,
                    "source": "token_service",
                    "hint": "Refresh token may be expired. Re-authentication required.",
                }
        except Exception as e:
            # Fall back to local refresh
            logger.warning(f"Token service unavailable, falling back to local refresh: {e}")

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
        logger.info(f"[{now_utc()}] Admin UI: Refreshing Schwab OAuth token...")
        client.update_tokens()
        logger.info(f"[{now_utc()}] Admin UI: Token refresh successful")

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
        logger.error(f"Token refresh error: {e}", exc_info=True)

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
    try:
        from urllib.parse import urlencode

        # Get Schwab credentials from environment
        app_key = os.getenv("SCHWAB_API_KEY")
        app_secret = os.getenv("SCHWAB_API_SECRET")
        callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

        if not app_key or not app_secret:
            return {
                "success": False,
                "message": "Schwab API credentials not found in environment variables",
                "required_vars": ["SCHWAB_API_KEY", "SCHWAB_API_SECRET", "SCHWAB_CALLBACK_URL"],
            }

        # Build OAuth authorization URL
        # Schwab OAuth 2.0 endpoint
        auth_base_url = "https://api.schwabapi.com/v1/oauth/authorize"

        # OAuth parameters
        params = {
            "client_id": app_key,
            "redirect_uri": callback_url,
            "response_type": "code",
        }

        oauth_url = f"{auth_base_url}?{urlencode(params)}"

        return {
            "success": True,
            "oauth_url": oauth_url,
            "callback_url": callback_url,
            "instructions": [
                "1. Visit the OAuth URL below",
                "2. Log in with your Schwab credentials",
                "3. Authorize the application",
                "4. You will be redirected to the callback URL",
                "5. Copy the 'code' parameter from the callback URL",
                "6. Use the code in the OAuth callback endpoint",
            ],
        }

    except ImportError:
        return {
            "success": False,
            "message": "schwabdev library not available",
            "note": "Install schwabdev: pip install schwabdev",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to generate OAuth URL: {str(e)}",
        }


@router.get("/oauth-redirect", response_class=HTMLResponse)
async def handle_oauth_redirect(code: str, session: str = None):
    """
    Handle OAuth redirect from Schwab (public endpoint - no auth required).

    This endpoint is called directly by the browser after Schwab redirects,
    so it must be publicly accessible (no authentication).

    Args:
        code: Authorization code from Schwab OAuth flow
        session: Session ID (optional)

    Returns:
        HTML page showing success/failure
    """
    if not code:
        return {
            "success": False,
            "message": "No authorization code provided",
        }

    try:

        settings = get_settings()
        token_db_path = settings.tokens_dir / "schwabdev_tokens.db"

        # Get Schwab credentials from environment
        app_key = os.getenv("SCHWAB_API_KEY")
        app_secret = os.getenv("SCHWAB_API_SECRET")
        callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

        if not app_key or not app_secret:
            return {
                "success": False,
                "message": "Schwab API credentials not found in environment variables",
                "required_vars": ["SCHWAB_API_KEY", "SCHWAB_API_SECRET", "SCHWAB_CALLBACK_URL"],
            }

        # Ensure tokens directory exists
        settings.tokens_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{now_utc()}] Admin UI: Exchanging OAuth code for tokens...")

        # Use the standalone exchange function (same as schwab_oauth_callback.py script)
        from .tokens_helper import exchange_code_for_tokens, save_tokens_to_db

        issued_time = datetime.now(timezone.utc)
        tokens = exchange_code_for_tokens(code, app_key, app_secret, callback_url)
        save_tokens_to_db(tokens, str(token_db_path), issued_time)

        logger.info(f"[{now_utc()}] Admin UI: OAuth token exchange successful")

        # Return HTML success page
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Success</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 500px;
                }
                .success {
                    color: #10b981;
                    font-size: 48px;
                    margin-bottom: 20px;
                }
                h1 {
                    color: #1f2937;
                    margin-bottom: 20px;
                }
                p {
                    color: #6b7280;
                    line-height: 1.6;
                }
                .close-btn {
                    background: #667eea;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-size: 16px;
                    cursor: pointer;
                    margin-top: 20px;
                }
                .close-btn:hover {
                    background: #5568d3;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success">✓</div>
                <h1>Authorization Successful!</h1>
                <p>Your Schwab API tokens have been obtained and stored.</p>
                <p>You can now close this window and return to the application.</p>
                <button class="close-btn" onclick="window.close()">Close Window</button>
            </div>
        </body>
        </html>
        """

    except Exception as e:
        logger.error(f"OAuth redirect error: {e}", exc_info=True)

        # Return HTML error page
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Error</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    text-align: center;
                    max-width: 500px;
                }}
                .error {{
                    color: #ef4444;
                    font-size: 48px;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #1f2937;
                    margin-bottom: 20px;
                }}
                p {{
                    color: #6b7280;
                    line-height: 1.6;
                }}
                .error-details {{
                    background: #fee2e2;
                    border: 1px solid #fecaca;
                    border-radius: 6px;
                    padding: 12px;
                    margin-top: 20px;
                    font-size: 14px;
                    text-align: left;
                    color: #991b1b;
                    word-wrap: break-word;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error">✗</div>
                <h1>Authorization Failed</h1>
                <p>There was an error exchanging the OAuth code for tokens.</p>
                <div class="error-details">
                    <strong>Error:</strong> {str(e)}
                </div>
            </div>
        </body>
        </html>
        """


@router.post("/oauth-callback")
async def handle_oauth_callback(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """
    Handle OAuth callback with authorization code (authenticated endpoint).

    Args:
        code: Authorization code from Schwab OAuth flow
        current_user: Authenticated user

    Returns:
        Token exchange result
    """
    if not code:
        return {
            "success": False,
            "message": "No authorization code provided",
        }

    try:
        import schwabdev

        settings = get_settings()
        token_db_path = settings.tokens_dir / "schwabdev_tokens.db"

        # Get Schwab credentials from environment
        app_key = os.getenv("SCHWAB_API_KEY")
        app_secret = os.getenv("SCHWAB_API_SECRET")
        callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

        if not app_key or not app_secret:
            return {
                "success": False,
                "message": "Schwab API credentials not found in environment variables",
                "required_vars": ["SCHWAB_API_KEY", "SCHWAB_API_SECRET", "SCHWAB_CALLBACK_URL"],
            }

        # Ensure tokens directory exists
        settings.tokens_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{now_utc()}] Admin UI: Exchanging OAuth code for tokens...")

        # Initialize schwabdev client with the authorization code
        # This will automatically exchange the code for tokens and store them
        schwabdev.Client(
            app_key,
            app_secret,
            callback_url,
            tokens_db=str(token_db_path),
        )

        # The schwabdev client should now have valid tokens
        # Verify by attempting to get token status
        token_status = get_token_from_db()

        if token_status and token_status.get("has_token"):
            logger.info(f"[{now_utc()}] Admin UI: OAuth token exchange successful")

            return {
                "success": True,
                "message": "OAuth authorization successful. Tokens obtained and stored.",
                "token_status": token_status,
            }
        else:
            return {
                "success": False,
                "message": "Token exchange completed but tokens not found in database",
            }

    except ImportError:
        return {
            "success": False,
            "message": "schwabdev library not available",
            "note": "Install schwabdev: pip install schwabdev",
        }
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)

        return {
            "success": False,
            "message": f"OAuth authorization failed: {str(e)}",
            "error_type": type(e).__name__,
            "hint": "Make sure the authorization code is valid and not expired. Codes are typically valid for only a few minutes.",
        }
