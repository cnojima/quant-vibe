"""
Helper functions for Schwab OAuth token management.

These functions are shared between the API endpoint and standalone scripts.
"""

import base64
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests


def exchange_code_for_tokens(
    code: str,
    app_key: str,
    app_secret: str,
    callback_url: str,
) -> dict:
    """
    Exchange authorization code for access and refresh tokens.

    Args:
        code: Authorization code from OAuth callback
        app_key: Schwab API key
        app_secret: Schwab API secret
        callback_url: OAuth callback URL (must match app settings)

    Returns:
        Token dictionary with access_token, refresh_token, etc.

    Raises:
        requests.HTTPError: If token exchange fails
    """
    # Build OAuth token endpoint request
    auth_string = f"{app_key}:{app_secret}"
    auth_b64 = base64.b64encode(auth_string.encode()).decode()

    headers = {
        'Authorization': f'Basic {auth_b64}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': callback_url
    }

    response = requests.post(
        'https://api.schwabapi.com/v1/oauth/token',
        headers=headers,
        data=data,
        timeout=30
    )

    if not response.ok:
        error_msg = (
            f"Token exchange failed (HTTP {response.status_code}): {response.text}\n\n"
            "Common issues:\n"
            "1. App status is not 'Ready For Use' in Schwab developer portal\n"
            "2. App key or app secret is invalid\n"
            "3. Authorization code expired (codes expire in ~30 seconds)\n"
            "4. Callback URL doesn't match the one configured in Schwab app settings\n"
            "5. You pasted the wrong URL or code"
        )
        raise requests.HTTPError(error_msg, response=response)

    return response.json()


def save_tokens_to_db(
    tokens: dict,
    db_path: str,
    issued_time: datetime = None,
) -> bool:
    """
    Save tokens to the schwabdev database.

    Args:
        tokens: Token dictionary from Schwab OAuth
        db_path: Path to tokens database
        issued_time: When tokens were issued (defaults to now)

    Returns:
        True if successful

    Raises:
        sqlite3.Error: If database operation fails
    """
    if issued_time is None:
        issued_time = datetime.now(timezone.utc)

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table if it doesn't exist (same schema as schwabdev)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schwabdev (
            access_token_issued TEXT NOT NULL,
            refresh_token_issued TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            id_token TEXT NOT NULL,
            expires_in INTEGER,
            token_type TEXT,
            scope TEXT
        );
    """)

    # Delete existing tokens
    cursor.execute("DELETE FROM schwabdev")

    # Insert new tokens
    cursor.execute(
        """
        INSERT INTO schwabdev (
            access_token_issued,
            refresh_token_issued,
            access_token,
            refresh_token,
            id_token,
            expires_in,
            token_type,
            scope
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            issued_time.isoformat(),
            issued_time.isoformat(),
            tokens.get("access_token", ""),
            tokens.get("refresh_token", ""),
            tokens.get("id_token", ""),
            tokens.get("expires_in", 1800),  # Default 30 minutes
            tokens.get("token_type", "Bearer"),
            tokens.get("scope", ""),
        ),
    )

    conn.commit()
    conn.close()

    return True
