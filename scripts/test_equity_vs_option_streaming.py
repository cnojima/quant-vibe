"""Compare equity streaming vs option streaming to diagnose the issue."""

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


async def test_equity_vs_option():
    """Test if equity streaming works but option streaming doesn't."""

    print("="*70)
    print("EQUITY vs OPTION STREAMING COMPARISON")
    print(f"Time: {datetime.now()}")
    print("="*70)

    # Initialize client
    api_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    token_path = os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
    account_number = os.getenv("SCHWAB_ACCOUNT_NUMBER")

    print("\nInitializing Schwab client...")
    client = auth.client_from_token_file(token_path, api_key, app_secret)
    print("✅ Client initialized")

    # Get contracts
    print("\nGetting option contracts...")
    response = client.get_option_chain(
        "$SPX",
        contract_type=Client.Options.ContractType.CALL,
        strike_count=2,
    )

    option_symbols = []
    if response.status_code == 200:
        chain_data = response.json()
        if "callExpDateMap" in chain_data:
            for exp_date, strikes in list(chain_data["callExpDateMap"].items())[:1]:
                for strike, contract_list in list(strikes.items())[:2]:
                    for contract_data in contract_list:
                        symbol = contract_data.get("symbol", "")
                        if symbol.startswith("SPXW"):
                            option_symbols.append(symbol)
                            print(f"   Option: {symbol}")
                            if len(option_symbols) >= 2:
                                break
                    if len(option_symbols) >= 2:
                        break

    equity_symbols = ["$SPX", "SPY", "AAPL"]
    print(f"\nEquity symbols: {equity_symbols}")

    # Initialize streaming
    print("\nInitializing streaming client...")
    stream_client = StreamClient(client, account_id=account_number)

    # Login
    print("Logging in to WebSocket...")
    await stream_client.login()
    print("✅ WebSocket connected")

    # Track messages
    equity_messages = []
    option_messages = []

    # Test 1: Equity Level One
    print("\n" + "="*70)
    print("TEST 1: EQUITY LEVEL ONE QUOTES")
    print("="*70)

    async def equity_handler(msg):
        equity_messages.append(msg)
        service = msg.get('service')
        content = msg.get('content', [])
        print(f"📈 Equity message: service={service}, items={len(content)}")
        if content:
            item = content[0]
            symbol = item.get('key')
            last_price = item.get('lastPrice')
            print(f"   Symbol: {symbol}, Last: ${last_price}")

    stream_client.add_level_one_equity_handler(equity_handler)

    try:
        await stream_client.level_one_equity_subs(equity_symbols)
        print(f"✅ Subscribed to equity quotes: {equity_symbols}")
    except Exception as e:
        print(f"❌ Equity subscription failed: {e}")

    # Test 2: Option Level One
    print("\n" + "="*70)
    print("TEST 2: OPTION LEVEL ONE QUOTES")
    print("="*70)

    async def option_handler(msg):
        option_messages.append(msg)
        service = msg.get('service')
        content = msg.get('content', [])
        print(f"📊 Option message: service={service}, items={len(content)}")
        if content:
            item = content[0]
            symbol = item.get('key')
            bid = item.get('bidPrice')
            ask = item.get('askPrice')
            print(f"   Symbol: {symbol}, Bid: ${bid}, Ask: ${ask}")

    stream_client.add_level_one_option_handler(option_handler)

    try:
        await stream_client.level_one_option_subs(option_symbols)
        print(f"✅ Subscribed to option quotes: {option_symbols}")
    except Exception as e:
        print(f"❌ Option subscription failed: {e}")

    # Wait and monitor
    print("\n" + "="*70)
    print("MONITORING (30 seconds)")
    print("="*70)

    for i in range(30):
        await asyncio.sleep(1)
        if i % 10 == 0:
            print(f"\n[{i}s] Equity: {len(equity_messages)} messages, Option: {len(option_messages)} messages")

    # Results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)

    print(f"\nEquity streaming: {len(equity_messages)} messages")
    if equity_messages:
        print("  ✅ Equity streaming WORKS")
        print(f"  Sample message service: {equity_messages[0].get('service')}")
    else:
        print("  ❌ Equity streaming FAILED (no messages)")

    print(f"\nOption streaming: {len(option_messages)} messages")
    if option_messages:
        print("  ✅ Option streaming WORKS")
        print(f"  Sample message service: {option_messages[0].get('service')}")
    else:
        print("  ❌ Option streaming FAILED (no messages)")

    # Diagnosis
    print("\n" + "="*70)
    print("DIAGNOSIS")
    print("="*70)

    if len(equity_messages) > 0 and len(option_messages) == 0:
        print("\n⚠️  EQUITY WORKS but OPTIONS DON'T")
        print("\nRoot cause:")
        print("  Your Schwab account has streaming permissions for EQUITIES")
        print("  but NOT for OPTIONS data.")
        print("\nWhat this means:")
        print("  - Basic streaming is enabled (equity quotes work)")
        print("  - Options market data subscription is either:")
        print("    1. Not included in your subscription tier")
        print("    2. Requires separate options data permission")
        print("    3. Your account level doesn't include real-time options")
        print("\nSolution:")
        print("  1. Contact Schwab support: 1-800-435-4000")
        print("  2. Ask about 'real-time options streaming data'")
        print("  3. May require account upgrade or additional subscription")
        print("\n  OR use the polling approach (already working!)")

    elif len(equity_messages) == 0 and len(option_messages) == 0:
        print("\n⚠️  NO STREAMING DATA AT ALL")
        print("\nPossible causes:")
        print("  1. Market is closed")
        print("  2. Delayed data only (15-20 minute delay)")
        print("  3. Streaming not enabled for account")
        print("\nRecommendation: Use polling approach")

    elif len(equity_messages) > 0 and len(option_messages) > 0:
        print("\n✅ BOTH EQUITY AND OPTION STREAMING WORK!")
        print("\nYour streaming issue was temporary.")
        print("The original streaming collector should work now.")

    print("\n" + "="*70)


if __name__ == "__main__":
    try:
        asyncio.run(test_equity_vs_option())
    except KeyboardInterrupt:
        print("\n\nTest stopped by user")
