#!/usr/bin/env python3
"""
Test Redis consumption exactly as live_trading does it.
This mimics the RedisDataFeed implementation.
"""

import sys
import time
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.messaging import RedisMessageBroker, Topic

class TestRedisDataFeed:
    def __init__(self):
        self.broker = RedisMessageBroker()
        self._running = False
        self._thread = None
        self.message_count = 0
        self.last_update_time = None

    def start(self):
        print("Starting test feed...")
        self._running = True

        # Subscribe (same as live_trading)
        self.broker.subscribe(
            topics=[Topic.OPTIONS_BARS, Topic.UNDERLYING_BARS],
            callback=self._handle_message
        )

        # Start listener thread (same as live_trading)
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        print("✓ Test feed started")

    def _listen_loop(self):
        print("  [Thread] Starting listen loop...")
        poll_count = 0

        try:
            while self._running:
                result = self.broker.get_message(timeout=0.1)
                poll_count += 1

                if poll_count % 100 == 0:
                    print(f"  [Thread] Polled {poll_count} times, received {self.message_count} messages")

                if result:
                    topic, message_data = result
                    # get_message already called callback, but call again to match live_trading
                    self._handle_message(topic, message_data)

        except Exception as e:
            print(f"  [Thread] Error: {e}")
            import traceback
            traceback.print_exc()

        print(f"  [Thread] Loop ended. Polls: {poll_count}, Messages: {self.message_count}")

    def _handle_message(self, topic, message_data):
        self.message_count += 1
        self.last_update_time = datetime.now()

        if self.message_count % 10 == 1:
            print(f"  [Callback] Message #{self.message_count} on {topic}: {list(message_data.keys())[:5]}")

    def is_data_stale(self, timeout_seconds=300):
        if not self.last_update_time:
            return True
        elapsed = (datetime.now() - self.last_update_time).total_seconds()
        return elapsed > timeout_seconds

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.broker.close()

def main():
    print("=" * 70)
    print("Testing Live Trading Redis Integration")
    print("=" * 70)

    feed = TestRedisDataFeed()
    feed.start()

    print("\nMonitoring for 30 seconds...")
    print("(Streaming service should be publishing messages)")
    print()

    for i in range(30):
        time.sleep(1)

        # Check staleness (same as live_trading health check)
        if feed.is_data_stale(timeout_seconds=5):
            print(f"[{i+1}s] ⚠️  Data feed is STALE (no messages in 5s)")
        else:
            elapsed = (datetime.now() - feed.last_update_time).total_seconds()
            print(f"[{i+1}s] ✓ Data feed active (last update {elapsed:.1f}s ago, total: {feed.message_count})")

    print("\n" + "=" * 70)
    print(f"Test complete! Total messages received: {feed.message_count}")
    print("=" * 70)

    if feed.message_count == 0:
        print("\n❌ PROBLEM: No messages received!")
        print("   Possible causes:")
        print("   1. Streaming service not running")
        print("   2. Streaming service not publishing")
        print("   3. Redis connection issue")
        print("   4. Topic mismatch")
    else:
        print(f"\n✅ SUCCESS: Received {feed.message_count} messages in 30 seconds")
        print(f"   Rate: {feed.message_count / 30:.1f} messages/second")

    feed.stop()

if __name__ == "__main__":
    main()
