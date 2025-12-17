"""Test streaming with schwabdev library (not schwab-py).

This uses the schwabdev library which has different streaming implementation
than schwab-py. It offers both sync and async interfaces.

Requirements:
    pip install schwabdev

Usage:
    python scripts/test_schwabdev_streaming.py
"""

import sys
from pathlib import Path
import time
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Try to import schwabdev
try:
    import schwabdev
    SCHWABDEV_AVAILABLE = True
except ImportError:
    SCHWABDEV_AVAILABLE = False
    print("❌ schwabdev library not installed")
    print("   Install with: pip install schwabdev")
    sys.exit(1)


class StreamStats:
    """Track streaming statistics."""

    def __init__(self):
        self.messages = []
        self.counts_by_service = defaultdict(int)
        self.start_time = None
        self.last_message_time = None

    def add_message(self, msg):
        """Record a message."""
        if self.start_time is None:
            self.start_time = datetime.now()

        self.last_message_time = datetime.now()
        self.messages.append(msg)

        # Try to extract service type
        service = "unknown"
        if isinstance(msg, dict):
            service = msg.get('service', 'unknown')

        self.counts_by_service[service] += 1

    def print_stats(self):
        """Print current statistics."""
        total = len(self.messages)
        elapsed = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

        print(f"\n{'='*70}")
        print("STREAMING STATISTICS")
        print(f"{'='*70}")
        print(f"Total messages: {total}")
        print(f"Elapsed time: {elapsed:.1f}s")

        if total > 0:
            print(f"Messages per second: {total/elapsed:.2f}")
            print(f"\nBreakdown by service:")
            for service, count in self.counts_by_service.items():
                print(f"  {service}: {count}")

            if self.last_message_time:
                since_last = (datetime.now() - self.last_message_time).total_seconds()
                print(f"\nLast message: {since_last:.1f}s ago")
        else:
            print("No messages received")


