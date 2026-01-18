"""Publisher for replay service - publishes bars to Redis with timing control."""

import os
import time
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv

from quant_vibe.messaging import RedisMessageBroker, Topic
from quant_vibe.models import OptionsBar, UnderlyingBar
from quant_vibe.logging import setup_normalized_logging

load_dotenv()
logger = setup_normalized_logging(app_name="replay", log_dir="logs/replay")


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
            speed: Speed multiplier (1.0 = real-time, 10.0 = 10x, 0 = instant)
            preserve_timestamps: Keep original timestamps if True
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
        """Publish all bars for a given timestamp."""
        count = 0

        # Publish matching options bars
        for bar in options_bars:
            if bar.timestamp == timestamp:
                self.message_broker.publish(Topic.REPLAY_OPTIONS_BARS, bar.model_dump())
                count += 1

        # Publish matching underlying bars
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
        """Replay bars with timing control."""
        if not timestamps:
            logger.warning("No timestamps to replay")
            return

        self.start_time = time.time()
        total_timestamps = len(timestamps)

        logger.info(f"Starting replay: {total_timestamps} timestamps at {self.speed}x speed")

        if self.speed == 0:
            self._replay_instant(timestamps, options_bars_by_time, underlying_bars_by_time)
        else:
            self._replay_timed(timestamps, options_bars_by_time, underlying_bars_by_time)

        self._log_completion()

    def _replay_instant(
        self,
        timestamps: List[datetime],
        options_bars_by_time: Dict[datetime, List[OptionsBar]],
        underlying_bars_by_time: Dict[datetime, List[UnderlyingBar]],
    ):
        """Replay all bars instantly without timing delays."""
        logger.info("Mode: INSTANT")

        for i, timestamp in enumerate(timestamps):
            options_bars = options_bars_by_time.get(timestamp, [])
            underlying_bars = underlying_bars_by_time.get(timestamp, [])

            self.publish_bars_at_timestamp(timestamp, options_bars, underlying_bars)

            if (i + 1) % 100 == 0:
                self._log_progress(i + 1, len(timestamps))

    def _replay_timed(
        self,
        timestamps: List[datetime],
        options_bars_by_time: Dict[datetime, List[OptionsBar]],
        underlying_bars_by_time: Dict[datetime, List[UnderlyingBar]],
    ):
        """Replay bars with realistic timing based on speed multiplier."""
        logger.info(f"Mode: {self.speed}x real-time")

        first_timestamp = timestamps[0]
        replay_start = time.time()

        for i, timestamp in enumerate(timestamps):
            # Calculate timing
            elapsed_in_data = (timestamp - first_timestamp).total_seconds()
            target_elapsed = elapsed_in_data / self.speed
            actual_elapsed = time.time() - replay_start

            # Sleep if ahead of schedule
            if target_elapsed > actual_elapsed:
                time.sleep(target_elapsed - actual_elapsed)

            # Publish bars
            options_bars = options_bars_by_time.get(timestamp, [])
            underlying_bars = underlying_bars_by_time.get(timestamp, [])

            count = self.publish_bars_at_timestamp(timestamp, options_bars, underlying_bars)

            # Log progress for debugging and monitoring
            if i < 10 or (i + 1) % 10 == 0 or count > 0:
                self._log_detailed_progress(i + 1, len(timestamps), timestamp, count)

    def _log_progress(self, current: int, total: int):
        """Log simple progress update."""
        logger.info(
            f"[{current}/{total}] Published {self.published_count:,} bars"
        )

    def _log_detailed_progress(
        self, current: int, total: int, timestamp: datetime, count: int
    ):
        """Log detailed progress with timing information."""
        elapsed = time.time() - self.start_time
        logger.info(
            f"[{current}/{total}] {timestamp} | "
            f"Published {count} bars | Total: {self.published_count:,} | "
            f"Elapsed: {elapsed:.1f}s"
        )

    def _log_completion(self):
        """Log completion statistics."""
        elapsed = time.time() - self.start_time
        logger.info(
            f"\nReplay complete: {self.published_count:,} bars in {elapsed:.1f}s"
        )

    def get_stats(self) -> Dict[str, any]:
        """Get publisher statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0

        return {
            "published_count": self.published_count,
            "elapsed_time": elapsed,
            "speed": self.speed,
            "preserve_timestamps": self.preserve_timestamps,
        }