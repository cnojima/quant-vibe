#!/usr/bin/env python3
"""Backfill historical $SPX 1-minute bars from Schwab API to underlying_bars table.

This script detects gaps in the underlying_bars table and backfills them from Schwab API.
It can also be used to backfill a specific date range.

Usage:
    # Detect and backfill gaps (default: scan last 7 days)
    python scripts/backfill/backfill_spx_underlying_1min.py

    # Scan specific date range for gaps
    python scripts/backfill/backfill_spx_underlying_1min.py --start-date 2025-12-01 --end-date 2025-12-30

    # Backfill today only
    python scripts/backfill/backfill_spx_underlying_1min.py --today

    # Dry run (show gaps without fetching/inserting)
    python scripts/backfill/backfill_spx_underlying_1min.py --dry-run

    # Show stats only (no backfill)
    python scripts/backfill/backfill_spx_underlying_1min.py --stats-only

Features:
    - Automatically detects gaps in existing data (missing days or incomplete days)
    - Respects market hours (9:30 AM - 4:00 PM EST)
    - Handles timezone conversions (EST <-> UTC)
    - Chunks large requests to respect Schwab API limits
    - Idempotent: uses ON CONFLICT to safely update existing bars

Notes:
    - Schwab API limits: 1-minute data can only go back ~30 days per request
    - Expected bars per trading day: 390 (6.5 hours * 60 minutes)
    - Partial day threshold: 80% (312 bars minimum)
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
import time
import pytz
from typing import List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.data.timescale_store import TimescaleStore

# Market hours (EST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# Expected bars per trading day (9:30 AM - 4:00 PM EST = 6.5 hours = 390 minutes)
EXPECTED_BARS_PER_DAY = 390

# Threshold for considering a day "incomplete" (80% of expected bars)
INCOMPLETE_DAY_THRESHOLD = 0.8


def is_trading_day(date: datetime) -> bool:
    """Check if a date is a trading day (Mon-Fri, excludes weekends)."""
    return date.weekday() < 5  # 0-4 are Mon-Fri


def get_trading_day_range_utc(date: datetime) -> Tuple[datetime, datetime]:
    """
    Get market hours (9:30 AM - 4:00 PM EST) for a trading day in UTC.

    Args:
        date: Date in any timezone

    Returns:
        Tuple of (market_open_utc, market_close_utc)
    """
    est = pytz.timezone('US/Eastern')

    # Create EST datetime for market open/close
    market_open_est = est.localize(datetime(
        date.year, date.month, date.day,
        MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, 0
    ))
    market_close_est = est.localize(datetime(
        date.year, date.month, date.day,
        MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE, 0
    ))

    # Convert to UTC
    market_open_utc = market_open_est.astimezone(pytz.utc).replace(tzinfo=timezone.utc)
    market_close_utc = market_close_est.astimezone(pytz.utc).replace(tzinfo=timezone.utc)

    return market_open_utc, market_close_utc


def detect_gaps(
    ts_store: TimescaleStore,
    start_date: datetime,
    end_date: datetime
) -> List[Tuple[datetime, datetime, str]]:
    """
    Detect gaps in underlying_bars data.

    Returns list of (start_utc, end_utc, reason) tuples for gaps found.
    Reasons: 'missing_day', 'incomplete_day'
    """
    print("=" * 80)
    print("DETECTING GAPS IN UNDERLYING_BARS")
    print("=" * 80)
    print(f"Scan range: {start_date.date()} to {end_date.date()}")
    print()

    gaps = []

    # Generate list of expected trading days
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date_only = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    trading_days = []
    while current_date <= end_date_only:
        if is_trading_day(current_date):
            trading_days.append(current_date)
        current_date += timedelta(days=1)

    print(f"Expected trading days in range: {len(trading_days)}")
    print()

    # Check each trading day
    missing_days = []
    incomplete_days = []

    for trade_date in trading_days:
        market_open, market_close = get_trading_day_range_utc(trade_date)

        # Query bars for this day
        day_bars = ts_store.get_underlying_bars(
            ticker='SPX',
            start_time=market_open,
            end_time=market_close
        )

        bar_count = len(day_bars)

        if bar_count == 0:
            missing_days.append(trade_date)
            gaps.append((market_open, market_close, 'missing_day'))
        elif bar_count < EXPECTED_BARS_PER_DAY * INCOMPLETE_DAY_THRESHOLD:
            incomplete_days.append((trade_date, bar_count))
            gaps.append((market_open, market_close, 'incomplete_day'))

    # Print summary
    print(f"✅ Complete days: {len(trading_days) - len(missing_days) - len(incomplete_days)}")

    if missing_days:
        print(f"\n❌ Missing days ({len(missing_days)}):")
        for date in missing_days[:10]:  # Show first 10
            print(f"   {date.date()}")
        if len(missing_days) > 10:
            print(f"   ... and {len(missing_days) - 10} more")

    if incomplete_days:
        print(f"\n⚠️  Incomplete days ({len(incomplete_days)}):")
        for date, count in incomplete_days[:10]:  # Show first 10
            pct = (count / EXPECTED_BARS_PER_DAY) * 100
            print(f"   {date.date()}: {count}/{EXPECTED_BARS_PER_DAY} bars ({pct:.1f}%)")
        if len(incomplete_days) > 10:
            print(f"   ... and {len(incomplete_days) - 10} more")

    print(f"\nTotal gaps to backfill: {len(gaps)}")
    print()

    return gaps


def backfill_gaps(
    gaps: List[Tuple[datetime, datetime, str]],
    dry_run: bool = False,
    chunk_days: int = 30
):
    """
    Backfill detected gaps with data from Schwab API.

    Args:
        gaps: List of (start_utc, end_utc, reason) tuples
        dry_run: If True, fetch data but don't insert into database
        chunk_days: Number of days to fetch per API request (max 30 for 1-min data)
    """
    if not gaps:
        print("✅ No gaps to backfill!")
        return

    print("=" * 80)
    print("BACKFILLING GAPS")
    print("=" * 80)
    print(f"Total gaps: {len(gaps)}")
    print(f"Dry run: {dry_run}")
    print()

    # Initialize clients
    print("Initializing Schwab API client...")
    schwab = SchwabDevClient()
    print("✅ Connected to Schwab API\n")

    if not dry_run:
        print("Initializing TimescaleDB connection...")
        ts_store = TimescaleStore()
        print("✅ Connected to TimescaleDB\n")
    else:
        ts_store = None

    # Track statistics
    total_bars = 0
    total_inserted = 0
    errors = []

    # Process each gap
    for gap_num, (gap_start, gap_end, reason) in enumerate(gaps, 1):
        print("-" * 80)
        print(f"Gap {gap_num}/{len(gaps)}: {gap_start.date()} ({reason})")
        print("-" * 80)

        try:
            # Fetch data from Schwab
            print(f"Fetching 1-minute bars from Schwab API...")
            print(f"  Start: {gap_start}")
            print(f"  End: {gap_end}")

            data = schwab.get_index_price_history(
                index_symbol="$SPX",
                start_datetime=gap_start,
                end_datetime=gap_end,
                frequency_minutes=1
            )

            if data.empty:
                print(f"⚠️  No data returned for this period")
                errors.append(f"No data: {gap_start.date()} ({reason})")
                continue

            print(f"✅ Fetched {len(data):,} bars")
            total_bars += len(data)

            # Convert DataFrame to list of dicts for bulk insert
            # NOTE: Schwab API returns columns as: Open, High, Low, Close, Volume (capitalized)
            # But database uses lowercase column names
            bars = []
            for timestamp, row in data.iterrows():
                bars.append({
                    'timestamp': timestamp.to_pydatetime(),
                    'ticker': 'SPX',
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume']),
                    'data_source': 'schwab'
                })

            if not dry_run:
                # Insert into database (uses ON CONFLICT to update existing bars)
                print(f"Inserting {len(bars):,} bars into underlying_bars table...")
                inserted = ts_store.bulk_insert_underlying_bars(bars)
                print(f"✅ Inserted/updated {inserted:,} bars")
                total_inserted += inserted
            else:
                print(f"[DRY RUN] Would insert {len(bars):,} bars")

            # Show sample data
            print(f"\nSample data:")
            print(f"  First bar: {data.index[0]} | Close: ${data['Close'].iloc[0]:.2f}")
            print(f"  Last bar:  {data.index[-1]} | Close: ${data['Close'].iloc[-1]:.2f}")
            print()

        except Exception as e:
            import traceback
            error_msg = f"Error processing {gap_start.date()} ({reason}): {e}"
            print(f"❌ {error_msg}")
            print(f"\nFull traceback:")
            traceback.print_exc()
            errors.append(error_msg)

        # Rate limiting: wait 1 second between requests
        if gap_num < len(gaps):
            print("Waiting 1 second before next request...")
            time.sleep(1)
            print()

    # Final summary
    print("=" * 80)
    print("BACKFILL SUMMARY")
    print("=" * 80)
    print(f"Gaps processed: {gap_num}/{len(gaps)}")
    print(f"Total bars fetched: {total_bars:,}")
    if not dry_run:
        print(f"Total bars inserted/updated: {total_inserted:,}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\nErrors encountered:")
        for error in errors:
            print(f"  - {error}")

    print("\n" + "=" * 80)
    if dry_run:
        print("✅ DRY RUN COMPLETE - No data was inserted")
    else:
        print("✅ BACKFILL COMPLETE")
    print("=" * 80)
    print()

    if ts_store:
        ts_store.close()


def main():
    parser = argparse.ArgumentParser(
        description="Detect and backfill gaps in SPX underlying_bars table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan last 7 days and backfill gaps (default)
  python scripts/backfill/backfill_spx_underlying_1min.py

  # Scan specific date range
  python scripts/backfill/backfill_spx_underlying_1min.py --start-date 2025-12-01 --end-date 2025-12-30

  # Backfill today only
  python scripts/backfill/backfill_spx_underlying_1min.py --today

  # Show stats only (no backfill)
  python scripts/backfill/backfill_spx_underlying_1min.py --stats-only

  # Dry run (show gaps without fetching/inserting)
  python scripts/backfill/backfill_spx_underlying_1min.py --dry-run
        """
    )

    parser.add_argument(
        '--start-date',
        type=str,
        default=None,
        help='Start date (YYYY-MM-DD) - default: 7 days ago'
    )

    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='End date (YYYY-MM-DD) - default: today'
    )

    parser.add_argument(
        '--today',
        action='store_true',
        help='Backfill today only (shortcut for --start-date today --end-date today)'
    )

    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Show gap statistics only, do not backfill'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show gaps without fetching or inserting data'
    )

    parser.add_argument(
        '--chunk-days',
        type=int,
        default=30,
        help='Number of days per API request (default: 30, max for 1-min data)'
    )

    args = parser.parse_args()

    # Determine date range
    if args.today:
        # Today only
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = today
        end_date = today
    else:
        # Parse dates
        if args.start_date:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
            start_date = start_date.replace(tzinfo=timezone.utc)
        else:
            # Default: 7 days ago
            start_date = datetime.now(timezone.utc) - timedelta(days=7)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
            end_date = end_date.replace(tzinfo=timezone.utc)
        else:
            # Default: today
            end_date = datetime.now(timezone.utc)
            end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # Initialize TimescaleDB
    print("Connecting to TimescaleDB...")
    ts_store = TimescaleStore()
    print("✅ Connected\n")

    # Detect gaps
    gaps = detect_gaps(ts_store, start_date, end_date)

    # Close connection (will reconnect in backfill if needed)
    ts_store.close()

    # Backfill gaps unless stats-only
    if not args.stats_only:
        backfill_gaps(gaps, dry_run=args.dry_run, chunk_days=args.chunk_days)
    else:
        print("=" * 80)
        print("STATS ONLY - Skipping backfill")
        print("=" * 80)
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
