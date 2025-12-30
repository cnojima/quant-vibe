#!/usr/bin/env python3
"""Test heartbeat pub/sub flow."""

import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.messaging import RedisMessageBroker

def test_pubsub():
    """Test Redis pub/sub for heartbeats."""
    print("Testing Redis Pub/Sub for Heartbeats")
    print("=" * 70)

    # Create broker
    broker = RedisMessageBroker()
    print("✓ Redis broker created")

    # Test publish
    test_msg = {
        "service": "test",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "healthy",
        "metrics": {"uptime": 100}
    }

    broker.publish("heartbeat.test", test_msg)
    print("✓ Published test message to heartbeat.test")

    # Test subscribe
    received_messages = []

    def on_message(topic, message):
        print(f"✓ Received message on {topic}: {message}")
        received_messages.append((topic, message))

    broker.subscribe(["heartbeat.test"], callback=on_message)
    print("✓ Subscribed to heartbeat.test")

    # Publish another message
    test_msg2 = {
        "service": "test2",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "degraded",
    }

    broker.publish("heartbeat.test", test_msg2)
    print("✓ Published second test message")

    # Listen for a bit (non-blocking test)
    print("\nListening for messages for 5 seconds...")
    print("(Press Ctrl+C to stop)")

    try:
        # This will block - in production it runs in a thread
        import threading
        listener_thread = threading.Thread(target=broker.listen, daemon=True)
        listener_thread.start()

        time.sleep(5)

    except KeyboardInterrupt:
        pass

    print(f"\n\nReceived {len(received_messages)} messages")
    broker.close()
    print("✓ Broker closed")

if __name__ == "__main__":
    test_pubsub()
