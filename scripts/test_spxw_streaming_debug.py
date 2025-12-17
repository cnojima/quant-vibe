"""Debug version to see what messages we're actually getting.

Usage:
    python scripts/test_spxw_streaming_debug.py
"""

import os
import sys
from pathlib import Path
import time
import json
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import schwabdev
from dotenv import load_dotenv

load_dotenv()

def main():
    print("="*70)
    print("SPXW STREAMING DEBUG - Message Inspector")
    print(f"Started: {datetime.now()}")
    print("="*70)

    # Initialize client
    print("\n1. Initializing client...")
    client = schwabdev.Client(
        os.getenv("SCHWAB_API_KEY"),
        os.getenv("SCHWAB_API_SECRET"),
        os.getenv("SCHWAB_CALLBACK_URL"),
        tokens_db="tokens/schwabdev_tokens.db",
    )
    print("   ✓ Client ready")

    # Get a few SPXW contracts
    print("\n2. Fetching a few SPXW contracts...")
    try:
        response = client.quote("$SPX")
        spx_data = response.json()
        spx_price = spx_data["$SPX"]["quote"]["lastPrice"]
        print(f"   SPX: ${spx_price:.2f}")

        # Get option chain
        response = client.option_chains("$SPX", strikeCount=3)
        chain = response.json()

        contracts = []
        for exp_type in ['callExpDateMap', 'putExpDateMap']:
            if exp_type not in chain:
                continue

            for exp_date, strikes in chain[exp_type].items():
                for strike, contract_list in strikes.items():
                    for contract in contract_list:
                        symbol = contract.get('symbol', '')
                        if 'SPXW' in symbol and len(contracts) < 5:
                            contracts.append(symbol)
                if len(contracts) >= 5:
                    break
            if len(contracts) >= 5:
                break

        print(f"   Found {len(contracts)} contracts:")
        for c in contracts:
            print(f"      {c}")

    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return

    if not contracts:
        print("   ✗ No contracts")
        return

    # Create streamer and handler
    print("\n3. Setting up stream...")
    streamer = schwabdev.Stream(client)

    messages = []
    message_types = defaultdict(int)

    def handler(msg):
        messages.append(msg)

        # Print first 10 messages in detail
        if len(messages) <= 10:
            print(f"\n📨 Message #{len(messages)}:")
            print(f"   Type: {type(msg)}")

            if isinstance(msg, str):
                try:
                    data = json.loads(msg)
                    print(f"   Parsed as JSON")
                    if isinstance(data, dict):
                        print(f"   Keys: {list(data.keys())}")
                        service = data.get('service', 'N/A')
                        print(f"   Service: {service}")
                        message_types[service] += 1

                        # Print full content for first 5 messages
                        if len(messages) <= 5:
                            print(f"   Full content: {json.dumps(data, indent=2)[:500]}")

                        if 'content' in data:
                            content = data['content']
                            print(f"   Content type: {type(content)}")
                            if isinstance(content, list):
                                print(f"   Content length: {len(content)}")
                                if len(content) > 0:
                                    print(f"   First item keys: {list(content[0].keys())[:10]}")
                except:
                    print(f"   Raw string: {msg[:200]}")
            elif isinstance(msg, dict):
                print(f"   Dict keys: {list(msg.keys())}")
                service = msg.get('service', 'N/A')
                print(f"   Service: {service}")
                message_types[service] += 1
            else:
                print(f"   Content: {str(msg)[:200]}")

    streamer.start(handler)
    print("   ✓ Stream started")

    # Subscribe
    print("\n4. Subscribing to contracts...")
    symbols_str = ",".join(contracts)

    # Try subscription
    streamer.send(
        streamer.level_one_options(symbols_str, "0,1,2,3,4,5,6,7,8,9,10,11,12")
    )
    print("   ✓ Subscription sent")

    # Wait
    print("\n5. Waiting 30 seconds...")
    for i in range(30):
        time.sleep(1)
        if i > 0 and i % 10 == 9:
            print(f"   [{i+1}s] Messages: {len(messages)}")

    # Results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    print(f"Total messages: {len(messages)}")
    print(f"\nBreakdown by service:")
    for service, count in message_types.items():
        print(f"  {service}: {count}")

    if len(messages) > 10:
        print(f"\nMessages 11-{len(messages)} were not printed (only first 10 shown)")

    # Stop
    print("\n6. Stopping...")
    streamer.stop()
    print("   ✓ Stopped")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
