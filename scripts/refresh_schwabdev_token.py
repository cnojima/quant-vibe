"""Refresh schwabdev authentication token.

This script checks if existing tokens are valid, and only prompts for
re-authorization if needed.

Usage:
    python scripts/refresh_schwabdev_token.py

    # Force re-authentication even if tokens are valid
    python scripts/refresh_schwabdev_token.py --force
"""

import os
import sys
import argparse
from pathlib import Path
import schwabdev
from dotenv import load_dotenv

load_dotenv()

def check_token_validity(client):
    """Check if the current token is valid by making a test API call.

    Args:
        client: schwabdev.Client instance

    Returns:
        True if token is valid, False otherwise
    """
    try:
        # Try a simple API call
        response = client.quote("SPY")

        if response.status_code == 200:
            return True
        elif response.status_code == 401:
            # Unauthorized - token is invalid
            return False
        else:
            # Some other error - assume token might be invalid
            print(f"   ⚠️  Unexpected status code: {response.status_code}")
            return False

    except Exception as e:
        print(f"   ⚠️  Error testing token: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Refresh Schwab OAuth tokens")
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force re-authentication even if tokens are valid'
    )
    args = parser.parse_args()

    print("="*70)
    print("SCHWABDEV TOKEN REFRESH")
    print("="*70)

    tokens_db_path = "tokens/schwabdev_tokens.db"

    # Check if token database exists
    if Path(tokens_db_path).exists() and not args.force:
        print(f"\n📁 Found existing token database: {tokens_db_path}")
        print("🔍 Checking if tokens are still valid...")

        try:
            # Try to initialize client with existing tokens
            client = schwabdev.Client(
                os.getenv("SCHWAB_API_KEY"),
                os.getenv("SCHWAB_API_SECRET"),
                os.getenv("SCHWAB_CALLBACK_URL"),
                tokens_db=tokens_db_path,
            )

            # Test if token works
            if check_token_validity(client):
                print("✅ Tokens are valid! No refresh needed.")

                # Get a quote to show it's working
                print("\n📊 Testing with SPY quote...")
                response = client.quote("SPY")
                data = response.json()
                spy_price = data['SPY']['quote']['lastPrice']
                spy_change = data['SPY']['quote'].get('netChange', 0)
                spy_percent = data['SPY']['quote'].get('netPercentChangeInDouble', 0)

                print(f"   SPY: ${spy_price:.2f} ({spy_change:+.2f}, {spy_percent:+.2f}%)")
                print(f"\n✅ All set! Tokens are working correctly.")
                return
            else:
                print("❌ Tokens are invalid or expired.")
                print("   Proceeding with re-authentication...\n")

        except Exception as e:
            print(f"⚠️  Error checking existing tokens: {e}")
            print("   Proceeding with re-authentication...\n")
    else:
        if args.force:
            print("\n🔄 Force re-authentication requested...")
        else:
            print(f"\n📁 No existing token database found at: {tokens_db_path}")
            print("   Creating new tokens...")

    # Need to re-authenticate
    print("\n" + "="*70)
    print("BROWSER AUTHENTICATION REQUIRED")
    print("="*70)
    print("\nThis will open a browser for you to authorize the application.")
    print("After authorizing, you'll be redirected to a URL starting with your callback URL.")
    print("Copy the ENTIRE URL from the browser address bar and paste it when prompted.")
    print("\nPress Ctrl+C to cancel, or Enter to continue...")

    try:
        input()
    except (EOFError, KeyboardInterrupt):
        print("\n\n❌ Cancelled by user")
        sys.exit(1)

    try:
        # Remove old tokens if forcing refresh
        if args.force and Path(tokens_db_path).exists():
            print(f"\n🗑️  Removing old token database...")
            Path(tokens_db_path).unlink()

        # Initialize client (will trigger OAuth flow)
        client = schwabdev.Client(
            os.getenv("SCHWAB_API_KEY"),
            os.getenv("SCHWAB_API_SECRET"),
            os.getenv("SCHWAB_CALLBACK_URL"),
            tokens_db=tokens_db_path,
        )

        print("\n✅ Token refreshed successfully!")
        print(f"   Token database: {tokens_db_path}")

        # Test the new token
        print("\n📊 Testing new token with SPY quote...")
        response = client.quote("SPY")
        if response.status_code == 200:
            data = response.json()
            spy_price = data['SPY']['quote']['lastPrice']
            spy_change = data['SPY']['quote'].get('netChange', 0)
            spy_percent = data['SPY']['quote'].get('netPercentChangeInDouble', 0)

            print(f"   SPY: ${spy_price:.2f} ({spy_change:+.2f}, {spy_percent:+.2f}%)")
            print(f"\n✅ Success! New tokens are working correctly.")
        else:
            print(f"   ⚠️  Quote request returned status {response.status_code}")
            print(f"   Response: {response.text[:200]}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
