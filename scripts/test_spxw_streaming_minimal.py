"""Minimal test for SPXW streaming using schwabdev.

This mirrors the working schwabdev-stream.py pattern but for options.

Usage:
    python scripts/test_spxw_streaming_minimal.py
"""

import os
import sys
import schwabdev
import time
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def main():
    """Test basic SPXW options streaming."""

    print("="*70)
    print("MINIMAL SPXW STREAMING TEST")
    print(f"Time: {datetime.now()}")
    print("="*70)

    # Initialize client
    print("\n1. Initializing SchwabDev client...")

    client = schwabdev.Client(
        os.getenv("SCHWAB_API_KEY"),
        os.getenv("SCHWAB_API_SECRET"),
        os.getenv("SCHWAB_CALLBACK_URL"),
        tokens_db="tokens/schwabdev_tokens.db",
    )
    print("   ✓ Client initialized")

    # Get a few SPXW contracts to stream
    print("\n2. Fetching SPXW contracts...")
    try:
        response = client.option_chains("$SPX", strikeCount=5)
        chain = response.json()

        # Extract just a few SPXW symbols
        contracts = []
        for exp_type in ['callExpDateMap', 'putExpDateMap']:
            if exp_type not in chain:
                continue

            for exp_date, strikes in chain[exp_type].items():
                for strike, contract_list in strikes.items():
                    for contract in contract_list:
                        symbol = contract.get('symbol', '')
                        if 'SPXW' in symbol and len(contracts) < 10:
                            contracts.append(symbol)

                if len(contracts) >= 10:
                    break

            if len(contracts) >= 10:
                break

        print(f"   ✓ Found {len(contracts)} SPXW contracts")
        for i, c in enumerate(contracts[:5], 1):
            print(f"      {i}. {c}")
        if len(contracts) > 5:
            print(f"      ... and {len(contracts) - 5} more")

    except Exception as e:
        print(f"   ✗ Error fetching contracts: {e}")
        return

    if not contracts:
        print("   ✗ No contracts found")
        return

    # Create streamer
    print("\n3. Creating streamer...")
    streamer = schwabdev.Stream(client)
    print("   ✓ Streamer created")

    # Message handler
    message_count = [0]  # Use list to allow modification in closure

    def my_handler(message):
        message_count[0] += 1
        print(f"📨 Message #{message_count[0]}: {str(message)[:200]}")

    print("\n4. Starting stream...")
    streamer.start(my_handler)
    print("   ✓ Stream started")

    # Subscribe to first 5 contracts
    print("\n5. Subscribing to options...")
    symbols_str = ",".join(contracts[:5])

    # Subscribe to level one options
    # Fields: 0=symbol, 2=bid, 3=ask, 4=last, etc.
    streamer.send(
        streamer.level_one_options(symbols_str, "0,1,2,3,4,5,6,7,8,9")
    )
    print("   ✓ Subscription sent")

    # Wait for messages
    print("\n6. Waiting 60 seconds for data...")
    print("   Press Ctrl+C to stop early\n")

    try:
        for i in range(60):
            time.sleep(1)
            if i > 0 and i % 10 == 0:
                print(f"   [{i}s] Messages received: {message_count[0]}")
    except KeyboardInterrupt:
        print("\n   Stopped by user")

    print(f"\n7. Final count: {message_count[0]} messages")

    # Stop stream
    print("\n8. Stopping stream...")
    streamer.stop()
    print("   ✓ Stopped")

    # Result
    print("\n" + "="*70)
    if message_count[0] > 0:
        print(f"✅ SUCCESS - Received {message_count[0]} messages!")
    else:
        print("⚠️  No messages received")
        print("   This could mean:")
        print("   - Market is closed")
        print("   - SPXW symbols don't stream in real-time")
        print("   - Need to use different symbol format")
    print("="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✅ Stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
