#!/usr/bin/env python3

"""Replay historical market data for testing live trading.

This script replays historical market data from TimescaleDB through Redis,
allowing you to test live trading strategies after market hours without
polluting the database.

The replay service:
1. Loads historical bars from TimescaleDB
2. Publishes to Redis replay topics (replay.options_bars, replay.underlying_bars)
3. Does NOT write back to database
4. Supports timing control (real-time, accelerated, instant)

Usage:
    # Replay yesterday's market hours at real-time speed
    python scripts/run_replay.py --timeframe yesterday

    # Replay today at 10x speed
    python scripts/run_replay.py --timeframe today --speed 10

    # Replay last 1 hour as fast as possible
    python scripts/run_replay.py --timeframe last_1h --speed 0

    # Replay specific date
    python scripts/run_replay.py --timeframe 2025-01-03 --speed 5

    # Replay custom range
    python scripts/run_replay.py --timeframe "2025-01-03T14:00:00/2025-01-03T15:30:00"

Note: Make sure to configure live_trading to use replay mode:
    Set data_source.mode: "replay" in config/live_trading.yaml
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from replay_service.service import ReplayService
from quant_vibe.config.logging_config import setup_normalized_logging


def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(
        description="Replay historical market data for testing live trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --timeframe yesterday
  %(prog)s --timeframe today --speed 10
  %(prog)s --timeframe last_1h --speed 0
  %(prog)s --timeframe 2025-01-03 --speed 5
  %(prog)s --timeframe "2025-01-03T14:00:00/2025-01-03T15:30:00"

Timeframe formats:
  - "today"         Market hours today (9:30 AM - 4:00 PM ET)
  - "yesterday"     Market hours previous trading day
  - "last_1h"       Most recent 1 hour of data
  - "1h", "30m"     Short form for last N hours/minutes
  - "2025-01-03"    Specific date (market hours)
  - "START/END"     Exact ISO 8601 range
        """,
    )

    parser.add_argument(
        "--timeframe",
        type=str,
        default="yesterday",
        help='Timeframe to replay (default: "yesterday")',
    )

    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speed multiplier (1.0 = real-time, 10.0 = 10x faster, 0 = instant) (default: 1.0)",
    )

    parser.add_argument(
        "--preserve-timestamps",
        action="store_true",
        help="Keep original timestamps (default: shift to now)",
    )

    parser.add_argument(
        "--underlying",
        type=str,
        default="SPX",
        help="Underlying ticker (default: SPX)",
    )

    parser.add_argument(
        "--min-dte",
        type=int,
        default=0,
        help="Minimum days to expiration (default: 0)",
    )

    parser.add_argument(
        "--max-dte",
        type=int,
        default=45,
        help="Maximum days to expiration (default: 45)",
    )

    parser.add_argument(
        "--db-profile",
        type=str,
        choices=["local", "remote"],
        default=None,
        help="Database profile (default: auto from USE_REMOTE_TIMESCALE env var)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_normalized_logging(
        app_name="replay",
        log_level=args.log_level,
        log_dir="logs/replay",
    )

    # Create and run replay service
    try:
        service = ReplayService(
            timeframe=args.timeframe,
            speed=args.speed,
            preserve_timestamps=args.preserve_timestamps,
            underlying_ticker=args.underlying,
            min_dte=args.min_dte,
            max_dte=args.max_dte,
            db_profile=args.db_profile,
        )

        service.run()

    except KeyboardInterrupt:
        print("\n\n🛑 Replay interrupted by user")
        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Replay failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
