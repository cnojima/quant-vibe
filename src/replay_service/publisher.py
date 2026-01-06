"""Publisher for replay service - publishes bars to Redis with timing control."""

import logging
import time
from datetime import datetime
from typing import List, Dict

from quant_vibe.messaging import RedisMessageBroker, Topic
from quant_vibe.models import OptionsBar, UnderlyingBar


logger = logging.getLogger(__name__)


class ReplayPublisher:
    """Publishes historical bars to Redis with timing control."""

    def __init__(
        self,
        message_broker: RedisMessageBroker,
        speed: float = 1.0,
        preserve_timestamps: bool = False,
    ):
        """Initialize replay publisher.

        Args:
            message_broker: Redis message broker
            speed: Speed multiplier (1.0 = real-time, 10.0 = 10x faster, 0 = instant)
            preserve_timestamps: If True, keeps original timestamps; if False, shifts to "now"
        """
        self.message_broker = message_broker
        self.speed = speed
        self.preserve_timestamps = preserve_timestamps
        self.published_count = 0
        self.start_time = None

    def publish_bars_at_timestamp(
        self,
        timestamp: datetime,
        options_bars: List[OptionsBar],
        underlying_bars: List[UnderlyingBar],
    ) -> int:
        """Publish all bars for a given timestamp.

        Args:
            timestamp: The timestamp for these bars
            options_bars: Options bars at this timestamp
            underlying_bars: Underlying bars at this timestamp

        Returns:
            Number of bars published
        """
        count = 0

        # Publish options bars
        for bar in options_bars:
            if bar.timestamp == timestamp:
                self.message_broker.publish(Topic.REPLAY_OPTIONS_BARS, bar.model_dump())
                count += 1

        # Publish underlying bars
        for bar in underlying_bars:
            if bar.timestamp == timestamp:
                self.message_broker.publish(Topic.REPLAY_UNDERLYING_BARS, bar.model_dump())
                count += 1

        self.published_count += count
        return count

    def replay_with_timing(
        self,
        timestamps: List[datetime],
        options_bars_by_time: Dict[datetime, List[OptionsBar]],
        underlying_bars_by_time: Dict[datetime, List[UnderlyingBar]],
    ):
        """Replay bars with timing control.

        Args:
            timestamps: Sorted list of unique timestamps
            options_bars_by_time: Dictionary mapping timestamp -> list of options bars
            underlying_bars_by_time: Dictionary mapping timestamp -> list of underlying bars
        """
        if not timestamps:
            logger.warning("No timestamps to replay")
            return

        self.start_time = time.time()
        logger.info(f"Starting replay with {len(timestamps)} timestamps at {self.speed}x speed...")

        if self.speed == 0:
            # Instant mode - publish all as fast as possible
            logger.info("  Mode: INSTANT (no delays)")
            for i, timestamp in enumerate(timestamps):
                options_bars = options_bars_by_time.get(timestamp, [])
                underlying_bars = underlying_bars_by_time.get(timestamp, [])

                count = self.publish_bars_at_timestamp(
                    timestamp, options_bars, underlying_bars
                )

                if (i + 1) % 100 == 0:
                    logger.info(
                        f"  [{i+1}/{len(timestamps)}] Published {self.published_count:,} bars"
                    )

        else:
            # Timed replay
            logger.info(f"  Mode: {self.speed}x real-time")

            # Track when we should be in the replay timeline
            first_timestamp = timestamps[0]
            replay_start = time.time()

            for i, timestamp in enumerate(timestamps):
                # Calculate how long we should have waited (in replay time)
                time_since_start = (timestamp - first_timestamp).total_seconds()
                adjusted_wait = time_since_start / self.speed

                # Calculate actual elapsed time
                actual_elapsed = time.time() - replay_start

                # Sleep if we're ahead of schedule
                sleep_time = adjusted_wait - actual_elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

                # Publish bars for this timestamp
                options_bars = options_bars_by_time.get(timestamp, [])
                underlying_bars = underlying_bars_by_time.get(timestamp, [])

                count = self.publish_bars_at_timestamp(
                    timestamp, options_bars, underlying_bars
                )

                # Log progress
                if (i + 1) % 10 == 0 or count > 0:
                    elapsed = time.time() - self.start_time
                    logger.info(
                        f"  [{i+1}/{len(timestamps)}] {timestamp} | "
                        f"Published {count} bars | "
                        f"Total: {self.published_count:,} | "
                        f"Elapsed: {elapsed:.1f}s"
                    )

        elapsed = time.time() - self.start_time
        logger.info(
            f"\n✅ Replay complete! Published {self.published_count:,} bars in {elapsed:.1f}s"
        )

    def get_stats(self) -> Dict[str, any]:
        """Get publisher statistics.

        Returns:
            Dictionary with stats (published_count, elapsed_time, etc.)
        """
        elapsed = time.time() - self.start_time if self.start_time else 0

        return {
            "published_count": self.published_count,
            "elapsed_time": elapsed,
            "speed": self.speed,
            "preserve_timestamps": self.preserve_timestamps,
        }
