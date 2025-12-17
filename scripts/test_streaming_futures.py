"""Test streaming /ES futures with verbose logging.

This script tests streaming E-mini S&P 500 futures (/ES) data from Schwab.
Futures streaming may have different permissions than options/equities.

Usage:
    python scripts/test_streaming_futures.py
"""

import sys
from pathlib import Path
import asyncio
import os
import logging
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schwab import auth
from schwab.streaming import StreamClient
from schwab.client import Client
from dotenv import load_dotenv

load_dotenv()

# Enable verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_futures_streaming():
    """Test streaming /ES futures with full debug logging."""

    print("="*70)
    print("FUTURES STREAMING TEST - /ES (E-mini S&P 500)")
    print("="*70)

    # Initialize client
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    account_number = os.getenv("SCHWAB_ACCOUNT_NUMBER")

    print("\n1. Initializing client...")
    client = auth.client_from_token_file(token_path, api_key, app_secret)
    print("   ✓ Client initialized")

    # Get futures contract
    print("\n2. Getting /ES futures contract info...")

    # Try to get current /ES contract via REST API
    # Futures symbols in Schwab: /ES (front month), /ESH25 (March 2025), etc.
    futures_symbols = [
        "/ES",      # Front month (most liquid)
        "/ESZ24",   # December 2024
        "/ESH25",   # March 2025
        "/ESM25",   # June 2025
    ]

    # Test if we can get quotes for these symbols
    print("   Testing futures symbols...")
    test_symbol = None
    for symbol in futures_symbols:
        try:
            print(f"   Trying {symbol}...")
            response = client.get_quote(symbol)
            print(f"      Status: {response.status_code}")

            if response.status_code == 200:
                quote_data = response.json()
                print(f"      Keys in response: {list(quote_data.keys())}")

                if symbol in quote_data:
                    test_symbol = symbol
                    quote = quote_data[symbol].get('quote', {})
                    last_price = quote.get('lastPrice', 'N/A')
                    print(f"   ✓ {symbol} - Last: ${last_price}")
                    break
                else:
                    # Try to find any key that looks like the symbol
                    for key in quote_data.keys():
                        if 'ES' in key.upper():
                            test_symbol = key
                            quote = quote_data[key].get('quote', {})
                            last_price = quote.get('lastPrice', 'N/A')
                            print(f"   ✓ Found {key} - Last: ${last_price}")
                            break
                    if test_symbol:
                        break
            else:
                error_text = response.text[:200]
                print(f"      Error: {error_text}")

        except Exception as e:
            print(f"   ✗ {symbol} - Error: {e}")
            import traceback
            traceback.print_exc()

    if not test_symbol:
        print("\n   ❌ Could not find valid /ES futures contract")
        print("   Note: Futures access may require special permissions")
        return

    print(f"\n   ✓ Using symbol: {test_symbol}")

    # Initialize streaming
    print("\n3. Initializing StreamClient...")
    stream_client = StreamClient(client, account_id=account_number)
    print("   ✓ StreamClient created")

    # Login
    print("\n4. Logging in to streaming service...")
    print("   (Watch for DEBUG messages in logs)")
    await stream_client.login()
    print("   ✓ Logged in")

    # Subscribe to futures
    print(f"\n5. Subscribing to {test_symbol} Level 1 futures data...")

    messages = []
    last_message_time = None

    async def futures_handler(msg):
        nonlocal last_message_time
        messages.append(msg)
        last_message_time = datetime.now()

        print(f"\n📨 FUTURES MESSAGE RECEIVED!")
        print(f"   Time: {last_message_time.strftime('%H:%M:%S')}")
        print(f"   Service: {msg.get('service', 'N/A')}")
        print(f"   Command: {msg.get('command', 'N/A')}")

        # Parse content
        content = msg.get('content', [])
        if content:
            for item in content[:3]:  # Show first 3 items
                print(f"   Data: {item}")

        # Show timestamp
        timestamp = msg.get('timestamp')
        if timestamp:
            print(f"   Timestamp: {timestamp}")

    # Add handler and subscribe
    stream_client.add_level_one_futures_handler(futures_handler)
    await stream_client.level_one_futures_subs([test_symbol])

    print("   ✓ Subscribed to futures stream")
    print("\n6. Waiting for messages (60 seconds)...")
    print("   Market Hours (US futures): Nearly 24/5 (Sun 6pm - Fri 5pm ET)")
    print("   Current time: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print()

    # Wait and monitor
    for i in range(60):
        await asyncio.sleep(1)

        if i % 10 == 0 and i > 0:
            status = f"   [{i}s] Messages: {len(messages)}"
            if last_message_time:
                elapsed = (datetime.now() - last_message_time).total_seconds()
                status += f" | Last: {elapsed:.0f}s ago"
            print(status)

    # Results
    print(f"\n7. Test Complete")
    print("="*70)
    print(f"Total messages received: {len(messages)}")
    print("="*70)

    if len(messages) == 0:
        print("\n⚠️  NO MESSAGES RECEIVED")
        print("\nPossible reasons:")
        print("  1. Market closed (futures trade nearly 24/5)")
        print("  2. No streaming permissions for futures data")
        print("  3. Account not enabled for futures")
        print("  4. Symbol format incorrect")
        print("\nCheck DEBUG logs above for:")
        print("  - WebSocket connection status")
        print("  - Login response (look for 'response' messages)")
        print("  - Subscription response (accepted/rejected)")
        print("  - Permission or entitlement errors")
        print("  - Market data authorization issues")
    else:
        print("\n✅ SUCCESS - Receiving futures data!")
        print(f"\nFirst message preview:")
        if messages:
            import json
            print(json.dumps(messages[0], indent=2)[:500])
        print("\nFutures streaming appears to be working!")

    # Cleanup
    print("\n8. Cleaning up...")
    await stream_client.level_one_futures_unsubs([test_symbol])
    print("   ✓ Unsubscribed")


async def test_all_futures_services():
    """Test multiple futures streaming services to see which work."""

    print("="*70)
    print("TESTING ALL FUTURES STREAMING SERVICES")
    print("="*70)

    # Initialize client
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    account_number = os.getenv("SCHWAB_ACCOUNT_NUMBER")

    client = auth.client_from_token_file(token_path, api_key, app_secret)
    stream_client = StreamClient(client, account_id=account_number)

    print("\nLogging in...")
    await stream_client.login()
    print("✓ Logged in")

    test_symbol = "/ES"
    results = {}

    # Test services
    services = [
        ("Level 1 Futures", stream_client.level_one_futures_subs, stream_client.add_level_one_futures_handler),
        # Note: Schwab may have other futures services like charts, options on futures, etc.
    ]

    for service_name, subscribe_func, handler_func in services:
        print(f"\n{'='*70}")
        print(f"Testing: {service_name}")
        print(f"{'='*70}")

        messages = []

        async def test_handler(msg):
            messages.append(msg)
            print(f"  📨 {service_name}: Got message!")

        handler_func(test_handler)

        try:
            await subscribe_func([test_symbol])
            print(f"  ✓ Subscribed to {service_name}")

            # Wait 10 seconds
            print(f"  Waiting 10 seconds...")
            await asyncio.sleep(10)

            results[service_name] = len(messages)
            print(f"  Result: {len(messages)} messages")

        except Exception as e:
            results[service_name] = f"Error: {e}"
            print(f"  ✗ Error: {e}")

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for service, result in results.items():
        if isinstance(result, int):
            status = f"✓ {result} messages" if result > 0 else "✗ No data"
        else:
            status = f"✗ {result}"
        print(f"{service}: {status}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test futures streaming")
    parser.add_argument(
        "--all-services",
        action="store_true",
        help="Test all available futures streaming services"
    )
    args = parser.parse_args()

    try:
        if args.all_services:
            asyncio.run(test_all_futures_services())
        else:
            asyncio.run(test_futures_streaming())
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
