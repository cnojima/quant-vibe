"""Test streaming with verbose logging to see what's happening."""

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


async def test_with_logging():
    """Test streaming with full debug logging."""

    print("="*70)
    print("STREAMING TEST WITH VERBOSE LOGGING")
    print("="*70)

    # Initialize client
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    account_number = os.getenv("SCHWAB_ACCOUNT_NUMBER")

    print("\n1. Initializing client...")
    client = auth.client_from_token_file(token_path, api_key, app_secret)

    # Get one contract
    print("\n2. Getting test contract...")
    response = client.get_option_chain("$SPX", contract_type=Client.Options.ContractType.CALL, strike_count=1)

    contract = None
    if response.status_code == 200:
        chain = response.json()
        if "callExpDateMap" in chain:
            for exp_date, strikes in list(chain["callExpDateMap"].items())[:1]:
                for strike, contract_list in list(strikes.items())[:1]:
                    for c in contract_list:
                        symbol = c.get("symbol", "")
                        if symbol.startswith("SPXW"):
                            contract = symbol
                            print(f"   Test contract: {contract}")
                            break

    if not contract:
        print("❌ No contract found")
        return

    # Initialize streaming
    print("\n3. Initializing StreamClient...")
    stream_client = StreamClient(client, account_id=account_number)

    # Login
    print("\n4. Logging in (watch for DEBUG messages)...")
    await stream_client.login()
    print("✅ Logged in")

    # Subscribe
    print("\n5. Subscribing to option...")

    messages = []

    async def handler(msg):
        messages.append(msg)
        print(f"\n📨 MESSAGE RECEIVED!")
        print(f"   Service: {msg.get('service')}")
        print(f"   Timestamp: {msg.get('timestamp')}")
        print(f"   Content: {msg.get('content', [])[:100]}...")

    stream_client.add_level_one_option_handler(handler)
    await stream_client.level_one_option_subs([contract])

    print("✅ Subscribed")
    print("\n6. Waiting for messages (60 seconds)...")
    print("   Watch the DEBUG logs above for clues...\n")

    for i in range(60):
        await asyncio.sleep(1)
        if i % 10 == 0 and i > 0:
            print(f"   [{i}s] Messages received: {len(messages)}")

    print(f"\n7. Final count: {len(messages)} messages")

    if len(messages) == 0:
        print("\n" + "="*70)
        print("NO MESSAGES RECEIVED")
        print("="*70)
        print("\nCheck the DEBUG logs above for:")
        print("  1. WebSocket connection establishment")
        print("  2. Login request/response")
        print("  3. Subscription request/response")
        print("  4. Any error messages or rejections")
        print("\nKey things to look for:")
        print("  - 'Login successful' or similar")
        print("  - 'Subscription accepted' or similar")
        print("  - Any 'permission denied' or 'unauthorized' messages")
        print("  - Market data entitlement errors")


if __name__ == "__main__":
    try:
        asyncio.run(test_with_logging())
    except KeyboardInterrupt:
        print("\n\nStopped by user")
