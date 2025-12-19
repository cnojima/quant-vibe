#!/usr/bin/env python3
"""
1-Minute Bar Sanity Check for Options Data

This utility connects to the TimescaleDB options_bars table and identifies
missing 1-minute bars during market hours (9:30 AM - 4:00 PM ET).

Usage:
    python data/schema/1-minute-sanity.py --date 2025-12-16
    python data/schema/1-minute-sanity.py --start 2025-12-15 --end 2025-12-16
    python data/schema/1-minute-sanity.py --last-24h
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

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
            start_time: Start of time range to check (UTC)
            end_time: End of time range to check (UTC)
            underlying_ticker: Underlying ticker (default: SPX)
            option_ticker: Specific option ticker to check (optional)

        Returns:
            DataFrame with gap information (start_time, end_time, duration_minutes, option_ticker)
        """
        # Ensure times are in UTC for database query
        if start_time.tzinfo is None:
            start_time = pytz.utc.localize(start_time)
        else:
            start_time = start_time.astimezone(pytz.utc)

        if end_time.tzinfo is None:
            end_time = pytz.utc.localize(end_time)
        else:
            end_time = end_time.astimezone(pytz.utc)

        # Build query - get unique timestamps first to check overall coverage
        timestamp_query = """
        SELECT DISTINCT timestamp
        FROM options_bars
        WHERE underlying_ticker = %s
            AND timestamp >= %s
            AND timestamp < %s
        ORDER BY timestamp ASC
        """

        with self.store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(timestamp_query, [underlying_ticker, start_time, end_time])
                timestamps = [row[0] for row in cur.fetchall()]

        if not timestamps:
            print(f"⚠️  No data found for {underlying_ticker} between {start_time} and {end_time}")
            return pd.DataFrame(columns=['start_time', 'end_time', 'duration_minutes', 'option_ticker'])

        # Check for overall time gaps (across all tickers)
        time_gaps = self._find_time_gaps(timestamps)

        # If checking specific ticker, also check per-ticker gaps
        if option_ticker:
            query = """
            SELECT timestamp, option_ticker
            FROM options_bars
            WHERE underlying_ticker = %s
                AND option_ticker = %s
                AND timestamp >= %s
                AND timestamp < %s
            ORDER BY timestamp ASC
            """

            with self.store.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, [underlying_ticker, option_ticker, start_time, end_time])
                    rows = cur.fetchall()

            if rows:
                df = pd.DataFrame(rows, columns=['timestamp', 'option_ticker'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
                ticker_gaps = self._find_gaps_for_ticker(df, option_ticker)

                # Convert time gaps to same format
                all_gaps = time_gaps + ticker_gaps
            else:
                all_gaps = time_gaps
        else:
            all_gaps = time_gaps

        # Convert to DataFrame
        gaps_df = pd.DataFrame(all_gaps, columns=['start_time', 'end_time', 'duration_minutes', 'option_ticker'])

        return gaps_df

    def _find_time_gaps(self, timestamps: List[datetime]) -> List[Tuple]:
        """
        Find gaps in the overall time series (across all tickers).

        Args:
            timestamps: List of unique timestamps from database (UTC)

        Returns:
            List of tuples (start_time, end_time, duration_minutes, 'ALL_TICKERS')
        """
        gaps = []

        for i in range(len(timestamps) - 1):
            current = timestamps[i]
            next_ts = timestamps[i + 1]

            # Ensure timestamps are timezone-aware (UTC)
            if current.tzinfo is None:
                current = pytz.utc.localize(current)
            if next_ts.tzinfo is None:
                next_ts = pytz.utc.localize(next_ts)

            # Expected next timestamp (1 minute later)
            expected_next = current + timedelta(minutes=1)

            # Check if there's a gap (allowing 5 seconds tolerance for rounding)
            gap_seconds = (next_ts - expected_next).total_seconds()
            if gap_seconds > 5:
                # Only consider gaps during market hours
                if self._is_market_hours_gap(current, next_ts):
                    gap_duration = (next_ts - current).total_seconds() / 60 - 1
                    gaps.append((
                        current + timedelta(minutes=1),
                        next_ts,
                        gap_duration,
                        'ALL_TICKERS'  # Indicates this is a time gap, not ticker-specific
                    ))

        return gaps

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
            start_time: Gap start time (UTC)
            end_time: Gap end time (UTC)

        Returns:
            True if gap is during market hours
        """
        # Ensure times are UTC before converting to ET
        if start_time.tzinfo is None:
            start_time = pytz.utc.localize(start_time)
        elif start_time.tzinfo != pytz.utc:
            start_time = start_time.astimezone(pytz.utc)

        if end_time.tzinfo is None:
            end_time = pytz.utc.localize(end_time)
        elif end_time.tzinfo != pytz.utc:
            end_time = end_time.astimezone(pytz.utc)

        # Convert to ET timezone for market hours check
        start_time_et = start_time.astimezone(self.et_tz)
        end_time_et = end_time.astimezone(self.et_tz)

        # Check if weekday (0=Monday, 4=Friday, 5=Saturday, 6=Sunday)
        if start_time_et.weekday() >= 5:  # Saturday or Sunday
            return False

        # Parse market hours in ET
        market_open_hour = int(self.MARKET_OPEN.split(':')[0])
        market_open_minute = int(self.MARKET_OPEN.split(':')[1])
        market_close_hour = int(self.MARKET_CLOSE.split(':')[0])
        market_close_minute = int(self.MARKET_CLOSE.split(':')[1])

        # Create market open/close times for the same day
        market_open = start_time_et.replace(
            hour=market_open_hour,
            minute=market_open_minute,
            second=0,
            microsecond=0
        )
        market_close = start_time_et.replace(
            hour=market_close_hour,
            minute=market_close_minute,
            second=0,
            microsecond=0
        )

        # Check if gap overlaps with market hours
        # Gap is during market hours if:
        # - Start is before market close AND
        # - End is after market open
        return start_time_et < market_close and end_time_et > market_open

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
            start_time: Start of time range (UTC)
            end_time: End of time range (UTC)
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

        earliest_bar = result[2]
        latest_bar = result[3]

        # Convert to ET for display
        earliest_et = earliest_bar.astimezone(self.et_tz)
        latest_et = latest_bar.astimezone(self.et_tz)

        print(f"\n📈 Data Summary for {underlying_ticker}:")
        print(f"   Time range: {start_time.astimezone(self.et_tz)} to {end_time.astimezone(self.et_tz)} ET")
        print(f"   Total bars: {result[0]:,}")
        print(f"   Unique option tickers: {result[1]:,}")
        print(f"   Earliest bar: {earliest_et} ET")
        print(f"   Latest bar: {latest_et} ET")
        print(f"   Trading days: {result[4]}")

        # Check market hours coverage
        market_open_hour = int(self.MARKET_OPEN.split(':')[0])
        market_open_minute = int(self.MARKET_OPEN.split(':')[1])
        market_close_hour = int(self.MARKET_CLOSE.split(':')[0])
        market_close_minute = int(self.MARKET_CLOSE.split(':')[1])

        # Check if data covers market hours
        market_open_time = earliest_et.replace(hour=market_open_hour, minute=market_open_minute, second=0, microsecond=0)
        market_close_time = earliest_et.replace(hour=market_close_hour, minute=market_close_minute, second=0, microsecond=0)

        if earliest_et.hour > market_open_hour or (earliest_et.hour == market_open_hour and earliest_et.minute > market_open_minute):
            print(f"\n   ⚠️  WARNING: Data starts AFTER market open (9:30 AM ET)")
            print(f"      Missing pre-market and early trading data")

        if latest_et.hour < market_close_hour or (latest_et.hour == market_close_hour and latest_et.minute < market_close_minute):
            print(f"\n   ⚠️  WARNING: Data ends BEFORE market close (4:00 PM ET)")
            print(f"      Missing late trading data")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='1-Minute Bar Sanity Check - Detect gaps in options data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check specific date
  python data/utils/1-minute-sanity.py --date 2025-12-16

  # Check date range
  python data/utils/1-minute-sanity.py --start 2025-12-15 --end 2025-12-16

  # Check last 24 hours
  python data/utils/1-minute-sanity.py --last-24h

  # Check specific option ticker
  python data/utils/1-minute-sanity.py --date 2025-12-16 --ticker SPXW251216C06050000
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