def test_synchronous_streaming():
    """Test synchronous streaming with schwabdev.Stream."""

    print("="*70)
    print("SCHWABDEV SYNCHRONOUS STREAMING TEST")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Initialize client (schwabdev uses different auth)
    print("\n1. Initializing schwabdev client...")

    # Load credentials from environment
    import os
    from dotenv import load_dotenv
    load_dotenv()

    app_key = os.getenv("SCHWAB_API_KEY")
    app_secret = os.getenv("SCHWAB_API_SECRET")
    callback_url = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182/")

    # schwabdev uses SQLite database, not JSON like schwab-py
    tokens_db = "./tokens/schwabdev_tokens.db"

    if not app_key or not app_secret:
        print("   ✗ Missing SCHWAB_API_KEY or SCHWAB_API_SECRET in .env")
        return

    try:
        client = schwabdev.Client(
            app_key=app_key,
            app_secret=app_secret,
            callback_url=callback_url,
            tokens_db=tokens_db
        )
        print("   ✓ Client initialized")
    except Exception as e:
        print(f"   ✗ Failed to initialize client: {e}")
        print("\n   Note: schwabdev requires initial authentication")
        print("   If this is first run, you may need to authorize via browser")
        import traceback
        traceback.print_exc()
        return

    # Create streamer
    print("\n2. Creating streamer...")
    streamer = schwabdev.Stream(client)
    print("   ✓ Streamer created")

    # Set up message handler
    print("\n3. Setting up message handler...")
    stats = StreamStats()

    def message_handler(msg):
        """Handle incoming stream messages."""
        stats.add_message(msg)

        # Print first few messages
        if len(stats.messages) <= 5:
            print(f"\n📨 Message #{len(stats.messages)}:")
            print(f"   Type: {type(msg)}")
            if isinstance(msg, dict):
                print(f"   Service: {msg.get('service', 'N/A')}")
                print(f"   Keys: {list(msg.keys())}")
            else:
                print(f"   Content: {str(msg)[:200]}")

    print("   ✓ Handler ready")

    # Start stream
    print("\n4. Starting stream...")
    print("   Note: Stream runs in background thread")
    streamer.start(receiver=message_handler, daemon=True)
    print("   ✓ Stream started")

    # Wait a bit for stream to initialize
    time.sleep(2)

    # Test different services
    test_services = [
        {
            'name': 'Level 1 Equities (SPY)',
            'request': streamer.level_one_equities("SPY", "0,1,2,3,4,5,6,7,8"),
            'symbols': ['SPY']
        },
        {
            'name': 'Level 1 Futures (/ES)',
            'request': streamer.level_one_futures("/ES", "0,1,2,3,4,5"),
            'symbols': ['/ES']
        },
        {
            'name': 'Chart Equity (SPY 1min)',
            'request': streamer.chart_equity("SPY", "0,1,2,3,4,5,6,7,8"),
            'symbols': ['SPY']
        },
    ]

    for i, service in enumerate(test_services, 1):
        print(f"\n5.{i} Testing: {service['name']}")
        print(f"     Symbols: {service['symbols']}")

        try:
            # Send subscription
            streamer.send(service['request'])
            print(f"     ✓ Subscription sent")

            # Wait for data
            initial_count = len(stats.messages)
            print(f"     Waiting 15 seconds for data...")

            for sec in range(15):
                time.sleep(1)
                if sec % 5 == 4:
                    new_messages = len(stats.messages) - initial_count
                    print(f"     [{sec+1}s] New messages: {new_messages}")

            final_count = len(stats.messages) - initial_count
            if final_count > 0:
                print(f"     ✅ Received {final_count} messages")
            else:
                print(f"     ⚠️  No messages received")

            # Unsubscribe
            unsub_request = service['request'].replace('"command":"ADD"', '"command":"UNSUBS"')
            streamer.send(unsub_request)

        except Exception as e:
            print(f"     ✗ Error: {e}")

        # Small delay between tests
        time.sleep(2)

    # Print final stats
    print("\n" + "="*70)
    print("TEST COMPLETE")
    stats.print_stats()

    # Stop stream
    print("\n6. Stopping stream...")
    streamer.stop()
    print("   ✓ Stream stopped")

    # Analysis
    print("\n" + "="*70)
    print("ANALYSIS")
    print("="*70)

    if len(stats.messages) == 0:
        print("\n❌ NO MESSAGES RECEIVED")
        print("\nPossible reasons:")
        print("  1. Market is closed")
        print("  2. Account doesn't have streaming permissions")
        print("  3. Schwabdev authentication not properly configured")
        print("  4. Need to enable real-time data in Schwab account")
    else:
        print(f"\n✅ SUCCESS - Received {len(stats.messages)} messages!")
        print("\nWorking services:")
        for service, count in stats.counts_by_service.items():
            if count > 0:
                print(f"  ✓ {service}: {count} messages")


async def test_async_streaming():
    """Test async streaming with schwabdev.StreamAsync."""

    print("="*70)
    print("SCHWABDEV ASYNC STREAMING TEST")
    print("="*70)

    # Initialize async client
    print("\n1. Initializing async client...")
    try:
        client = schwabdev.ClientAsync()
        print("   ✓ Client initialized")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return

    # Create async streamer
    print("\n2. Creating async streamer...")
    streamer = schwabdev.StreamAsync(client)
    print("   ✓ Streamer created")

    # Set up handler
    stats = StreamStats()

    def message_handler(msg):
        stats.add_message(msg)
        if len(stats.messages) <= 3:
            print(f"📨 Message #{len(stats.messages)}")

    # Start stream
    print("\n3. Starting stream...")
    streamer.start(receiver=message_handler)
    print("   ✓ Stream started")

    # Subscribe to /ES futures
    print("\n4. Subscribing to /ES futures...")
    await streamer.send(streamer.level_one_futures("/ES", "0,1,2,3,4,5"))
    print("   ✓ Subscribed")

    # Wait
    print("\n5. Waiting 30 seconds...")
    import asyncio
    for i in range(6):
        await asyncio.sleep(5)
        print(f"   [{(i+1)*5}s] Messages: {len(stats.messages)}")

    # Stop
    print("\n6. Stopping...")
    streamer.stop()

    stats.print_stats()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--async",
        action="store_true",
        dest="use_async",
        help="Use async streaming instead of sync"
    )
    args = parser.parse_args()

    try:
        if args.use_async:
            import asyncio
            asyncio.run(test_async_streaming())
        else:
            test_synchronous_streaming()
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
