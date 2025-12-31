#!/usr/bin/env python3
"""Run backtests using the backtest orchestrator.

This script provides a unified interface for running backtests similar to
the live trading engine. Backtests are configured via YAML files.

Usage:
    # Run with default configuration
    python scripts/run_backtest.py

    # Run with custom configuration
    python scripts/run_backtest.py --config config/my_backtest.yaml

    # Run specific strategy only
    python scripts/run_backtest.py --strategy bullish_vertical_put

    # Combine options
    python scripts/run_backtest.py --config config/custom.yaml --strategy my_strategy

Examples:
    # Run all enabled strategies from default config
    python scripts/run_backtest.py

    # Run only the bullish vertical put strategy
    python scripts/run_backtest.py --strategy bullish_vertical_put

    # Use a custom config file
    python scripts/run_backtest.py --config config/my_aggressive_backtest.yaml

Configuration:
    Default config: config/backtest.yaml
    See config/backtest.yaml for all available options.
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from backtest import BacktestOrchestrator


def print_banner():
    """Print startup banner."""
    print("\n" + "=" * 70)
    print(" " * 20 + "BACKTEST ORCHESTRATOR")
    print("=" * 70)
    print()
    print("  Running historical backtests for configured strategies")
    print("  Results will be saved to the configured output directory")
    print()
    print("=" * 70)
    print()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run backtests with configuration-based strategy execution',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s
    Run all enabled strategies from default config

  %(prog)s --strategy bullish_vertical_put
    Run only the bullish vertical put strategy

  %(prog)s --config config/my_backtest.yaml
    Use custom configuration file

  %(prog)s --config config/custom.yaml --strategy my_strategy
    Custom config + specific strategy filter

For more information, see:
  - config/backtest.yaml (default configuration)
  - CLAUDE.md (architecture documentation)
        """
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config/backtest.yaml',
        help='Path to backtest configuration file (default: config/backtest.yaml)'
    )

    parser.add_argument(
        '--strategy',
        type=str,
        default=None,
        help='Run only this strategy (filters enabled strategies by name)'
    )

    parser.add_argument(
        '--start-date',
        type=str,
        default=None,
        help='Start date for backtest (YYYY-MM-DD format). Overrides config.'
    )

    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='End date for backtest (YYYY-MM-DD format). Overrides config.'
    )

    parser.add_argument(
        '--min-dte',
        type=int,
        default=None,
        help='Minimum days to expiration. Overrides config.'
    )

    parser.add_argument(
        '--max-dte',
        type=int,
        default=None,
        help='Maximum days to expiration. Overrides config.'
    )

    parser.add_argument(
        '--max-trades-daily',
        type=int,
        default=None,
        help='Maximum trades per day. Overrides config.'
    )

    parser.add_argument(
        '--initial-capital',
        type=float,
        default=None,
        help='Initial capital amount. Overrides config.'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    # Parse arguments
    args = parse_args()

    # Print banner
    print_banner()

    try:
        # Parse dates if provided
        start_date = None
        end_date = None
        if args.start_date and args.end_date:
            from datetime import datetime
            from quant_vibe.utils.datetime_utils import trading_day_to_utc

            # Parse YYYY-MM-DD format
            start_parts = args.start_date.split('-')
            end_parts = args.end_date.split('-')

            # Convert to market hours in UTC
            start_date, _ = trading_day_to_utc(
                int(start_parts[0]), int(start_parts[1]), int(start_parts[2])
            )
            _, end_date = trading_day_to_utc(
                int(end_parts[0]), int(end_parts[1]), int(end_parts[2])
            )

        # Initialize orchestrator
        orchestrator = BacktestOrchestrator(
            config_path=args.config,
            strategy_filter=args.strategy,
        )

        # Run backtests
        results = orchestrator.run(
            start_date=start_date,
            end_date=end_date,
            min_dte=args.min_dte,
            max_dte=args.max_dte,
            max_trades_daily=args.max_trades_daily,
            initial_capital=args.initial_capital,
        )

        # Exit with success
        print("\n✓ All backtests completed successfully\n")
        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Backtest interrupted by user (Ctrl+C)")
        print("Partial results may have been saved.\n")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n✗ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
