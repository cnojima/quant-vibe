"""
Schwab token management API endpoints.

Provides endpoints to view and refresh Schwab API tokens.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings

router = APIRouter()


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

        # Query the tokens table (schwabdev schema)
        cursor.execute("""
            SELECT access_token, refresh_token, id_token,
                   access_token_expires_at, refresh_token_expires_at
            FROM tokens
            ORDER BY access_token_expires_at DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        access_token, refresh_token, id_token, access_expires, refresh_expires = row

        # Parse timestamps (schwabdev stores as Unix timestamps)
        access_expires_dt = (
            datetime.fromtimestamp(access_expires, tz=timezone.utc)
            if access_expires else None
        )
        refresh_expires_dt = (
            datetime.fromtimestamp(refresh_expires, tz=timezone.utc)
            if refresh_expires else None
        )

        now = datetime.now(timezone.utc)

        return {
            "has_token": True,
            "access_token_expires_at": access_expires_dt.isoformat() if access_expires_dt else None,
            "refresh_token_expires_at": refresh_expires_dt.isoformat() if refresh_expires_dt else None,
            "access_token_expired": access_expires_dt < now if access_expires_dt else True,
            "refresh_token_expired": refresh_expires_dt < now if refresh_expires_dt else True,
            "access_token_age_minutes": (
                (now - access_expires_dt).total_seconds() / 60
                if access_expires_dt else None
            ),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read token database: {str(e)}"
        )


@router.get("/status")
async def get_token_status(current_user: User = Depends(get_current_user)):
    """
    Get Schwab token status.

    Args:
        current_user: Authenticated user

    Returns:
        Token status information
    """
    token_info = get_token_from_db()

    if not token_info:
        return {
            "has_token": False,
            "message": "No token found. Please authenticate.",
        }

    return token_info


@router.post("/refresh")
async def refresh_token(current_user: User = Depends(get_current_user)):
    """
    Manually refresh the Schwab token.

    This would typically call the TokenManager.refresh() method
    from the streaming service.

    Args:
        current_user: Authenticated user

    Returns:
        Refresh operation result

    Note:
        For MVP, this returns a placeholder. In production, you would:
        1. Import TokenManager from streaming_service
        2. Call refresh() method
        3. Return updated token status
    """
    # TODO: Implement actual token refresh
    # from streaming_service.token_manager import TokenManager
    # manager = TokenManager()
    # await manager.refresh()

    return {
        "success": True,
        "message": "Token refresh functionality to be implemented",
        "note": "For now, tokens are auto-refreshed by streaming service every 14 minutes",
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
