"""Refresh schwabdev authentication token.

This script will prompt you to authorize via browser and update the token database.

Usage:
    python scripts/refresh_schwabdev_token.py
"""

import os
import schwabdev
from dotenv import load_dotenv

load_dotenv()

print("="*70)
print("SCHWABDEV TOKEN REFRESH")
print("="*70)

print("\nThis will open a browser for you to authorize the application.")
print("After authorizing, you'll be redirected to a URL starting with your callback URL.")
print("Copy the ENTIRE URL from the browser address bar and paste it when prompted.\n")

input("Press Enter to continue...")

try:
    client = schwabdev.Client(
        os.getenv("SCHWAB_API_KEY"),
        os.getenv("SCHWAB_API_SECRET"),
        os.getenv("SCHWAB_CALLBACK_URL"),
        tokens_db="tokens/schwabdev_tokens.db",
    )

    print("\n✅ Token refreshed successfully!")
    print(f"Token database updated: tokens/schwabdev_tokens.db")

    # Test the token
    print("\nTesting token with a quote request...")
    response = client.quote("SPY")
    if response.status_code == 200:
        data = response.json()
        spy_price = data['SPY']['quote']['lastPrice']
        print(f"✅ Token works! SPY: ${spy_price:.2f}")
    else:
        print(f"⚠️  Quote request returned status {response.status_code}")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
