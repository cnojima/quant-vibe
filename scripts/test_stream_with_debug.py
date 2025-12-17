"""Test streaming with verbose debugging to diagnose the issue."""

import sys
from pathlib import Path
import asyncio
import os
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schwab import auth
from schwab.streaming import StreamClient
from schwab.client import Client
from dotenv import load_dotenv

load_dotenv()


async def test_streaming():
    """Test streaming with verbose output."""

    print("="*70)
    print("SCHWAB STREAMING DEBUG TEST")
    print(f"Time: {datetime.now()}")
    print("="*70)
    print()

    # Initialize client
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    account_number = os.getenv("SCHWAB_ACCOUNT_NUMBER")

    print("Initializing Schwab client...")
    client = auth.client_from_token_file(token_path, api_key, app_secret)
    print("✅ Client initialized")

    # Get SPX price
    print("\nGetting SPX price...")
    response = client.get_quote("$SPX")
    quote_data = response.json()
    spx_price = quote_data.get("$SPX", {}).get("quote", {}).get("lastPrice", 6000)
    print(f"SPX Price: ${spx_price:.2f}")

    # Get option chain
    print("\nFetching option chain...")
    response = client.get_option_chain(
        "$SPX",
        contract_type=Client.Options.ContractType.CALL,
        strike_count=5,
        include_underlying_quote=True
    )

    if response.status_code != 200:
        print(f"❌ Option chain failed: {response.status_code}")
        print(f"Response: {response.text}")
        return

    chain_data = response.json()
    print(f"✅ Option chain received")

    # Extract some contract symbols
    contracts = []
    if 'callExpDateMap' in chain_data:
        for exp_date, strikes in list(chain_data['callExpDateMap'].items())[:2]:  # First 2 expirations
            for strike_price, contracts_list in list(strikes.items())[:3]:  # First 3 strikes
                for contract in contracts_list:
                    symbol = contract.get('symbol', '')
                    if symbol:
                        contracts.append(symbol)
                        print(f"  Contract: {symbol}")
                        if len(contracts) >= 5:  # Limit to 5 contracts for testing
                            break
                if len(contracts) >= 5:
                    break
            if len(contracts) >= 5:
                break

    if not contracts:
        print("❌ No contracts found")
        return

    print(f"\n✅ Found {len(contracts)} contracts to test")

    # Initialize streaming
    print("\nInitializing streaming client...")
    stream_client = StreamClient(client, account_id=account_number)
    print("✅ Streaming client created")

    # Message counter
    message_count = 0
    messages_received = []

    async def option_handler(msg):
        nonlocal message_count
        message_count += 1
        messages_received.append(msg)
        print(f"\n📨 Message #{message_count}")
        print(f"   Service: {msg.get('service')}")
        print(f"   Timestamp: {datetime.now()}")
        print(f"   Content items: {len(msg.get('content', []))}")

        # Print first few content items
        for i, item in enumerate(msg.get('content', [])[:2]):
            print(f"   Item {i}: {item.get('key')} - {item}")

    # Add handler BEFORE login
    stream_client.add_options_book_handler(option_handler)

    # Login
    print("\n🔌 Logging in to WebSocket...")
    try:
        await stream_client.login()
        print("✅ WebSocket connected")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Subscribe to options
    print(f"\n📡 Subscribing to {len(contracts)} option contracts...")
    for contract in contracts:
        print(f"   Subscribing to: {contract}")

    try:
        await stream_client.options_book_subs(contracts)
        print("✅ Subscribed to options")
    except Exception as e:
        print(f"❌ Subscription failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Also try level one equity quotes for comparison
    print("\n📡 Also subscribing to $SPX equity quotes (for comparison)...")

    equity_message_count = 0

    async def equity_handler(msg):
        nonlocal equity_message_count
        equity_message_count += 1
        print(f"\n📈 Equity Message #{equity_message_count}")
        print(f"   Service: {msg.get('service')}")
        print(f"   Content items: {len(msg.get('content', []))}")

    stream_client.add_level_one_equity_handler(equity_handler)

    try:
        await stream_client.level_one_equity_subs(["$SPX"])
        print("✅ Subscribed to equity quotes")
    except Exception as e:
        print(f"⚠️  Equity subscription failed: {e}")

    # Wait and monitor
    print("\n⏳ Waiting 30 seconds for messages...")
    print("   (Press Ctrl+C to stop early)")

    for i in range(30):
        await asyncio.sleep(1)
        if i % 5 == 0:
            print(f"   {i}s - Options messages: {message_count}, Equity messages: {equity_message_count}")

    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    print(f"Option messages received: {message_count}")
    print(f"Equity messages received: {equity_message_count}")

    if message_count == 0 and equity_message_count == 0:
        print("\n⚠️  NO MESSAGES RECEIVED")
        print("\nPossible causes:")
        print("1. ❌ Streaming data not enabled for your Schwab account")
        print("   - Contact Schwab to enable streaming/real-time data permissions")
        print("   - This is often a separate permission from API access")
        print("\n2. ⚠️  Market data delay")
        print("   - Some accounts only have delayed data (15-20 min)")
        print("\n3. ⚠️  Symbol format issues")
        print("   - SPX options might use different symbol format in streaming API")
        print("\nRecommendation: Use the polling approach instead (poll_spxw_quotes.py)")
        print("                Polling works with REST API which is already functional")

    elif equity_message_count > 0 and message_count == 0:
        print("\n⚠️  Equity quotes working but NOT options quotes")
        print("   - This suggests options streaming might not be enabled")
        print("   - Or SPX options symbol format is incorrect for streaming")
        print("\nRecommendation: Use polling approach for options data")

    else:
        print("\n✅ Streaming is working!")
        if len(messages_received) > 0:
            print(f"\nSample message:")
            print(messages_received[0])


if __name__ == "__main__":
    try:
        asyncio.run(test_streaming())
    except KeyboardInterrupt:
        print("\n\nTest stopped by user")
