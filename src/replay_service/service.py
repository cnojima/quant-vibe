"""Main replay service orchestrator."""

import os
import traceback
from collections import defaultdict
from datetime import datetime
from typing import Optional, Dict, List

from dotenv import load_dotenv

from quant_vibe.logging import setup_normalized_logging
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.messaging import RedisMessageBroker
from quant_vibe.models import OptionsBar, UnderlyingBar
from .data_loader import ReplayDataLoader
from .publisher import ReplayPublisher
from .timeframe import parse_timeframe

load_dotenv()


class ReplayService:
    """Replays historical market data through Redis for testing live trading."""

    def __init__(
        self,
        timeframe: str = "yesterday",
        speed: float = 1.0,
        preserve_timestamps: bool = False,
        underlying_ticker: str = "SPX",
        min_dte: int = 0,
        max_dte: int = 45,
        db_profile: Optional[str] = None,
    ):
        """Initialize replay service.

        Args:
            timeframe: Timeframe to replay (e.g., "today", "yesterday", "last_1h")
            speed: Speed multiplier (1.0 = real-time, 10.0 = 10x, 0 = instant)
            preserve_timestamps: Keep original timestamps if True
            underlying_ticker: Underlying ticker (default: SPX)
            min_dte: Minimum days to expiration (default: 0)
            max_dte: Maximum days to expiration (default: 45)
            db_profile: Database profile ("local" or "remote")
        """
        self.timeframe = timeframe
        self.speed = speed
        self.preserve_timestamps = preserve_timestamps
        self.underlying_ticker = underlying_ticker
        self.min_dte = min_dte
        self.max_dte = max_dte

        # Setup logging
        self.logger = setup_normalized_logging(app_name="replay", log_dir="logs/replay")

        # Parse timeframe
        self.start_time, self.end_time = parse_timeframe(timeframe)

        # Log configuration
        self._log_configuration(db_profile)

        # Initialize connections
        self.ts_store = self._create_timescale_store(db_profile)
        self.message_broker = self._create_message_broker()

        # Initialize components
        self.data_loader = ReplayDataLoader(self.ts_store)
        self.publisher = ReplayPublisher(
            self.message_broker,
            speed=speed,
            preserve_timestamps=preserve_timestamps,
        )

    def _log_configuration(self, db_profile: Optional[str]):
        """Log service configuration."""
        self.logger.info("=" * 70)
        self.logger.info("REPLAY SERVICE")
        self.logger.info("=" * 70)
        self.logger.info(f"Timeframe: {self.timeframe}")
        self.logger.info(f"Speed: {self.speed}x")
        self.logger.info(f"Preserve Timestamps: {self.preserve_timestamps}")
        self.logger.info(f"Underlying: {self.underlying_ticker}")
        self.logger.info(f"DTE Range: {self.min_dte} - {self.max_dte}")
        self.logger.info(f"Start: {self.start_time}")
        self.logger.info(f"End: {self.end_time}")
        self.logger.info(f"Database: {self._get_db_profile(db_profile)}")
        self.logger.info("=" * 70)

    def _get_db_profile(self, db_profile: Optional[str]) -> str:
        """Determine database profile from environment or parameter."""
        if db_profile:
            return db_profile
        use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"
        return "remote" if use_remote else "local"

    def _create_timescale_store(self, db_profile: Optional[str]) -> TimescaleStore:
        """Create TimescaleDB connection based on profile."""
        profile = self._get_db_profile(db_profile)

        if profile == "remote":
            return TimescaleStore(
                host=os.getenv("REMOTE_TIMESCALE_HOST"),
                port=int(os.getenv("REMOTE_TIMESCALE_PORT", "5432")),
                database=os.getenv("REMOTE_TIMESCALE_DB"),
                user=os.getenv("REMOTE_TIMESCALE_USER"),
                password=os.getenv("REMOTE_TIMESCALE_PASSWORD"),
            )

        return TimescaleStore()

    def _create_message_broker(self) -> RedisMessageBroker:
        """Create Redis message broker from environment settings."""
        return RedisMessageBroker(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD"),
        )

    def run(self):
        """Run the replay service."""
        try:
            # Load historical data
            self.logger.info("\nLoading historical data...")
            options_bars, underlying_bars = self.data_loader.load_bars(
                start_time=self.start_time,
                end_time=self.end_time,
                underlying_ticker=self.underlying_ticker,
                min_dte=self.min_dte,
                max_dte=self.max_dte,
            )

            # Organize data by timestamp
            self.logger.info("\nOrganizing data by timestamp...")
            timestamps = self.data_loader.get_unique_timestamps(options_bars, underlying_bars)
            options_by_time, underlying_by_time = self._organize_bars_by_timestamp(
                options_bars, underlying_bars
            )

            self.logger.info(f"Found {len(timestamps)} unique timestamps")
            self.logger.info(
                f"Contracts per timestamp: {len(options_bars) / len(timestamps):.1f} avg"
            )

            # Publish to Redis
            self.logger.info("\nPublishing to Redis...")
            self.logger.info("Topics: replay.options_bars, replay.underlying_bars")

            self.publisher.replay_with_timing(
                timestamps=timestamps,
                options_bars_by_time=options_by_time,
                underlying_bars_by_time=underlying_by_time,
            )

            # Display statistics
            self._display_stats()

        except Exception as e:
            self.logger.error(f"\nError during replay: {e}")
            traceback.print_exc()
            raise
        finally:
            self._cleanup()

    def _organize_bars_by_timestamp(
        self, options_bars: List[OptionsBar], underlying_bars: List[UnderlyingBar]
    ) -> tuple[Dict[datetime, List[OptionsBar]], Dict[datetime, List[UnderlyingBar]]]:
        """Organize bars by timestamp for efficient publishing."""
        options_by_time = defaultdict(list)
        underlying_by_time = defaultdict(list)

        for bar in options_bars:
            options_by_time[bar.timestamp].append(bar)

        for bar in underlying_bars:
            underlying_by_time[bar.timestamp].append(bar)

        return options_by_time, underlying_by_time

    def _display_stats(self):
        """Display replay statistics."""
        stats = self.publisher.get_stats()
        self.logger.info("\nReplay Statistics:")
        self.logger.info(f"Total bars published: {stats['published_count']:,}")
        self.logger.info(f"Elapsed time: {stats['elapsed_time']:.1f}s")

        if stats['elapsed_time'] > 0:
            throughput = stats['published_count'] / stats['elapsed_time']
            self.logger.info(f"Throughput: {throughput:.1f} bars/sec")

    def _cleanup(self):
        """Clean up resources."""
        if hasattr(self, "ts_store"):
            self.ts_store.close()
        if hasattr(self, "message_broker"):
            self.message_broker.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        self._cleanup()