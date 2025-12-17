"""Stream SPXW options data in real-time.

This script runs the real-time data collector which:
1. Connects to Schwab streaming API via websocket
2. Subscribes to SPXW option quotes (0-45 DTE, ±10% ATM strikes)
3. Aggregates 1-minute bars from quote updates
4. Stores bars with bid/ask/Greeks in TimescaleDB

Run with:
    python scripts/stream_spxw_realtime.py
"""

import sys
from pathlib import Path
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.realtime_collector import RealtimeOptionsCollector


async def main():
    """Main entry point."""

    print("="*70)
    print("SPXW REAL-TIME OPTIONS DATA STREAMING")
    print("="*70)
    print()
    print("Configuration:")
    print("  DTE Range: 0-5 days")
    print("  Strike Range: ±10% from ATM")
    print("  Bar Interval: 1 minute")
    print("  Data: OHLCV + Bid/Ask + Greeks")
    print()

    # Initialize collector
    collector = RealtimeOptionsCollector(
        max_dte=5,
        min_dte=0,
        strike_range_pct=0.10,
    )

    # Start streaming
    await collector.start_streaming()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Streaming stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
