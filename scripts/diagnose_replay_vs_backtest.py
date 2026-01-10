#!/usr/bin/env python3
"""Diagnose differences between replay and backtest results.

This script helps identify why the same strategy run on the same data
produces different results in backtest vs replay modes.

Common issues:
1. Missing initial data (replay starts late)
2. Batching delays (replay groups bars before calling callbacks)
3. Different timing/ordering of bars
4. State differences (position tracking, daily resets, etc.)
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.logging import setup_normalized_logging


class ReplayBacktestDiagnostic:
    """Diagnostic tool for comparing replay vs backtest behavior."""

    def __init__(self):
        self.logger = setup_normalized_logging(
            app_name="diagnostic",
            log_dir="logs/diagnostics",
        )

    def analyze_backtest_trades(self, backtest_csv: str) -> pd.DataFrame:
        """Load and analyze backtest trades."""
        self.logger.info(f"Loading backtest trades from: {backtest_csv}")

        df = pd.read_csv(backtest_csv)
        df['entry_time'] = pd.to_datetime(df['entry_time'])
        df['exit_time'] = pd.to_datetime(df['exit_time'])

        self.logger.info(f"  Found {len(df)} trades")
        self.logger.info(f"  First trade entry: {df['entry_time'].min()}")
        self.logger.info(f"  Last trade exit: {df['exit_time'].max()}")

        return df

    def analyze_replay_logs(self, replay_log: str) -> dict:
        """Parse replay logs to extract trade information."""
        self.logger.info(f"Analyzing replay logs from: {replay_log}")

        with open(replay_log, 'r') as f:
            lines = f.readlines()

        # Extract key events
        first_bar = None
        first_entry = None
        positions_opened = []
        positions_closed = []

        for line in lines:
            # Find first bar processed
            if "Processing new bar at" in line and not first_bar:
                # Extract timestamp from log line
                timestamp_str = line.split("Processing new bar at ")[1].strip()
                first_bar = pd.to_datetime(timestamp_str)

            # Find entry signals
            if "Entry signal at" in line and not first_entry:
                timestamp_str = line.split("Entry signal at ")[1].strip()
                first_entry = pd.to_datetime(timestamp_str)

            # Track positions
            if "Position opened:" in line:
                # Extract position ID and cost
                parts = line.split("Position opened: ")
                if len(parts) > 1:
                    position_info = parts[1].strip()
                    positions_opened.append(position_info)

            if "Position closed:" in line:
                parts = line.split("Position closed: ")
                if len(parts) > 1:
                    position_info = parts[1].strip()
                    positions_closed.append(position_info)

        self.logger.info(f"  First bar processed: {first_bar}")
        self.logger.info(f"  First entry signal: {first_entry}")
        self.logger.info(f"  Positions opened: {len(positions_opened)}")
        self.logger.info(f"  Positions closed: {len(positions_closed)}")

        return {
            'first_bar': first_bar,
            'first_entry': first_entry,
            'positions_opened': len(positions_opened),
            'positions_closed': len(positions_closed),
        }

    def compare_timings(self, backtest_df: pd.DataFrame, replay_stats: dict):
        """Compare timing differences between backtest and replay."""
        self.logger.info("\n" + "="*70)
        self.logger.info("TIMING COMPARISON")
        self.logger.info("="*70)

        # Compare first entry times
        backtest_first_entry = backtest_df['entry_time'].min()
        replay_first_entry = replay_stats['first_entry']
        replay_first_bar = replay_stats['first_bar']

        self.logger.info(f"\n📊 First Events:")
        self.logger.info(f"  Backtest - First Entry:  {backtest_first_entry}")
        self.logger.info(f"  Replay   - First Bar:    {replay_first_bar}")
        self.logger.info(f"  Replay   - First Entry:  {replay_first_entry}")

        if replay_first_bar and backtest_first_entry:
            delay = (replay_first_bar - backtest_first_entry).total_seconds() / 60
            self.logger.info(f"\n⏰ Time Difference:")
            self.logger.info(f"  Replay started {delay:.1f} minutes AFTER backtest")

            if delay > 1:
                self.logger.warning(f"\n⚠️  PROBLEM DETECTED:")
                self.logger.warning(f"  Replay is missing the first {delay:.1f} minutes of data!")
                self.logger.warning(f"  This causes different trades because:")
                self.logger.warning(f"    - Different entry times")
                self.logger.warning(f"    - Different contracts selected")
                self.logger.warning(f"    - Different market conditions")

        # Compare trade counts
        self.logger.info(f"\n📈 Trade Counts:")
        self.logger.info(f"  Backtest: {len(backtest_df)} trades")
        self.logger.info(f"  Replay:   {replay_stats['positions_opened']} trades")

        if len(backtest_df) != replay_stats['positions_opened']:
            self.logger.warning(f"\n⚠️  Trade count mismatch!")
            self.logger.warning(f"  Difference: {len(backtest_df) - replay_stats['positions_opened']} trades")

    def diagnose_root_cause(self, backtest_df: pd.DataFrame, replay_stats: dict):
        """Identify the root cause of differences."""
        self.logger.info("\n" + "="*70)
        self.logger.info("ROOT CAUSE ANALYSIS")
        self.logger.info("="*70)

        issues_found = []

        # Issue 1: Missing initial data
        if replay_stats['first_bar'] and backtest_df['entry_time'].min():
            delay_minutes = (replay_stats['first_bar'] - backtest_df['entry_time'].min()).total_seconds() / 60
            if delay_minutes > 1:
                issues_found.append({
                    'issue': 'Missing Initial Data',
                    'severity': 'HIGH',
                    'description': f"Replay is missing first {delay_minutes:.0f} minutes of data",
                    'impact': 'Different entry times and contracts',
                    'fix': 'Check why RedisDataFeed receives first bar at 14:34 instead of 14:30'
                })

        # Issue 2: Trade count mismatch
        if len(backtest_df) != replay_stats['positions_opened']:
            issues_found.append({
                'issue': 'Trade Count Mismatch',
                'severity': 'HIGH',
                'description': f"Backtest has {len(backtest_df)} trades, Replay has {replay_stats['positions_opened']}",
                'impact': 'Different trading behavior',
                'fix': 'Investigate why trades are being skipped or added'
            })

        # Issue 3: Batching delays
        if replay_stats['first_entry'] and replay_stats['first_bar']:
            entry_delay = (replay_stats['first_entry'] - replay_stats['first_bar']).total_seconds() / 60
            if entry_delay > 1:
                issues_found.append({
                    'issue': 'Batching Delay',
                    'severity': 'MEDIUM',
                    'description': f"First entry is {entry_delay:.1f} minutes after first bar",
                    'impact': 'Delayed trade execution',
                    'fix': 'Check batching settings in RedisDataFeed (callback_batch_size, callback_batch_interval_ms)'
                })

        # Display issues
        if issues_found:
            self.logger.warning(f"\n🔍 Found {len(issues_found)} issue(s):\n")
            for i, issue in enumerate(issues_found, 1):
                self.logger.warning(f"{i}. {issue['issue']} ({issue['severity']})")
                self.logger.warning(f"   Description: {issue['description']}")
                self.logger.warning(f"   Impact: {issue['impact']}")
                self.logger.warning(f"   Fix: {issue['fix']}\n")
        else:
            self.logger.info("\n✅ No obvious issues found in timing analysis")

        return issues_found

    def generate_recommendations(self, issues: list):
        """Generate actionable recommendations."""
        if not issues:
            return

        self.logger.info("\n" + "="*70)
        self.logger.info("RECOMMENDATIONS")
        self.logger.info("="*70)

        self.logger.info("\n🔧 Immediate Actions:\n")

        for issue in issues:
            if issue['severity'] == 'HIGH':
                self.logger.info(f"  HIGH PRIORITY: {issue['issue']}")
                self.logger.info(f"    → {issue['fix']}\n")

        self.logger.info("📝 Investigation Steps:\n")
        self.logger.info("  1. Check RedisDataFeed batching logic (redis_data_feed.py:76-80)")
        self.logger.info("     - _callback_batch_size = 50")
        self.logger.info("     - _callback_batch_interval_ms = 500")
        self.logger.info("     - May be holding bars before calling strategy executor\n")

        self.logger.info("  2. Verify replay service publishes all bars (replay_service/publisher.py)")
        self.logger.info("     - Check if 14:30 bars are being published")
        self.logger.info("     - Check if bars are arriving in correct order\n")

        self.logger.info("  3. Check strategy_executor.on_bar() timing (strategy_executor.py:125)")
        self.logger.info("     - Verify it's called for every timestamp")
        self.logger.info("     - Check if any timestamps are being skipped\n")

    def run(self, backtest_csv: str, replay_log: str):
        """Run full diagnostic analysis."""
        self.logger.info("="*70)
        self.logger.info("REPLAY vs BACKTEST DIAGNOSTIC")
        self.logger.info("="*70)

        # Load data
        backtest_df = self.analyze_backtest_trades(backtest_csv)
        replay_stats = self.analyze_replay_logs(replay_log)

        # Compare
        self.compare_timings(backtest_df, replay_stats)

        # Diagnose
        issues = self.diagnose_root_cause(backtest_df, replay_stats)

        # Recommend
        self.generate_recommendations(issues)

        self.logger.info("\n" + "="*70)
        self.logger.info("DIAGNOSTIC COMPLETE")
        self.logger.info("="*70)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Diagnose differences between replay and backtest results"
    )
    parser.add_argument(
        "--backtest-csv",
        default="reports/backtests/coin_toss_trades_20260109_181246.csv",
        help="Path to backtest trades CSV"
    )
    parser.add_argument(
        "--replay-log",
        default="logs/live_trading_strategy_executor/live_trading_strategy_executor_20260109.log",
        help="Path to replay execution log"
    )

    args = parser.parse_args()

    # Run diagnostic
    diagnostic = ReplayBacktestDiagnostic()
    diagnostic.run(args.backtest_csv, args.replay_log)


if __name__ == "__main__":
    main()
