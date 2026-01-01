#!/usr/bin/env python3
"""
Interactive Schwab OAuth Authorization Script

This script performs the initial OAuth flow with Schwab API to obtain
refresh and access tokens. Run this interactively when:

1. First time setup (no tokens exist)
2. Refresh token has expired (every 7 days)
3. Manual re-authorization needed

The tokens are stored in a SQLite database and used by all services
(token_service, streaming_service, live_trading, etc.)

Usage:
    python scripts/authorize_schwab.py

Environment Variables Required:
    SCHWAB_API_KEY - Your Schwab API app key
    SCHWAB_API_SECRET - Your Schwab API app secret
    SCHWAB_CALLBACK_URL - OAuth callback URL (default: https://127.0.0.1)
    SCHWAB_TOKENS_DB - Path to tokens database (default: tokens/schwabdev_tokens.db)
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
import schwabdev

# Load environment variables
load_dotenv()


def main():
    print("="*70)
    print("Schwab API OAuth Authorization")
    print("="*70)
    print()

    # Get credentials from environment
    # Support both SCHWAB_API_KEY and SCHWAB_API_KEY for backward compatibility
    app_key = os.getenv("SCHWAB_API_KEY") or os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET") or os.getenv("SCHWAB_API_SECRET")
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

    # Ensure tokens directory exists
    Path(tokens_db).parent.mkdir(parents=True, exist_ok=True)

    # Check if tokens already exist
    if Path(tokens_db).exists():
        print("⚠️  WARNING: Tokens database already exists")
        print(f"   Path: {tokens_db}")
        print()
        response = input("Continue and re-authorize? This will overwrite existing tokens. (y/N): ")
        if response.lower() != 'y':
            print("Authorization cancelled.")
            sys.exit(0)
        print()

    print("Starting OAuth flow...")
    print()
    print("INSTRUCTIONS:")
    print("1. A browser window will open with Schwab login")
    print("2. Log in to your Schwab account")
    print("3. Approve the authorization")
    print("4. You'll be redirected to localhost (this is expected)")
    print("5. Copy the ENTIRE redirected URL from your browser")
    print("6. Paste it here when prompted")
    print()
    input("Press ENTER to continue...")
    print()

    try:
        # Initialize client (this will trigger OAuth flow)
        client = schwabdev.Client(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=callback_url,
            tokens_db=tokens_db,
        )

        print()
        print("="*70)
        print("✓ Authorization Successful!")
        print("="*70)
        print()
        print(f"Tokens saved to: {tokens_db}")
        print()
        print("You can now start services that require Schwab API access:")
        print("  - Token Service: docker compose up token_service")
        print("  - Streaming Service: python scripts/stream_spxw_schwabdev.py")
        print("  - Live Trading: python scripts/run_live_trading.py")
        print()
        print("NOTE: Refresh tokens expire after 7 days.")
        print("      Re-run this script when you see authentication errors.")
        print()

    except KeyboardInterrupt:
        print()
        print("Authorization cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print()
        print("="*70)
        print("✗ Authorization Failed")
        print("="*70)
        print()
        print(f"Error: {e}")
        print()
        print("Common issues:")
        print("  - Incorrect app key or secret")
        print("  - Callback URL mismatch (must match Schwab app settings)")
        print("  - Invalid redirect URL pasted")
        print("  - Network connectivity issues")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
