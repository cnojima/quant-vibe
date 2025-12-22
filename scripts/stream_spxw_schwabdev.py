"""Stream SPXW options data using schwabdev and store in TimescaleDB.

This script is a simple entry point for the SPXW Options Streaming Service.

The service:
1. Connects to Schwab streaming using schwabdev library
2. Subscribes to SPXW options contracts (0-45 DTE, ±10% ATM)
3. Aggregates streaming quotes into 1-minute bars
4. Auto-refreshes OAuth tokens every 14 minutes
5. Enriches quotes with Greeks and contract details
6. Stores in TimescaleDB for backtesting

Usage:
    python scripts/stream_spxw_schwabdev.py

    # With specific DTE range
    python scripts/stream_spxw_schwabdev.py --max-dte 7

    # With wider strike range
    python scripts/stream_spxw_schwabdev.py --strike-range-pct 0.20

    # Custom aggregate interval
    python scripts/stream_spxw_schwabdev.py --aggregate-interval 300  # 5-min bars
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from streaming_service import StreamingService, StreamingConfig


def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(description="Stream SPXW options data")

    parser.add_argument(
        "--max-dte",
        type=int,
        default=45,
        help="Maximum days to expiration (default: 45)"
    )

    parser.add_argument(
        "--min-dte",
        type=int,
        default=0,
        help="Minimum days to expiration (default: 0)"
    )

    parser.add_argument(
        "--strike-range-pct",
        type=float,
        default=0.10,
        help="Strike range as percentage of underlying (default: 0.10 = ±10%%)"
    )

    parser.add_argument(
        "--aggregate-interval",
        type=int,
        default=60,
        help="Seconds to aggregate into bars (default: 60 = 1min bars)"
    )

    parser.add_argument(
        "--token-refresh-minutes",
        type=int,
        default=14,
        help="Minutes between token refreshes (default: 14)"
    )

    args = parser.parse_args()

    # Create configuration
    config = StreamingConfig(
        max_dte=args.max_dte,
        min_dte=args.min_dte,
        strike_range_pct=args.strike_range_pct,
        aggregate_interval_seconds=args.aggregate_interval,
        token_refresh_minutes=args.token_refresh_minutes,
    )

    # Create and start service
    service = StreamingService(config)
    service.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✅ Stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
