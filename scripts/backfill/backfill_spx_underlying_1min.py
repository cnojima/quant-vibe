#!/usr/bin/env python3
"""Backfill historical $SPX bars from Schwab API to underlying_bars table.

This script detects gaps in the underlying_bars table and backfills them from Schwab API.
Supports both 1-minute and 5-minute bar frequencies.

Schema Compliance (Updated 2026-01):
- Uses UnderlyingBar Pydantic model from quant_vibe.models.market_data
- All data validated by Pydantic before database insertion
- Timestamps: Always UTC-aware (validated by Pydantic)
- Decimal types for prices (validated by Pydantic)
- OHLC relationships validated (high >= low, open, close)
- Market holiday calendar (2025-2026) to avoid API errors

Usage:
    # Detect and backfill gaps with 1-minute bars (default: scan last 7 days)
    python scripts/backfill/backfill_spx_underlying_1min.py

    # Backfill with 5-minute bars
    python scripts/backfill/backfill_spx_underlying_1min.py --frequency 5

    # Scan specific date range for gaps
    python scripts/backfill/backfill_spx_underlying_1min.py --start-date 2025-12-01 --end-date 2025-12-30

    # Backfill today only with 5-minute bars
    python scripts/backfill/backfill_spx_underlying_1min.py --today --frequency 5

    # Dry run (show gaps without fetching/inserting)
    python scripts/backfill/backfill_spx_underlying_1min.py --dry-run

    # Show stats only (no backfill)
    python scripts/backfill/backfill_spx_underlying_1min.py --stats-only

Features:
    - Automatically detects gaps in existing data (missing days or incomplete days)
    - Supports 1-minute and 5-minute bar frequencies
    - Respects market hours (9:30 AM - 4:00 PM EST)
    - Handles timezone conversions (EST <-> UTC)
    - Filters market holidays (2025-2026 NYSE calendar)
    - Idempotent: uses ON CONFLICT to safely update existing bars

Notes:
    - Schwab API limits: 1-minute data can only go back ~30 days per request
    - Expected bars per trading day: 390 (1-min) or 78 (5-min)
    - Partial day threshold: 80% of expected bars
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import time
import pytz
from typing import List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.models import UnderlyingBar
from quant_vibe.utils.timestamp_utils import to_utc

# Market hours (EST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# Expected bars per trading day
# 1-minute: 9:30 AM - 4:00 PM EST = 6.5 hours = 390 bars
# 5-minute: 390 / 5 = 78 bars
EXPECTED_BARS_PER_DAY_1MIN = 390
EXPECTED_BARS_PER_DAY_5MIN = 78

# Threshold for considering a day "incomplete" (80% of expected bars)
INCOMPLETE_DAY_THRESHOLD = 0.8


def get_market_holidays_2025() -> set:
    """
    Get US market holidays for 2025.

    Based on NYSE calendar: https://www.nyse.com/markets/hours-calendars
    """
    return {
        datetime(2025, 1, 1).date(),   # New Year's Day (Wednesday)
        datetime(2025, 1, 20).date(),  # Martin Luther King Jr. Day
        datetime(2025, 2, 17).date(),  # Presidents' Day
        datetime(2025, 4, 18).date(),  # Good Friday
        datetime(2025, 5, 26).date(),  # Memorial Day
        datetime(2025, 6, 19).date(),  # Juneteenth
        datetime(2025, 7, 4).date(),   # Independence Day
        datetime(2025, 9, 1).date(),   # Labor Day
        datetime(2025, 11, 27).date(), # Thanksgiving
        datetime(2025, 12, 25).date(), # Christmas
    }


def get_market_holidays_2026() -> set:
    """
    Get US market holidays for 2026.

    Based on NYSE calendar (projected).
    """
    return {
        datetime(2026, 1, 1).date(),   # New Year's Day
        datetime(2026, 1, 19).date(),  # Martin Luther King Jr. Day
        datetime(2026, 2, 16).date(),  # Presidents' Day
        datetime(2026, 4, 3).date(),   # Good Friday
        datetime(2026, 5, 25).date(),  # Memorial Day
        datetime(2026, 6, 19).date(),  # Juneteenth
        datetime(2026, 7, 3).date(),   # Independence Day (observed Friday)
        datetime(2026, 9, 7).date(),   # Labor Day
        datetime(2026, 11, 26).date(), # Thanksgiving
        datetime(2026, 12, 25).date(), # Christmas
    }


def get_all_market_holidays() -> set:
    """Get all market holidays (2025-2026)."""
    return get_market_holidays_2025() | get_market_holidays_2026()


def is_trading_day(date: datetime) -> bool:
    """
    Check if a date is a trading day (Mon-Fri, excluding market holidays).

    Args:
        date: Date to check

    Returns:
        True if it's a trading day, False otherwise
    """
    # Check weekends
    if date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Check market holidays
    holidays = get_all_market_holidays()
    return date.date() not in holidays


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
    end_date: datetime,
    frequency_minutes: int = 1
) -> List[Tuple[datetime, datetime, str]]:
    """
    Detect gaps in underlying_bars data.

    Args:
        ts_store: TimescaleDB store instance
        start_date: Start date for gap detection
        end_date: End date for gap detection
        frequency_minutes: Bar frequency (1 or 5 minutes)

    Returns:
        List of (start_utc, end_utc, reason) tuples for gaps found.
        Reasons: 'missing_day', 'incomplete_day'
    """
    expected_bars = EXPECTED_BARS_PER_DAY_1MIN if frequency_minutes == 1 else EXPECTED_BARS_PER_DAY_5MIN

    print("=" * 80)
    print("DETECTING GAPS IN UNDERLYING_BARS")
    print("=" * 80)
    print(f"Scan range: {start_date.date()} to {end_date.date()}")
    print(f"Frequency: {frequency_minutes}-minute bars")
    print(f"Expected bars per day: {expected_bars}")
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
            start_date=market_open,
            end_date=market_close
        )

        bar_count = len(day_bars)

        if bar_count == 0:
            missing_days.append(trade_date)
            gaps.append((market_open, market_close, 'missing_day'))
        elif bar_count < expected_bars * INCOMPLETE_DAY_THRESHOLD:
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
            pct = (count / expected_bars) * 100
            print(f"   {date.date()}: {count}/{expected_bars} bars ({pct:.1f}%)")
        if len(incomplete_days) > 10:
            print(f"   ... and {len(incomplete_days) - 10} more")

    print(f"\nTotal gaps to backfill: {len(gaps)}")
    print()

    return gaps


def backfill_gaps(
    gaps: List[Tuple[datetime, datetime, str]],
    dry_run: bool = False,
    frequency_minutes: int = 1
):
    """
    Backfill detected gaps with data from Schwab API.

    Args:
        gaps: List of (start_utc, end_utc, reason) tuples
        dry_run: If True, fetch data but don't insert into database
        frequency_minutes: Bar frequency (1 or 5 minutes)
    """
    if not gaps:
        print("✅ No gaps to backfill!")
        return

    print("=" * 80)
    print("BACKFILLING GAPS")
    print("=" * 80)
    print(f"Total gaps: {len(gaps)}")
    print(f"Frequency: {frequency_minutes}-minute bars")
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
            print(f"Fetching {frequency_minutes}-minute bars from Schwab API...")
            print(f"  Start: {gap_start}")
            print(f"  End: {gap_end}")

            data = schwab.get_index_price_history(
                index_symbol="$SPX",
                start_datetime=gap_start,
                end_datetime=gap_end,
                frequency_minutes=frequency_minutes
            )

            if data.empty:
                print(f"⚠️  No data returned for this period")
                errors.append(f"No data: {gap_start.date()} ({reason})")
                continue

            print(f"✅ Fetched {len(data):,} bars")
            total_bars += len(data)

            # Convert DataFrame to Pydantic UnderlyingBar models
            # NOTE: Schwab API returns columns as: Open, High, Low, Close, Volume (capitalized)
            # Pydantic model will validate OHLC relationships, timestamps, and types
            bars = []
            for timestamp, row in data.iterrows():
                try:
                    # Create validated UnderlyingBar model
                    # Pydantic will validate OHLC relationships and convert to Decimal
                    bar = UnderlyingBar(
                        timestamp=to_utc(timestamp.to_pydatetime()),  # Ensure UTC-aware
                        ticker='SPX',
                        open=Decimal(str(row['Open'])),
                        high=Decimal(str(row['High'])),
                        low=Decimal(str(row['Low'])),
                        close=Decimal(str(row['Close'])),
                        volume=int(row['Volume']) if row['Volume'] > 0 else 0,
                        vwap=None,  # Not available from Schwab API
                        transactions=None,  # Not available from Schwab API
                        data_source='schwab'
                    )
                    bars.append(bar)
                except Exception as e:
                    print(f"    ⚠️  Error creating UnderlyingBar for {timestamp}: {e}")
                    # Skip invalid bars
                    continue

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
  # Scan last 7 days and backfill gaps with 1-minute bars (default)
  python scripts/backfill/backfill_spx_underlying_1min.py

  # Backfill with 5-minute bars
  python scripts/backfill/backfill_spx_underlying_1min.py --frequency 5

  # Scan specific date range with 5-minute bars
  python scripts/backfill/backfill_spx_underlying_1min.py --start-date 2025-12-01 --end-date 2025-12-30 --frequency 5

  # Backfill today only with 5-minute bars
  python scripts/backfill/backfill_spx_underlying_1min.py --today --frequency 5

  # Show stats only (no backfill)
  python scripts/backfill/backfill_spx_underlying_1min.py --stats-only

  # Dry run (show gaps without fetching/inserting)
  python scripts/backfill/backfill_spx_underlying_1min.py --dry-run --frequency 5
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
        '--frequency',
        type=int,
        choices=[1, 5],
        default=1,
        help='Bar frequency in minutes (default: 1, options: 1 or 5)'
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
    gaps = detect_gaps(ts_store, start_date, end_date, frequency_minutes=args.frequency)

    # Close connection (will reconnect in backfill if needed)
    ts_store.close()

    # Backfill gaps unless stats-only
    if not args.stats_only:
        backfill_gaps(gaps, dry_run=args.dry_run, frequency_minutes=args.frequency)
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
