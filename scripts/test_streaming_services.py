"""Test different Schwab streaming services for options data."""

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


async def test_streaming_services():
    """Test all three option streaming services."""

    print("="*70)
    print("SCHWAB OPTION STREAMING SERVICES TEST")
    print(f"Time: {datetime.now()}")
    print("="*70)

    # Initialize client
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    account_number = os.getenv("SCHWAB_ACCOUNT_NUMBER")

    print("\n1. Initializing Schwab client...")
    client = auth.client_from_token_file(token_path, api_key, app_secret)
    print("✅ Client initialized")

    # Get a few contracts
    print("\n2. Getting option contracts...")
    response = client.get_option_chain(
        "$SPX",
        contract_type=Client.Options.ContractType.CALL,
        strike_count=3,
    )

    contracts = []
    if response.status_code == 200:
        chain_data = response.json()
        if "callExpDateMap" in chain_data:
            for exp_date, strikes in list(chain_data["callExpDateMap"].items())[:1]:
                for strike, contract_list in list(strikes.items())[:3]:
                    for contract_data in contract_list:
                        symbol = contract_data.get("symbol", "")
                        if symbol.startswith("SPXW"):
                            contracts.append(symbol)
                            print(f"   Contract: {symbol}")
                            if len(contracts) >= 3:
                                break
                    if len(contracts) >= 3:
                        break

    if not contracts:
        print("❌ No contracts found")
        return

    print(f"\n✅ Found {len(contracts)} test contracts")

    # Initialize streaming
    print("\n3. Initializing streaming client...")
    stream_client = StreamClient(client, account_id=account_number)

    # Login
    print("\n4. Logging in to WebSocket...")
    try:
        await stream_client.login()
        print("✅ WebSocket connected")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return

    # Test each service
    services_tested = {}

    # SERVICE 1: LEVEL_ONE_OPTION (most common for quotes)
    print("\n" + "="*70)
    print("TEST A: level_one_option_subs (Level 1 Option Quotes)")
    print("="*70)

    messages_a = []

    async def handler_a(msg):
        messages_a.append(msg)
        print(f"📨 [LEVEL_ONE_OPTION] Message received!")
        print(f"   Service: {msg.get('service')}")
        print(f"   Content items: {len(msg.get('content', []))}")
        if msg.get('content'):
            item = msg['content'][0]
            print(f"   First item key: {item.get('key')}")
            print(f"   Sample fields: {list(item.keys())[:5]}")

    stream_client.add_level_one_option_handler(handler_a)

    try:
        await stream_client.level_one_option_subs(contracts)
        print(f"✅ Subscribed to level_one_option")
        print("   Waiting 15 seconds for messages...")

        for i in range(15):
            await asyncio.sleep(1)
            if i % 5 == 0:
                print(f"   {i}s - Messages received: {len(messages_a)}")

        services_tested['level_one_option'] = len(messages_a)
        print(f"\n{'✅' if len(messages_a) > 0 else '❌'} level_one_option: {len(messages_a)} messages")

    except Exception as e:
        print(f"❌ level_one_option failed: {e}")
        services_tested['level_one_option'] = 0

    # SERVICE 2: OPTIONS_BOOK
    print("\n" + "="*70)
    print("TEST B: options_book_subs (Options Book)")
    print("="*70)

    messages_b = []

    async def handler_b(msg):
        messages_b.append(msg)
        print(f"📨 [OPTIONS_BOOK] Message received!")
        print(f"   Service: {msg.get('service')}")
        print(f"   Content items: {len(msg.get('content', []))}")
        if msg.get('content'):
            item = msg['content'][0]
            print(f"   First item key: {item.get('key')}")
            print(f"   Sample fields: {list(item.keys())[:5]}")

    stream_client.add_options_book_handler(handler_b)

    try:
        await stream_client.options_book_subs(contracts)
        print(f"✅ Subscribed to options_book")
        print("   Waiting 15 seconds for messages...")

        for i in range(15):
            await asyncio.sleep(1)
            if i % 5 == 0:
                print(f"   {i}s - Messages received: {len(messages_b)}")

        services_tested['options_book'] = len(messages_b)
        print(f"\n{'✅' if len(messages_b) > 0 else '❌'} options_book: {len(messages_b)} messages")

    except Exception as e:
        print(f"❌ options_book failed: {e}")
        services_tested['options_book'] = 0

    # SUMMARY
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)

    for service, count in services_tested.items():
        status = "✅ WORKING" if count > 0 else "❌ NO DATA"
        print(f"{status}: {service:20s} - {count} messages")

    print("\n" + "="*70)

    working_services = [s for s, c in services_tested.items() if c > 0]

    if working_services:
        print(f"✅ Found {len(working_services)} working service(s)!")
        print(f"\nWorking services: {', '.join(working_services)}")
        print(f"\nRecommendation: Use '{working_services[0]}' for real-time data collection")
    else:
        print("❌ NO STREAMING SERVICES WORKING")
        print("\nPossible issues:")
        print("1. Streaming permissions not enabled for account")
        print("2. Market data subscription level insufficient")
        print("3. Delayed data only (not real-time)")
        print("\nRecommendation: Contact Schwab support or use polling approach")

    print("="*70)


if __name__ == "__main__":
    try:
        asyncio.run(test_streaming_services())
    except KeyboardInterrupt:
        print("\n\nTest stopped by user")
