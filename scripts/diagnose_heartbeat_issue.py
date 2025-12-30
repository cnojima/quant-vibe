#!/usr/bin/env python3
"""
Diagnostic script to identify the heartbeat listener issue.

This script will:
1. Subscribe to heartbeat topics
2. Monitor what messages are being received
3. Show the exact message format
4. Compare with what the listener expects
"""

import sys
import time
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.messaging import RedisMessageBroker
import redis


def diagnose_heartbeat_messages():
    """Diagnose what's happening with heartbeat messages."""
    print("=" * 70)
    print("Heartbeat Message Diagnostic Tool")
    print("=" * 70)
    print()

    # Create broker
    broker = RedisMessageBroker()
    print("✓ Connected to Redis")
    print()

    # Also create a raw Redis client for comparison
    raw_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    raw_pubsub = raw_client.pubsub()

    # Subscribe to heartbeat topics
    topics = [
        "heartbeat.token_service",
        "heartbeat.streaming",
        "heartbeat.live_trading",
    ]

    print("Subscribing to topics:")
    for topic in topics:
        print(f"  - {topic}")
    print()

    # Subscribe with raw client
    raw_pubsub.subscribe(*topics)

    # Consume subscription confirmations
    for _ in topics:
        msg = raw_pubsub.get_message(timeout=1.0)
        if msg and msg['type'] == 'subscribe':
            print(f"✓ Raw client subscribed to: {msg.get('channel')}")

    print()
    print("Listening for heartbeat messages...")
    print("(Will listen for 60 seconds, press Ctrl+C to stop)")
    print()

    received_count = 0
    start_time = time.time()
    timeout = 60.0

    try:
        while time.time() - start_time < timeout:
            # Get message from raw Redis client
            msg = raw_pubsub.get_message(timeout=0.1)

            if msg and msg['type'] == 'message':
                received_count += 1
                print(f"\n[Message #{received_count}] Received on channel: {msg['channel']}")
                print(f"Message type: {msg['type']}")
                print(f"Raw data type: {type(msg['data'])}")
                print(f"Raw data: {msg['data']}")
                print()

                # Try to parse as JSON
                try:
                    parsed = json.loads(msg['data'])
                    print("✓ Successfully parsed as JSON:")
                    print(json.dumps(parsed, indent=2))
                    print()

                    # Check if it has the envelope format
                    if 'topic' in parsed and 'data' in parsed:
                        print("✓ Has envelope format (topic + data)")
                        print(f"  Envelope topic: {parsed['topic']}")
                        print(f"  Inner data: {json.dumps(parsed['data'], indent=4)}")
                    else:
                        print("⚠  NO envelope format (direct payload)")
                        print("  This is the problem! Messages should have 'topic' and 'data' fields")
                    print()

                except json.JSONDecodeError as e:
                    print(f"✗ Failed to parse JSON: {e}")
                    print()

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopped by user")

    print()
    print("=" * 70)
    print(f"Summary: Received {received_count} messages in {time.time() - start_time:.1f} seconds")
    print("=" * 70)

    # Cleanup
    raw_pubsub.close()
    raw_client.close()
    broker.close()

    if received_count == 0:
        print()
        print("⚠  NO MESSAGES RECEIVED")
        print("   Possible causes:")
        print("   1. Services are not running (docker compose up -d)")
        print("   2. Services are not publishing heartbeats")
        print("   3. Redis pub/sub is not working")
        print()
        print("   Check services:")
        print("   - docker compose logs token_service | grep heartbeat")
        print("   - docker compose logs streaming | grep heartbeat")
        print("   - docker compose logs live_trading | grep heartbeat")
        print()


if __name__ == "__main__":
    try:
        diagnose_heartbeat_messages()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
