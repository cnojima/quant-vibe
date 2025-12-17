"""Refresh schwab-py authentication token.

This script will prompt you to authorize via browser and update the token JSON file.

Usage:
    python scripts/refresh_schwabpy_token.py
"""

import os
from schwab import auth
from dotenv import load_dotenv

load_dotenv()

print("="*70)
print("SCHWAB-PY TOKEN REFRESH")
print("="*70)

api_key = os.getenv("SCHWAB_API_KEY")
app_secret = os.getenv("SCHWAB_API_SECRET")
redirect_uri = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182/")
token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")

print(f"\nToken file: {token_path}")
print("\nThis will open a browser for you to authorize the application.")
print("After authorizing, you'll be redirected to a URL starting with your callback URL.")
print("Copy the ENTIRE URL from the browser address bar and paste it when prompted.\n")

input("Press Enter to continue...")

try:
    # This will prompt for authorization in the browser
    client = auth.client_from_manual_flow(
        api_key=api_key,
        app_secret=app_secret,
        callback_url=redirect_uri,
        token_path=token_path
    )

    print("\n✅ Token refreshed successfully!")
    print(f"Token file updated: {token_path}")

    # Test the token
    print("\nTesting token with a quote request...")
    response = client.get_quote("SPY")
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
