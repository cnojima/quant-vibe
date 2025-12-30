#!/usr/bin/env python3
"""
Minimal test to see if we can consume Redis messages.
Run this while streaming service is publishing.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.messaging import RedisMessageBroker, Topic

def main():
    print("Creating Redis broker...")
    broker = RedisMessageBroker()

    message_count = 0

    def callback(topic, data):
        nonlocal message_count
        message_count += 1
        if message_count % 10 == 1:  # Print first and every 10th
            print(f"[{message_count}] Received on {topic}: {list(data.keys())}")

    print(f"Subscribing to {Topic.OPTIONS_BARS} and {Topic.UNDERLYING_BARS}...")
    broker.subscribe([Topic.OPTIONS_BARS, Topic.UNDERLYING_BARS], callback=callback)

    print("Polling for messages (30 seconds)...")
    start_time = time.time()

    while time.time() - start_time < 30:
        result = broker.get_message(timeout=0.1)

        if result:
            topic, data = result
            # Note: callback was already called by get_message()
            # So we don't need to call it again

        # Print stats every 5 seconds
        elapsed = time.time() - start_time
        if int(elapsed) % 5 == 0 and int(elapsed * 10) % 10 == 0:  # Avoid spam
            print(f"[{int(elapsed)}s] Received {message_count} messages so far")
            time.sleep(0.1)  # Avoid printing same second twice

    print(f"\nTest complete! Received {message_count} messages in 30 seconds")
    print(f"Rate: {message_count / 30:.1f} messages/second")

    broker.close()

if __name__ == "__main__":
    main()
