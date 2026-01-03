#!/usr/bin/env python3
"""Generate daily performance report.

Usage:
    python scripts/generate_daily_report.py --date 2025-12-31
    python scripts/generate_daily_report.py  # Uses today
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.reporting import DailyPerformanceReport
from quant_vibe.notifications import TradingNotifier
from live_trading_service.state_store import StateStore
from quant_vibe.utils import now_utc


def main():
    parser = argparse.ArgumentParser(description="Generate daily performance report")
    parser.add_argument(
        '--date',
        type=str,
        help='Report date (YYYY-MM-DD), defaults to today'
    )
    parser.add_argument(
        '--target',
        type=float,
        default=1780.0,
        help='Daily income target (default: $1,780)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='reports/daily',
        help='Output directory for reports'
    )
    parser.add_argument(
        '--send-notification',
        action='store_true',
        help='Send Pushover notification with summary'
    )
    args = parser.parse_args()

    # Parse date
    if args.date:
        report_date = datetime.strptime(args.date, '%Y-%m-%d')
    else:
        report_date = now_utc()

    print(f"Generating daily report for: {report_date.strftime('%Y-%m-%d')}")
    print("=" * 70)

    # Initialize reporter
    reporter = DailyPerformanceReport(
        target_daily_income=args.target,
        initial_capital=800000.0,
        max_daily_drawdown_pct=0.02
    )

    # Load trades from StateStore
    print("Loading trades from state store...")
    state_store = StateStore()

    try:
        # Get trades for the date
        trades = state_store.get_trades_for_date(report_date.date())

        if trades:
            import pandas as pd
            from decimal import Decimal

            # Convert Decimal to float for numeric fields
            for trade in trades:
                for key in ['entry_cost', 'exit_value', 'pnl']:
                    if key in trade and isinstance(trade[key], Decimal):
                        trade[key] = float(trade[key])

            trades_df = pd.DataFrame(trades)
            print(f"  Found {len(trades_df)} trades")
        else:
            print("  No trades found for this date")
            import pandas as pd
            trades_df = pd.DataFrame()

        # Generate report
        print("\nGenerating report...")
        report = reporter.generate_report(trades_df, report_date)

        # Display summary
        print("\n" + "=" * 70)
        print("DAILY PERFORMANCE SUMMARY")
        print("=" * 70)
        print(f"Date:             {report['date']}")
        print(f"Target:           ${report['target_pnl']:,.2f}")
        print(f"Actual P&L:       ${report['actual_pnl']:+,.2f}")
        print(f"Achievement:      {report['achievement_pct']:.1f}%")
        print(f"\nTrades:           {report['total_trades']}")
        print(f"  Winners:        {report['winning_trades']}")
        print(f"  Losers:         {report['losing_trades']}")
        print(f"  Win Rate:       {report['win_rate']:.1f}%")
        print(f"\nAverage Win:      ${report['avg_win']:,.2f}")
        print(f"Average Loss:     ${report['avg_loss']:,.2f}")
        print(f"Profit Factor:    {report['profit_factor']:.2f}")
        print(f"\nMax Drawdown:     ${report['max_drawdown']:,.2f} ({report['max_drawdown_pct']:.2f}%)")
        print(f"Risk Status:      {report['risk_metrics']['status'].upper()}")

        if report['risk_metrics']['warnings']:
            print(f"\n⚠️  WARNINGS:")
            for warning in report['risk_metrics']['warnings']:
                print(f"  • {warning}")

        # Strategy breakdown
        if report['by_strategy']:
            print(f"\n" + "-" * 70)
            print("STRATEGY BREAKDOWN")
            print("-" * 70)
            for strategy, metrics in report['by_strategy'].items():
                print(f"{strategy}:")
                print(f"  Trades:    {metrics['trades']}")
                print(f"  P&L:       ${metrics['pnl']:+,.2f}")
                print(f"  Win Rate:  {metrics['win_rate']:.1f}%")

        # Save report
        print(f"\n" + "=" * 70)
        print("Saving report...")
        output_dir = Path(args.output_dir)
        saved_files = reporter.save_report(report, output_dir)

        for format_type, file_path in saved_files.items():
            print(f"  ✓ Saved {format_type.upper()}: {file_path}")

        # Send notification
        if args.send_notification:
            print(f"\nSending Pushover notification...")
            notifier = TradingNotifier()
            if reporter.send_summary(report, notifier):
                print("  ✓ Notification sent")
            else:
                print("  ⚠️  Notification failed or disabled")

        print("\n" + "=" * 70)
        print("✅ Daily report generated successfully")
        print("=" * 70)

    except Exception as e:
        print(f"\n❌ Error generating report: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        state_store.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
