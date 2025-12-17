"""Check Schwab User Preferences endpoint for streaming configuration."""

import sys
from pathlib import Path
import os
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schwab import auth
from dotenv import load_dotenv

load_dotenv()


def check_user_preferences():
    """Check user preferences for streaming entitlements."""

    print("="*70)
    print("SCHWAB USER PREFERENCES CHECK")
    print("="*70)

    # Initialize client
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")

    print("\nInitializing Schwab client...")
    client = auth.client_from_token_file(token_path, api_key, app_secret)
    print("✅ Client initialized")

    # Get user preferences
    print("\n" + "="*70)
    print("FETCHING USER PREFERENCES")
    print("="*70)

    try:
        response = client.get_user_preferences()

        if response.status_code == 200:
            preferences = response.json()

            print("\n✅ User preferences retrieved successfully")
            print(f"\nFull response:")
            print(json.dumps(preferences, indent=2))

            # Check for streamer info
            print("\n" + "="*70)
            print("STREAMER INFORMATION")
            print("="*70)

            if 'streamerInfo' in preferences:
                streamer_info = preferences['streamerInfo']
                print("\n✅ Streamer info found!")

                # Handle both list and dict
                if isinstance(streamer_info, list):
                    if len(streamer_info) > 0:
                        streamer_info = streamer_info[0]
                        print(f"\nStreamer details (using first item from list):")
                    else:
                        print("\n⚠️  Streamer info list is empty")
                        streamer_info = {}
                else:
                    print(f"\nStreamer details:")

                for key, value in streamer_info.items():
                    if key == 'streamerSocketUrl':
                        print(f"  {key}: {value}")
                    elif key == 'token':
                        print(f"  {key}: {value[:50]}... (truncated)")
                    else:
                        print(f"  {key}: {value}")

                # Check for market data entitlements
                print("\n" + "="*70)
                print("MARKET DATA ENTITLEMENTS")
                print("="*70)

                if 'quotes' in preferences:
                    quotes = preferences['quotes']
                    print("\n📊 Quote entitlements:")
                    print(json.dumps(quotes, indent=2))

                if 'streamerInfo' in preferences:
                    si = preferences['streamerInfo']
                    if 'quotes' in si:
                        print("\n📊 Streamer quote entitlements:")
                        print(json.dumps(si['quotes'], indent=2))

            else:
                print("\n❌ No streamer info found in preferences")
                print("\nThis likely means:")
                print("  1. Streaming is not enabled for your account")
                print("  2. You need to contact Schwab to enable streaming")

            # Check account info
            print("\n" + "="*70)
            print("ACCOUNT INFORMATION")
            print("="*70)

            if 'accounts' in preferences:
                accounts = preferences['accounts']
                print(f"\n✅ Found {len(accounts)} account(s)")
                for i, acc in enumerate(accounts):
                    print(f"\nAccount {i+1}:")
                    print(f"  Account Number: {acc.get('accountNumber')}")
                    print(f"  Primary: {acc.get('primaryAccount')}")
                    print(f"  Type: {acc.get('type')}")
                    if 'authorizations' in acc:
                        print(f"  Authorizations: {acc.get('authorizations')}")

            # Summary
            print("\n" + "="*70)
            print("DIAGNOSIS")
            print("="*70)

            has_streamer_info = 'streamerInfo' in preferences
            has_socket_url = has_streamer_info and 'streamerSocketUrl' in preferences.get('streamerInfo', {})
            has_token = has_streamer_info and 'token' in preferences.get('streamerInfo', {})

            if has_streamer_info and has_socket_url and has_token:
                print("\n✅ STREAMING IS CONFIGURED")
                print("\nYour account has:")
                print("  ✅ Streamer information")
                print("  ✅ WebSocket URL")
                print("  ✅ Streamer token")
                print("\nThe schwab-py library should handle this automatically.")
                print("If streaming still doesn't work, it may be a library issue.")
                print("\nNext steps:")
                print("  1. Check schwab-py version: pip show schwab-py")
                print("  2. Try upgrading: pip install --upgrade schwab-py")
                print("  3. Check if there's a known issue on GitHub")
            else:
                print("\n❌ STREAMING NOT PROPERLY CONFIGURED")
                print("\nMissing components:")
                if not has_streamer_info:
                    print("  ❌ No streamer info in user preferences")
                if not has_socket_url:
                    print("  ❌ No WebSocket URL")
                if not has_token:
                    print("  ❌ No streamer token")

                print("\nRoot cause:")
                print("  Streaming/real-time data is not enabled for your account")
                print("\nSolution:")
                print("  Contact Schwab to enable streaming data:")
                print("    - Phone: 1-800-435-4000")
                print("    - Or use developer.schwab.com support")
                print("    - Request 'real-time streaming market data'")

        else:
            print(f"\n❌ Failed to get user preferences: {response.status_code}")
            print(f"Response: {response.text[:500]}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)


if __name__ == "__main__":
    check_user_preferences()
