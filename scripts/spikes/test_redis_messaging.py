#!/usr/bin/env python3
"""Test Redis messaging system.

This script tests the pub/sub messaging between services.
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.messaging import RedisMessageBroker, Topic


def test_publish_subscribe():
    """Test basic pub/sub functionality."""
    print("="*70)
    print("Testing Redis Pub/Sub Messaging")
    print("="*70)
    print()

    # Create publisher
    print("Creating publisher...")
    publisher = RedisMessageBroker()
    print("✓ Publisher connected to Redis")
    print()

    # Create subscriber
    print("Creating subscriber...")
    subscriber = RedisMessageBroker()
    print("✓ Subscriber connected to Redis")
    print()

    # Track received messages
    received_messages = []

    def on_message(topic: Topic, data: dict):
        """Callback for received messages."""
        print(f"  📥 Received on {topic}: {data}")
        received_messages.append((topic, data))

    # Subscribe
    print(f"Subscribing to {Topic.OPTIONS_BARS} and {Topic.UNDERLYING_BARS}...")
    subscriber.subscribe(
        topics=[Topic.OPTIONS_BARS, Topic.UNDERLYING_BARS],
        callback=on_message
    )
    print("✓ Subscribed")
    print()

    # Give subscription time to register
    time.sleep(0.5)

    # Publish test messages
    print("Publishing test messages...")

    test_option_bar = {
        'option_ticker': 'SPXW251227P6000',
        'timestamp': datetime.now().isoformat(),
        'open': 1.50,
        'high': 1.55,
        'low': 1.48,
        'close': 1.52,
        'volume': 1000,
    }

    test_underlying_bar = {
        'underlying_ticker': 'SPX',
        'timestamp': datetime.now().isoformat(),
        'open': 6000.0,
        'high': 6005.0,
        'low': 5998.0,
        'close': 6002.0,
        'volume': 50000,
    }

    print(f"  📤 Publishing to {Topic.OPTIONS_BARS}...")
    success1 = publisher.publish(Topic.OPTIONS_BARS, test_option_bar)
    print(f"     {'✓' if success1 else '✗'} Published")

    print(f"  📤 Publishing to {Topic.UNDERLYING_BARS}...")
    success2 = publisher.publish(Topic.UNDERLYING_BARS, test_underlying_bar)
    print(f"     {'✓' if success2 else '✗'} Published")
    print()

    # Poll for messages
    print("Polling for messages (3 second timeout)...")
    timeout = time.time() + 3
    while time.time() < timeout:
        result = subscriber.get_message(timeout=0.1)
        if result:
            # Already handled by callback
            pass
        time.sleep(0.1)

    print()

    # Check results
    print("="*70)
    print("Test Results")
    print("="*70)
    print(f"Messages published: 2")
    print(f"Messages received: {len(received_messages)}")

    if len(received_messages) == 2:
        print("✅ SUCCESS: All messages received!")

        # Verify message contents
        topics_received = [topic for topic, _ in received_messages]
        if Topic.OPTIONS_BARS in topics_received and Topic.UNDERLYING_BARS in topics_received:
            print("✅ SUCCESS: Correct topics received!")
        else:
            print("❌ FAIL: Wrong topics received")
            return 1
    else:
        print("❌ FAIL: Not all messages received")
        return 1

    # Cleanup
    print()
    print("Cleaning up...")
    subscriber.close()
    publisher.close()
    print("✓ Closed connections")
    print()

    return 0


if __name__ == "__main__":
    try:
        exit_code = test_publish_subscribe()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
