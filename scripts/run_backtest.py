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

    return parser.parse_args()


def main():
    """Main entry point."""
    # Parse arguments
    args = parse_args()

    # Print banner
    print_banner()

    try:
        # Initialize orchestrator
        orchestrator = BacktestOrchestrator(
            config_path=args.config,
            strategy_filter=args.strategy,
        )

        # Run backtests
        results = orchestrator.run()

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
