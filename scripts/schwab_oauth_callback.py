#!/usr/bin/env python3
"""
Schwab OAuth2 Callback Handler

Handles the OAuth2 callback URL from Schwab and exchanges the authorization
code for access/refresh tokens, saving them to the token database.

This script can be run in two modes:

1. Interactive mode (default):
   python scripts/schwab_oauth_callback.py

   Prompts you to paste the callback URL.

2. Command-line argument mode:
   python scripts/schwab_oauth_callback.py "https://127.0.0.1:53430/?code=..."

Usage after OAuth redirect:
1. User clicks "Authorize" on Schwab website
2. Browser redirects to callback URL (e.g., https://127.0.0.1:53430/?code=C0...)
3. Copy the entire URL from the browser address bar
4. Run this script and paste the URL (or pass as argument)
5. Script extracts the code and exchanges it for tokens
6. Tokens are saved to the database

Environment Variables Required:
    SCHWAB_API_KEY - Your Schwab API app key
    SCHWAB_API_SECRET - Your Schwab API app secret
    SCHWAB_CALLBACK_URL - OAuth callback URL (default: https://127.0.0.1)
    SCHWAB_TOKENS_DB - Path to tokens database (default: tokens/schwabdev_tokens.db)
"""

import os
import sys
from pathlib import Path
import urllib.parse
from datetime import datetime, timezone
import base64
import sqlite3
import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def extract_code_from_url(callback_url: str) -> str:
    """
    Extract the authorization code from the OAuth callback URL.

    Args:
        callback_url: Full callback URL (e.g., https://127.0.0.1:53430/?code=...)
                     or just the code itself

    Returns:
        Authorization code string

    Raises:
        ValueError: If code cannot be extracted from URL
    """
    # Try to parse as URL first
    parsed = urllib.parse.urlparse(callback_url)
    if parsed.scheme:
        # It's a full URL - extract code parameter
        query_params = urllib.parse.parse_qs(parsed.query)
        code = query_params.get("code", [None])[0]
        if not code:
            raise ValueError(f"No 'code' parameter found in URL: {callback_url}")
        return urllib.parse.unquote(code)
    else:
        # Assume it's already just the code
        return urllib.parse.unquote(callback_url)


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


def main():
    print("="*70)
    print("Schwab OAuth2 Callback Handler")
    print("="*70)
    print()

    # Get credentials from environment
    app_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")
    tokens_db = os.getenv("SCHWAB_TOKENS_DB", "tokens/schwabdev_tokens.db")

    # Validate credentials
    if not app_key or not app_secret:
        print("ERROR: Missing required environment variables")
        print()
        print("Please set the following in your .env file:")
        print("  SCHWAB_API_KEY=your_app_key")
        print("  SCHWAB_API_SECRET=your_app_secret")
        print("  SCHWAB_CALLBACK_URL=https://127.0.0.1  (optional)")
        print("  SCHWAB_TOKENS_DB=tokens/schwabdev_tokens.db  (optional)")
        sys.exit(1)

    print(f"App Key: {app_key[:10]}...")
    print(f"Callback URL: {callback_url}")
    print(f"Tokens DB: {tokens_db}")
    print()

    # Get callback URL from command line or prompt
    if len(sys.argv) > 1:
        # URL provided as command-line argument
        callback_url_input = sys.argv[1]
        print(f"Using callback URL from command line argument")
    else:
        # Interactive mode - prompt for URL
        print("INSTRUCTIONS:")
        print("1. After authorizing on Schwab website, you were redirected to a URL")
        print("2. Copy the ENTIRE URL from your browser address bar")
        print("3. It should look like:")
        print("   https://127.0.0.1:53430/?code=C0.b2F1dGgyLm...&session=...")
        print("4. Paste it below")
        print()
        callback_url_input = input("Paste the callback URL here: ").strip()

    if not callback_url_input:
        print("ERROR: No callback URL provided")
        sys.exit(1)

    print()
    print("-"*70)
    print("Processing...")
    print("-"*70)
    print()

    try:
        # Extract authorization code
        print("1. Extracting authorization code from URL...")
        code = extract_code_from_url(callback_url_input)
        print(f"   ✓ Code extracted: {code[:20]}...")
        print()

        # Exchange code for tokens
        print("2. Exchanging code for tokens...")
        issued_time = datetime.now(timezone.utc)
        tokens = exchange_code_for_tokens(code, app_key, app_secret, callback_url)
        print(f"   ✓ Tokens received from Schwab")
        print()

        # Save to database
        print("3. Saving tokens to database...")
        save_tokens_to_db(tokens, tokens_db, issued_time)
        print(f"   ✓ Tokens saved to: {tokens_db}")
        print()

        # Show token info
        print("-"*70)
        print("SUCCESS!")
        print("-"*70)
        print()
        print("Token Information:")
        print(f"  Access Token Issued: {issued_time.isoformat()}")
        print(f"  Token Type: {tokens.get('token_type', 'Bearer')}")
        print(f"  Expires In: {tokens.get('expires_in', 1800)} seconds ({tokens.get('expires_in', 1800) / 60:.1f} minutes)")
        print(f"  Scope: {tokens.get('scope', '')}")
        print()
        print("Next Steps:")
        print("  - Access token is valid for ~30 minutes")
        print("  - Refresh token is valid for 7 days")
        print("  - Your services will automatically refresh the access token")
        print("  - Re-run this script (or authorize_schwab.py) before the refresh token expires")
        print()
        print("Services you can now start:")
        print("  - Token Service: docker compose up token_service")
        print("  - Streaming Service: python scripts/stream_spxw_schwabdev.py")
        print("  - Live Trading: python scripts/run_live_trading.py")
        print()

    except ValueError as e:
        print()
        print("="*70)
        print("ERROR: Invalid callback URL")
        print("="*70)
        print()
        print(str(e))
        print()
        print("Make sure you paste the ENTIRE URL from the browser, including:")
        print("  - https://")
        print("  - The full code parameter")
        print("  - Any other query parameters")
        print()
        sys.exit(1)

    except requests.HTTPError as e:
        print()
        print("="*70)
        print("ERROR: Token exchange failed")
        print("="*70)
        print()
        print(str(e))
        print()
        sys.exit(1)

    except sqlite3.Error as e:
        print()
        print("="*70)
        print("ERROR: Database error")
        print("="*70)
        print()
        print(f"Failed to save tokens to database: {e}")
        print()
        print(f"Database path: {tokens_db}")
        print()
        sys.exit(1)

    except Exception as e:
        print()
        print("="*70)
        print("ERROR: Unexpected error")
        print("="*70)
        print()
        print(f"{type(e).__name__}: {e}")
        print()
        import traceback
        traceback.print_exc()
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
