"""Main replay service orchestrator."""

import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Optional, Dict, List

from dotenv import load_dotenv

from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.messaging import RedisMessageBroker
from quant_vibe.models import OptionsBar, UnderlyingBar
from replay_service.data_loader import ReplayDataLoader
from replay_service.publisher import ReplayPublisher
from replay_service.timeframe import parse_timeframe


load_dotenv()
logger = logging.getLogger(__name__)


class ReplayService:
    """Replays historical market data through Redis for testing live trading.

    This service:
    1. Loads historical data from TimescaleDB
    2. Publishes to Redis replay topics (replay.options_bars, replay.underlying_bars)
    3. Does NOT write back to database (prevents pollution)
    4. Supports timing control (real-time, accelerated, instant)
    """

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
            timeframe: Timeframe to replay (e.g., "today", "yesterday", "last_1h", "2025-01-03")
            speed: Speed multiplier (1.0 = real-time, 10.0 = 10x faster, 0 = instant)
            preserve_timestamps: If True, keeps original timestamps; if False, shifts to "now"
            underlying_ticker: Underlying ticker (default: SPX)
            min_dte: Minimum days to expiration (default: 0)
            max_dte: Maximum days to expiration (default: 45)
            db_profile: Database profile ("local" or "remote", default: auto from env)
        """
        self.timeframe = timeframe
        self.speed = speed
        self.preserve_timestamps = preserve_timestamps
        self.underlying_ticker = underlying_ticker
        self.min_dte = min_dte
        self.max_dte = max_dte

        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.info("=" * 70)
        self.logger.info("REPLAY SERVICE")
        self.logger.info("=" * 70)
        self.logger.info(f"  Timeframe: {timeframe}")
        self.logger.info(f"  Speed: {speed}x")
        self.logger.info(f"  Preserve Timestamps: {preserve_timestamps}")
        self.logger.info(f"  Underlying: {underlying_ticker}")
        self.logger.info(f"  DTE Range: {min_dte} - {max_dte}")

        # Parse timeframe
        self.start_time, self.end_time = parse_timeframe(timeframe)
        self.logger.info(f"  Start: {self.start_time}")
        self.logger.info(f"  End: {self.end_time}")

        # Determine database profile
        if db_profile is None:
            use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"
            db_profile = "remote" if use_remote else "local"

        self.logger.info(f"  Database: {db_profile}")

        # Initialize TimescaleDB connection
        if db_profile == "remote":
            self.ts_store = TimescaleStore(
                host=os.getenv("REMOTE_TIMESCALE_HOST"),
                port=int(os.getenv("REMOTE_TIMESCALE_PORT", "5432")),
                database=os.getenv("REMOTE_TIMESCALE_DB"),
                user=os.getenv("REMOTE_TIMESCALE_USER"),
                password=os.getenv("REMOTE_TIMESCALE_PASSWORD"),
            )
        else:
            self.ts_store = TimescaleStore()

        # Initialize Redis message broker
        self.message_broker = RedisMessageBroker(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD"),
        )

        # Initialize components
        self.data_loader = ReplayDataLoader(self.ts_store)
        self.publisher = ReplayPublisher(
            self.message_broker,
            speed=speed,
            preserve_timestamps=preserve_timestamps,
        )

        self.logger.info("=" * 70)

    def run(self):
        """Run the replay service."""
        try:
            # 1. Load data
            self.logger.info("\n📊 Loading historical data...")
            options_bars, underlying_bars = self.data_loader.load_bars(
                start_time=self.start_time,
                end_time=self.end_time,
                underlying_ticker=self.underlying_ticker,
                min_dte=self.min_dte,
                max_dte=self.max_dte,
            )

            # 2. Organize by timestamp
            self.logger.info("\n🗂️  Organizing data by timestamp...")
            timestamps = self.data_loader.get_unique_timestamps(
                options_bars, underlying_bars
            )

            # Group bars by timestamp
            options_by_time: Dict[datetime, List[OptionsBar]] = defaultdict(list)
            underlying_by_time: Dict[datetime, List[UnderlyingBar]] = defaultdict(list)

            for bar in options_bars:
                options_by_time[bar.timestamp].append(bar)

            for bar in underlying_bars:
                underlying_by_time[bar.timestamp].append(bar)

            self.logger.info(f"  ✓ Found {len(timestamps)} unique timestamps")
            self.logger.info(
                f"  ✓ Contracts per timestamp: "
                f"{len(options_bars) / len(timestamps):.1f} avg"
            )

            # 3. Publish to Redis
            self.logger.info("\n📡 Publishing to Redis...")
            self.logger.info(f"  Topics: {', '.join(['replay.options_bars', 'replay.underlying_bars'])}")

            self.publisher.replay_with_timing(
                timestamps=timestamps,
                options_bars_by_time=options_by_time,
                underlying_bars_by_time=underlying_by_time,
            )

            # 4. Show stats
            stats = self.publisher.get_stats()
            self.logger.info("\n📈 Replay Statistics:")
            self.logger.info(f"  Total bars published: {stats['published_count']:,}")
            self.logger.info(f"  Elapsed time: {stats['elapsed_time']:.1f}s")
            self.logger.info(
                f"  Throughput: {stats['published_count'] / max(stats['elapsed_time'], 0.001):.1f} bars/sec"
            )

        except Exception as e:
            self.logger.error(f"\n❌ Error during replay: {e}")
            import traceback

            traceback.print_exc()
            raise

        finally:
            # Cleanup
            self.ts_store.close()
            self.message_broker.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup resources."""
        if hasattr(self, "ts_store"):
            self.ts_store.close()
        if hasattr(self, "message_broker"):
            self.message_broker.close()
