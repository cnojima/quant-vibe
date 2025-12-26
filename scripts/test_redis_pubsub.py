#!/usr/bin/env python3
"""
Test Redis pub/sub connectivity between streaming and live trading services.
This script helps diagnose why live_trading isn't receiving messages.
"""

import os
import sys
import time
import redis
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.messaging import RedisMessageBroker, Topic
from dotenv import load_dotenv

load_dotenv()

def test_redis_connection():
    """Test basic Redis connection."""
    print("\n=== Testing Redis Connection ===")

    try:
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=int(os.getenv("REDIS_DB", 0)),
            decode_responses=True
        )

        # Test ping
        if r.ping():
            print("✅ Redis connection successful")
            print(f"   Host: {r.connection_pool.connection_kwargs['host']}")
            print(f"   Port: {r.connection_pool.connection_kwargs['port']}")
            print(f"   DB: {r.connection_pool.connection_kwargs['db']}")
            return True
        else:
            print("❌ Redis ping failed")
            return False

    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def test_pubsub():
    """Test pub/sub functionality."""
    print("\n=== Testing Pub/Sub ===")

    try:
        broker = RedisMessageBroker()

        # Flag to track if message received
        received = []

        def callback(topic, data):
            print(f"✅ Received message on {topic}: {data}")
            received.append(data)

        # Subscribe
        print(f"Subscribing to {Topic.OPTIONS_BARS}...")
        broker.subscribe([Topic.OPTIONS_BARS], callback=callback)

        # Give subscription time to establish
        time.sleep(1)

        # Publish test message
        test_message = {
            "timestamp": "2025-12-26T15:30:00Z",
            "option_ticker": "SPXW251226C6000000",
            "close": 10.50,
            "volume": 100
        }

        print(f"Publishing test message to {Topic.OPTIONS_BARS}...")
        broker.publish(Topic.OPTIONS_BARS, test_message)

        # Listen for a short time
        print("Listening for messages (5 seconds)...")

        # Manual listen loop instead of broker.listen()
        pubsub = broker._pubsub
        for message in pubsub.listen():
            if message['type'] == 'message':
                print(f"   Raw message: {message}")

            # Exit after 5 seconds or when message received
            if received or time.time() > time.time() + 5:
                break

        if received:
            print(f"✅ Pub/sub working! Received {len(received)} message(s)")
            return True
        else:
            print("❌ No messages received in 5 seconds")
            return False

    except Exception as e:
        print(f"❌ Pub/sub test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_active_subscriptions():
    """Check what channels have active subscriptions."""
    print("\n=== Checking Active Subscriptions ===")

    try:
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=int(os.getenv("REDIS_DB", 0)),
            decode_responses=True
        )

        # Get pubsub channels
        channels = r.pubsub_channels(pattern="streaming.*")

        if channels:
            print(f"✅ Found {len(channels)} active channels:")
            for channel in channels:
                num_subs = r.pubsub_numsub(channel)[0][1]
                print(f"   {channel}: {num_subs} subscriber(s)")
        else:
            print("⚠️  No active streaming.* channels found")
            print("   This might be normal if no services are running")

        return True

    except Exception as e:
        print(f"❌ Failed to check subscriptions: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Redis Pub/Sub Diagnostic Tool")
    print("=" * 60)

    # Test 1: Connection
    if not test_redis_connection():
        print("\n❌ FAILED: Can't connect to Redis")
        print("   Make sure Redis is running (docker-compose up redis)")
        sys.exit(1)

    # Test 2: Active subscriptions
    check_active_subscriptions()

    # Test 3: Pub/sub
    if not test_pubsub():
        print("\n❌ FAILED: Pub/sub not working")
        print("   Possible issues:")
        print("   1. Redis not configured for pub/sub")
        print("   2. Network/firewall blocking")
        print("   3. Wrong Redis DB number")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)
    print("\nIf live_trading still shows 'Data feed is stale', check:")
    print("1. Is streaming_service actually publishing?")
    print("2. Is live_trading_service subscribing to the right topics?")
    print("3. Are both services using the same Redis DB?")

if __name__ == "__main__":
    main()
