#!/usr/bin/env python3
"""Analyze slippage from paper trading fills.

This script analyzes slippage between expected and actual fills from paper trading,
providing insights to improve backtest accuracy.

Usage:
    # Analyze all filled orders
    python scripts/analyze_slippage.py

    # Analyze specific date range
    python scripts/analyze_slippage.py --start 2025-12-01 --end 2025-12-31

    # Analyze specific strategy
    python scripts/analyze_slippage.py --strategy bullish_vertical_put

    # Get recommended slippage adjustments for backtests
    python scripts/analyze_slippage.py --recommendations

    # Export to JSON
    python scripts/analyze_slippage.py --output slippage_report.json
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
import json
from datetime import datetime
from quant_vibe.analytics import SlippageAnalyzer


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze slippage from paper trading fills"
    )

    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD)"
    )

    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD)"
    )

    parser.add_argument(
        "--strategy",
        type=str,
        help="Filter by strategy name"
    )

    parser.add_argument(
        "--recommendations",
        action="store_true",
        help="Get recommended slippage adjustments for backtests"
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Output file for JSON report (default: print to console)"
    )

    parser.add_argument(
        "--db-profile",
        type=str,
        choices=['local', 'remote'],
        help="Database profile to use (default: auto-detect from USE_REMOTE_TIMESCALE)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Parse dates
    start_date = None
    end_date = None

    if args.start:
        try:
            start_date = datetime.strptime(args.start, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Invalid start date: {args.start} (use YYYY-MM-DD)")
            return 1

    if args.end:
        try:
            end_date = datetime.strptime(args.end, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Invalid end date: {args.end} (use YYYY-MM-DD)")
            return 1

    # Initialize analyzer
    print("🔍 Initializing SlippageAnalyzer...")

    with SlippageAnalyzer(db_profile=args.db_profile) as analyzer:
        if args.recommendations:
            # Get recommendations
            print("\n📊 Calculating recommended slippage adjustments...")
            recommendations = analyzer.get_recommended_slippage_adjustments(
                start_date=start_date,
                end_date=end_date
            )

            if 'error' in recommendations:
                print(f"\n❌ {recommendations['error']}")
                return 1

            # Print recommendations
            print("\n" + "="*70)
            print("RECOMMENDED SLIPPAGE ADJUSTMENTS FOR BACKTEST ENGINE")
            print("="*70)

            for dte_bucket, params in recommendations.items():
                print(f"\n{dte_bucket}:")
                print(f"  Mean Slippage: {params['mean_slippage_pct']*100:.2f}%")
                print(f"  Std Dev: {params['std_slippage_pct']*100:.2f}%")
                print(f"  Sample Size: {params['num_orders']} orders")
                print(f"  Confidence: {params['confidence']}")

            print("\n" + "="*70)
            print("\nTo use these values, update the _get_slippage_model() method")
            print("in src/live_trading_service/order_manager.py")
            print("="*70)

            # Save to file if requested
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(recommendations, f, indent=2)
                print(f"\n✅ Recommendations saved to: {args.output}")

        else:
            # Generate full report
            if args.output:
                # Generate JSON report
                print("\n📊 Generating slippage report...")
                report = analyzer.generate_summary_report(
                    start_date=start_date,
                    end_date=end_date,
                    strategy_name=args.strategy
                )

                # Save to file
                with open(args.output, 'w') as f:
                    json.dump(report, f, indent=2, default=str)

                print(f"\n✅ Report saved to: {args.output}")

            else:
                # Print formatted report
                analyzer.print_summary_report(
                    start_date=start_date,
                    end_date=end_date,
                    strategy_name=args.strategy
                )

    return 0


if __name__ == "__main__":
    sys.exit(main())
