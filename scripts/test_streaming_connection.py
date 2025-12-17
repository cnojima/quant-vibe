"""Test Schwab streaming connection and diagnose issues."""

import sys
from pathlib import Path
import asyncio
import os
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schwab import auth
from schwab.streaming import StreamClient
from dotenv import load_dotenv

load_dotenv()


async def test_connection():
    """Test Schwab streaming connection step by step."""

    print("="*70)
    print("SCHWAB STREAMING CONNECTION TEST")
    print("="*70)
    print()

    # Step 1: Check environment variables
    print("Step 1: Checking environment variables...")
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    account_number = os.getenv("SCHWAB_ACCOUNT_NUMBER")

    print(f"  API Key: {'✅ Set' if api_key else '❌ Missing'}")
    print(f"  App Secret: {'✅ Set' if app_secret else '❌ Missing'}")
    print(f"  Token Path: {token_path}")
    print(f"  Account Number: {'✅ Set' if account_number else '❌ Missing'}")

    if not all([api_key, app_secret, account_number]):
        print("\n❌ Missing required environment variables")
        return

    # Step 2: Check token file
    print(f"\nStep 2: Checking token file...")
    if not Path(token_path).exists():
        print(f"  ❌ Token file not found at {token_path}")
        return
    else:
        print(f"  ✅ Token file exists")
        # Check token age
        token_stat = Path(token_path).stat()
        token_age = datetime.now().timestamp() - token_stat.st_mtime
        print(f"  Token age: {token_age / 3600:.1f} hours")
        if token_age > 7 * 24 * 3600:  # 7 days
            print(f"  ⚠️  Token might be expired (older than 7 days)")

    # Step 3: Initialize Schwab client
    print(f"\nStep 3: Initializing Schwab client...")
    try:
        client = auth.client_from_token_file(
            token_path,
            api_key,
            app_secret
        )
        print("  ✅ Schwab client initialized")
    except Exception as e:
        print(f"  ❌ Failed to initialize client: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 4: Test basic API call
    print(f"\nStep 4: Testing basic API call (get $SPX quote)...")
    try:
        response = client.get_quote("$SPX")
        if response.status_code == 200:
            quote_data = response.json()
            spx_price = quote_data.get("$SPX", {}).get("quote", {}).get("lastPrice")
            print(f"  ✅ API call successful")
            print(f"  SPX price: ${spx_price:.2f}" if spx_price else "  ⚠️  Could not extract price")
        else:
            print(f"  ❌ API call failed: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
    except Exception as e:
        print(f"  ❌ API call failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 5: Test option chain call
    print(f"\nStep 5: Testing option chain call...")
    try:
        from schwab.client import Client

        response = client.get_option_chain(
            "$SPX",
            contract_type=Client.Options.ContractType.ALL,
            strike_count=10,
            include_underlying_quote=True
        )

        if response.status_code == 200:
            chain_data = response.json()
            call_exps = len(chain_data.get('callExpDateMap', {}))
            put_exps = len(chain_data.get('putExpDateMap', {}))
            print(f"  ✅ Option chain call successful")
            print(f"  Call expirations: {call_exps}")
            print(f"  Put expirations: {put_exps}")

            # Count contracts
            total_contracts = 0
            if 'callExpDateMap' in chain_data:
                for exp_date, strikes in chain_data['callExpDateMap'].items():
                    for strike, contracts_list in strikes.items():
                        total_contracts += len(contracts_list)
            if 'putExpDateMap' in chain_data:
                for exp_date, strikes in chain_data['putExpDateMap'].items():
                    for strike, contracts_list in strikes.items():
                        total_contracts += len(contracts_list)

            print(f"  Total contracts: {total_contracts}")

        else:
            print(f"  ❌ Option chain call failed: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
    except Exception as e:
        print(f"  ❌ Option chain call failed: {e}")
        import traceback
        traceback.print_exc()

    # Step 6: Initialize streaming client
    print(f"\nStep 6: Initializing streaming client...")
    try:
        stream_client = StreamClient(client, account_id=account_number)
        print("  ✅ Streaming client initialized")
    except Exception as e:
        print(f"  ❌ Failed to initialize streaming client: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 7: Test WebSocket login
    print(f"\nStep 7: Testing WebSocket connection...")
    try:
        await stream_client.login()
        print("  ✅ WebSocket login successful")

        # Step 8: Test subscribing to a quote
        print(f"\nStep 8: Testing quote subscription...")

        # Simple handler to capture messages
        messages_received = []

        async def quote_handler(msg):
            messages_received.append(msg)
            print(f"  📨 Received message: {msg.get('service')} - {len(msg.get('content', []))} items")

        # Subscribe to SPX index quotes
        stream_client.add_level_one_equity_handler(quote_handler)
        await stream_client.level_one_equity_subs(["$SPX"])

        print("  ✅ Subscribed to $SPX quotes")
        print("  Waiting 10 seconds for messages...")

        # Wait for messages
        await asyncio.sleep(10)

        if messages_received:
            print(f"  ✅ Received {len(messages_received)} messages")
            print(f"  First message: {messages_received[0]}")
        else:
            print(f"  ⚠️  No messages received")
            print(f"  This could mean:")
            print(f"    - Market is closed")
            print(f"    - Streaming permissions not enabled for account")
            print(f"    - WebSocket connection issues")

    except Exception as e:
        print(f"  ❌ WebSocket test failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(test_connection())
