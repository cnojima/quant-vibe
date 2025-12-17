#!/usr/bin/env python3
"""
Check for gaps in 1-minute options_bars data.

This utility connects to the TimescaleDB options_bars table and identifies
missing 1-minute bars during market hours (9:30 AM - 4:00 PM ET).

Usage:
    python scripts/check_options_gaps.py --date 2025-12-16
    python scripts/check_options_gaps.py --start 2025-12-15 --end 2025-12-16
    python scripts/check_options_gaps.py --last-24h
"""

import argparse
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import pandas as pd
import pytz
from tabulate import tabulate

from quant_vibe.data.timescale_store import TimescaleStore


class OptionsGapChecker:
    """Check for gaps in 1-minute options bars data."""

    # US market hours in ET timezone
    MARKET_OPEN = "09:30"
    MARKET_CLOSE = "16:00"

    def __init__(self):
        """Initialize the gap checker with TimescaleDB connection."""
        self.store = TimescaleStore()
        self.et_tz = pytz.timezone('America/New_York')

    def check_gaps(
        self,
        start_time: datetime,
        end_time: datetime,
        underlying_ticker: str = 'SPX',
        option_ticker: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Check for gaps in options bars data.

        Args:
            start_time: Start of time range to check
            end_time: End of time range to check
            underlying_ticker: Underlying ticker (default: SPX)
            option_ticker: Specific option ticker to check (optional)

        Returns:
            DataFrame with gap information (start_time, end_time, duration_minutes, option_ticker)
        """
        # Build query
        query = """
        SELECT
            timestamp,
            option_ticker,
            underlying_ticker
        FROM options_bars
        WHERE underlying_ticker = %s
            AND timestamp >= %s
            AND timestamp < %s
        """
        params = [underlying_ticker, start_time, end_time]

        if option_ticker:
            query += " AND option_ticker = %s"
            params.append(option_ticker)

        query += " ORDER BY timestamp ASC"

        # Execute query
        with self.store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()

        if not rows:
            print(f"⚠️  No data found for {underlying_ticker} between {start_time} and {end_time}")
            return pd.DataFrame(columns=['start_time', 'end_time', 'duration_minutes', 'option_ticker'])

        # Convert to DataFrame
        df = pd.DataFrame(rows, columns=['timestamp', 'option_ticker', 'underlying_ticker'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Find gaps
        gaps = []

        if option_ticker:
            # Check single ticker
            gaps.extend(self._find_gaps_for_ticker(df, option_ticker))
        else:
            # Check all tickers
            for ticker in df['option_ticker'].unique():
                ticker_df = df[df['option_ticker'] == ticker]
                gaps.extend(self._find_gaps_for_ticker(ticker_df, ticker))

        # Convert to DataFrame
        gaps_df = pd.DataFrame(gaps, columns=['start_time', 'end_time', 'duration_minutes', 'option_ticker'])

        return gaps_df

    def _find_gaps_for_ticker(self, df: pd.DataFrame, ticker: str) -> List[Tuple]:
        """
        Find gaps in data for a specific ticker.

        Args:
            df: DataFrame with timestamp column
            ticker: Option ticker

        Returns:
            List of tuples (start_time, end_time, duration_minutes, ticker)
        """
        gaps = []

        # Sort by timestamp
        df = df.sort_values('timestamp')
        timestamps = df['timestamp'].tolist()

        for i in range(len(timestamps) - 1):
            current = timestamps[i]
            next_ts = timestamps[i + 1]

            # Expected next timestamp (1 minute later)
            expected_next = current + timedelta(minutes=1)

            # Check if there's a gap
            if next_ts > expected_next:
                # Only consider gaps during market hours
                if self._is_market_hours_gap(current, next_ts):
                    gap_duration = (next_ts - current).total_seconds() / 60 - 1  # Subtract 1 for expected minute
                    gaps.append((
                        current + timedelta(minutes=1),  # Gap starts after current
                        next_ts,  # Gap ends at next timestamp
                        gap_duration,
                        ticker
                    ))

        return gaps

    def _is_market_hours_gap(self, start_time: datetime, end_time: datetime) -> bool:
        """
        Check if a gap occurs during market hours.

        Market hours: 9:30 AM - 4:00 PM ET, Monday-Friday

        Args:
            start_time: Gap start time
            end_time: Gap end time

        Returns:
            True if gap is during market hours
        """
        # Convert to ET timezone
        if start_time.tzinfo is None:
            start_time = pytz.utc.localize(start_time).astimezone(self.et_tz)
        else:
            start_time = start_time.astimezone(self.et_tz)

        if end_time.tzinfo is None:
            end_time = pytz.utc.localize(end_time).astimezone(self.et_tz)
        else:
            end_time = end_time.astimezone(self.et_tz)

        # Check if weekday (0=Monday, 6=Sunday)
        if start_time.weekday() >= 5:  # Saturday or Sunday
            return False

        # Parse market hours
        market_open = start_time.replace(
            hour=int(self.MARKET_OPEN.split(':')[0]),
            minute=int(self.MARKET_OPEN.split(':')[1]),
            second=0,
            microsecond=0
        )
        market_close = start_time.replace(
            hour=int(self.MARKET_CLOSE.split(':')[0]),
            minute=int(self.MARKET_CLOSE.split(':')[1]),
            second=0,
            microsecond=0
        )

        # Check if gap overlaps with market hours
        return (start_time >= market_open and start_time < market_close) or \
               (end_time > market_open and end_time <= market_close)

    def print_summary(self, gaps_df: pd.DataFrame):
        """
        Print a summary of gaps found.

        Args:
            gaps_df: DataFrame with gap information
        """
        if gaps_df.empty:
            print("✅ No gaps found in the data!")
            return

        print(f"\n⚠️  Found {len(gaps_df)} gaps in the data:\n")

        # Format for display
        display_df = gaps_df.copy()
        display_df['start_time'] = display_df['start_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        display_df['end_time'] = display_df['end_time'].dt.strftime('%Y-%m-%d %H:%M:%S')
        display_df['duration_minutes'] = display_df['duration_minutes'].astype(int)

        # Print table
        print(tabulate(display_df, headers='keys', tablefmt='grid', showindex=False))

        # Print statistics
        print(f"\n📊 Gap Statistics:")
        print(f"   Total gaps: {len(gaps_df)}")
        print(f"   Total missing minutes: {gaps_df['duration_minutes'].sum():.0f}")
        print(f"   Average gap duration: {gaps_df['duration_minutes'].mean():.1f} minutes")
        print(f"   Max gap duration: {gaps_df['duration_minutes'].max():.0f} minutes")
        print(f"   Unique tickers affected: {gaps_df['option_ticker'].nunique()}")

    def get_data_summary(
        self,
        start_time: datetime,
        end_time: datetime,
        underlying_ticker: str = 'SPX',
    ):
        """
        Get a summary of available data in the time range.

        Args:
            start_time: Start of time range
            end_time: End of time range
            underlying_ticker: Underlying ticker
        """
        query = """
        SELECT
            COUNT(*) as total_bars,
            COUNT(DISTINCT option_ticker) as unique_tickers,
            MIN(timestamp) as earliest_bar,
            MAX(timestamp) as latest_bar,
            COUNT(DISTINCT DATE(timestamp)) as trading_days
        FROM options_bars
        WHERE underlying_ticker = %s
            AND timestamp >= %s
            AND timestamp < %s
        """

        with self.store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, [underlying_ticker, start_time, end_time])
                result = cur.fetchone()

        if result[0] == 0:
            print(f"⚠️  No data found for {underlying_ticker}")
            return

        print(f"\n📈 Data Summary for {underlying_ticker}:")
        print(f"   Time range: {start_time} to {end_time}")
        print(f"   Total bars: {result[0]:,}")
        print(f"   Unique option tickers: {result[1]:,}")
        print(f"   Earliest bar: {result[2]}")
        print(f"   Latest bar: {result[3]}")
        print(f"   Trading days: {result[4]}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Check for gaps in 1-minute options bars data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check specific date
  python scripts/check_options_gaps.py --date 2025-12-16

  # Check date range
  python scripts/check_options_gaps.py --start 2025-12-15 --end 2025-12-16

  # Check last 24 hours
  python scripts/check_options_gaps.py --last-24h

  # Check specific option ticker
  python scripts/check_options_gaps.py --date 2025-12-16 --ticker SPXW251216C06050000
        """
    )

    time_group = parser.add_mutually_exclusive_group(required=True)
    time_group.add_argument('--date', type=str, help='Check specific date (YYYY-MM-DD)')
    time_group.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    time_group.add_argument('--last-24h', action='store_true', help='Check last 24 hours')

    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD), required with --start')
    parser.add_argument('--ticker', type=str, help='Specific option ticker to check')
    parser.add_argument('--underlying', type=str, default='SPX', help='Underlying ticker (default: SPX)')

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Parse time range
    et_tz = pytz.timezone('America/New_York')

    if args.last_24h:
        end_time = datetime.now(et_tz)
        start_time = end_time - timedelta(hours=24)
    elif args.date:
        start_time = et_tz.localize(datetime.strptime(args.date, '%Y-%m-%d'))
        end_time = start_time + timedelta(days=1)
    else:
        if not args.end:
            print("Error: --end is required when using --start")
            return
        start_time = et_tz.localize(datetime.strptime(args.start, '%Y-%m-%d'))
        end_time = et_tz.localize(datetime.strptime(args.end, '%Y-%m-%d'))

    # Convert to UTC for database query
    start_time_utc = start_time.astimezone(pytz.utc)
    end_time_utc = end_time.astimezone(pytz.utc)

    print(f"🔍 Checking options bars data for gaps...")
    print(f"   Time range: {start_time} to {end_time} ET")
    if args.ticker:
        print(f"   Option ticker: {args.ticker}")
    print(f"   Underlying: {args.underlying}")

    # Create checker and run
    checker = OptionsGapChecker()

    # Get data summary
    checker.get_data_summary(start_time_utc, end_time_utc, args.underlying)

    # Check for gaps
    gaps_df = checker.check_gaps(
        start_time_utc,
        end_time_utc,
        args.underlying,
        args.ticker
    )

    # Print results
    checker.print_summary(gaps_df)


if __name__ == '__main__':
    main()
