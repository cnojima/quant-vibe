#!/usr/bin/env python3
"""Run the live trading engine.

This script starts the live trading engine with the configured strategies.

Usage:
    # Run with default configuration
    python scripts/run_live_trading.py

    # Run with custom configuration
    python scripts/run_live_trading.py --config config/my_config.yaml

    # Run with specific log level
    python scripts/run_live_trading.py --log-level DEBUG

Safety:
    - The engine starts in PAPER TRADING mode by default
    - Change paper_trading to false in config only after thorough testing
    - Always monitor the first few trades closely
    - Use kill switch (Ctrl+C) if anything unexpected happens

Example:
    python scripts/run_live_trading.py
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.live import LiveTradingEngine


def print_banner():
    """Print startup banner."""
    print("\n" + "="*70)
    print(" "*15 + "LIVE TRADING ENGINE")
    print("="*70)
    print()
    print("  ⚠️  WARNING: Live trading involves real money and real risk")
    print("  ⚠️  Always start with paper trading mode")
    print("  ⚠️  Monitor closely and use stop-loss limits")
    print()
    print("  Press Ctrl+C at any time to stop")
    print()
    print("="*70)
    print()


def confirm_live_trading(engine: LiveTradingEngine) -> bool:
    """
    Confirm if user wants to proceed with live trading.

    Args:
        engine: Trading engine instance

    Returns:
        True if user confirms
    """
    if engine.paper_trading:
        print("✅ Running in PAPER TRADING mode (safe)")
        return True

    print("\n" + "⚠️ "*20)
    print("⚠️  LIVE TRADING MODE ENABLED")
    print("⚠️ "*20)
    print()
    print("You are about to start LIVE trading with REAL MONEY.")
    print()
    print("Have you:")
    print("  ✓ Thoroughly tested with paper trading?")
    print("  ✓ Verified your strategy parameters?")
    print("  ✓ Checked your risk limits?")
    print("  ✓ Confirmed your account has sufficient funds?")
    print()

    response = input("Type 'YES I AM READY' to proceed: ").strip()

    if response == "YES I AM READY":
        print()
        print("⚠️  Live trading confirmed. Proceeding...")
        return True
    else:
        print()
        print("❌ Confirmation failed. Exiting for safety.")
        print("   (Hint: Set paper_trading: true in config to run safely)")
        return False


def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(
        description="Run the live options trading engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default configuration
  python scripts/run_live_trading.py

  # Run with custom config
  python scripts/run_live_trading.py --config config/my_config.yaml

  # Run with debug logging
  python scripts/run_live_trading.py --log-level DEBUG

Safety Notes:
  - Always start with paper trading mode
  - Monitor the first few trades closely
  - Use Ctrl+C to stop immediately if needed
  - Check logs in logs/live_trading/
        """
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/live_trading.yaml",
        help="Path to configuration file (default: config/live_trading.yaml)"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level from config"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Initialize but don't start trading (for testing)"
    )

    args = parser.parse_args()

    # Print banner
    print_banner()

    # Initialize engine
    print("Initializing trading engine...")
    print(f"Configuration: {args.config}")
    print()

    try:
        engine = LiveTradingEngine(config_path=args.config)

        # Override log level if specified
        if args.log_level:
            engine.logger.setLevel(args.log_level)
            print(f"Log level: {args.log_level}")

        # Initialize components
        engine.initialize()

        # Dry run mode
        if args.dry_run:
            print("\n✅ Dry run complete. Engine initialized successfully.")
            print("   (Use without --dry-run to start trading)")
            return

        # Confirm if live trading
        if not confirm_live_trading(engine):
            return

        # Start trading
        print("\nStarting engine...")
        print()
        engine.start()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
