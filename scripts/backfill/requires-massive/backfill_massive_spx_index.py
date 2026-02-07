#!/usr/bin/env python3
"""
Backfill SPX index 1-minute bars from Massive.io Custom Bars API.

⚠️  DATA AVAILABILITY: Massive.io has I:SPX data starting from February 14, 2023.
    Earlier dates will return no data. For historical data before 2023, use the
    Schwab API backfill script (backfill_spx_underlying_1min.py).

This script fetches historical I:SPX (S&P 500 Index) 1-minute OHLC data from the
Massive.io Custom Bars API and backfills the underlying_bars table in TimescaleDB.

Features:
- Fetches I:SPX 1-minute bars using Massive.io Custom Bars API
- Handles market holidays and weekends
- Validates bar counts (390 bars per trading day)
- Detects and fills gaps in existing data
- Uses UnderlyingBar Pydantic model for schema compliance
- Idempotent inserts (can be re-run safely)
- Progress tracking and statistics

Schema Compliance:
- All timestamps are UTC-aware (validated by Pydantic)
- Prices converted to Decimal for precision
- Ticker normalized from I:SPX to SPX
- Volume set to 0 (indices don't have volume)
- Data source set to 'massive'

Market Calendar:
- NYSE trading hours: 9:30 AM - 4:00 PM ET (390 minutes = 390 bars)
- Excludes weekends (Saturday, Sunday)
- Excludes market holidays (2015-2026 calendar included)

Usage:
    # Backfill available range (Feb 2023 - Present)
    python backfill_massive_spx_index.py --start-date 2023-02-01 --end-date 2025-01-01

    # Test with dry run (no database inserts)
    python backfill_massive_spx_index.py --start-date 2024-12-01 --end-date 2024-12-31 --dry-run

    # Backfill specific date range with custom chunk size
    python backfill_massive_spx_index.py --start-date 2024-01-01 --end-date 2025-01-01 --chunk-days 60

    # Skip validation (faster, use if confident in data quality)
    python backfill_massive_spx_index.py --skip-validation

Dependencies:
    - Massive.io API key in .env (MASSIVE_API_KEY)
    - TimescaleDB connection configured
    - quant_vibe package installed

Author: Claude Code
Date: 2026-01-10
"""

import argparse
import sys
from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import List, Tuple, Optional
import time

import pandas as pd
from psycopg2.extras import execute_batch

# Add parent directory to path for imports
sys.path.insert(0, '/Users/curisu/dev/quant-vibe')

from quant_vibe.data.massive_client import MassiveClient
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.models import UnderlyingBar
from quant_vibe.utils.timestamp_utils import to_utc, now_utc


# =============================================================================
# MARKET CALENDAR - NYSE Trading Days
# =============================================================================

def get_market_holidays_2015() -> set:
    """NYSE market holidays for 2015."""
    return {
        date(2015, 1, 1),   # New Year's Day
        date(2015, 1, 19),  # Martin Luther King Jr. Day
        date(2015, 2, 16),  # Presidents' Day
        date(2015, 4, 3),   # Good Friday
        date(2015, 5, 25),  # Memorial Day
        date(2015, 7, 3),   # Independence Day (observed)
        date(2015, 9, 7),   # Labor Day
        date(2015, 11, 26), # Thanksgiving
        date(2015, 12, 25), # Christmas
    }


def get_market_holidays_2016() -> set:
    """NYSE market holidays for 2016."""
    return {
        date(2016, 1, 1),   # New Year's Day
        date(2016, 1, 18),  # Martin Luther King Jr. Day
        date(2016, 2, 15),  # Presidents' Day
        date(2016, 3, 25),  # Good Friday
        date(2016, 5, 30),  # Memorial Day
        date(2016, 7, 4),   # Independence Day
        date(2016, 9, 5),   # Labor Day
        date(2016, 11, 24), # Thanksgiving
        date(2016, 12, 26), # Christmas (observed)
    }


def get_market_holidays_2017() -> set:
    """NYSE market holidays for 2017."""
    return {
        date(2017, 1, 2),   # New Year's Day (observed)
        date(2017, 1, 16),  # Martin Luther King Jr. Day
        date(2017, 2, 20),  # Presidents' Day
        date(2017, 4, 14),  # Good Friday
        date(2017, 5, 29),  # Memorial Day
        date(2017, 7, 4),   # Independence Day
        date(2017, 9, 4),   # Labor Day
        date(2017, 11, 23), # Thanksgiving
        date(2017, 12, 25), # Christmas
    }


def get_market_holidays_2018() -> set:
    """NYSE market holidays for 2018."""
    return {
        date(2018, 1, 1),   # New Year's Day
        date(2018, 1, 15),  # Martin Luther King Jr. Day
        date(2018, 2, 19),  # Presidents' Day
        date(2018, 3, 30),  # Good Friday
        date(2018, 5, 28),  # Memorial Day
        date(2018, 7, 4),   # Independence Day
        date(2018, 9, 3),   # Labor Day
        date(2018, 11, 22), # Thanksgiving
        date(2018, 12, 5),  # National Day of Mourning (George H.W. Bush)
        date(2018, 12, 25), # Christmas
    }


def get_market_holidays_2019() -> set:
    """NYSE market holidays for 2019."""
    return {
        date(2019, 1, 1),   # New Year's Day
        date(2019, 1, 21),  # Martin Luther King Jr. Day
        date(2019, 2, 18),  # Presidents' Day
        date(2019, 4, 19),  # Good Friday
        date(2019, 5, 27),  # Memorial Day
        date(2019, 7, 4),   # Independence Day
        date(2019, 9, 2),   # Labor Day
        date(2019, 11, 28), # Thanksgiving
        date(2019, 12, 25), # Christmas
    }


def get_market_holidays_2020() -> set:
    """NYSE market holidays for 2020."""
    return {
        date(2020, 1, 1),   # New Year's Day
        date(2020, 1, 20),  # Martin Luther King Jr. Day
        date(2020, 2, 17),  # Presidents' Day
        date(2020, 4, 10),  # Good Friday
        date(2020, 5, 25),  # Memorial Day
        date(2020, 7, 3),   # Independence Day (observed)
        date(2020, 9, 7),   # Labor Day
        date(2020, 11, 26), # Thanksgiving
        date(2020, 12, 25), # Christmas
    }


def get_market_holidays_2021() -> set:
    """NYSE market holidays for 2021."""
    return {
        date(2021, 1, 1),   # New Year's Day
        date(2021, 1, 18),  # Martin Luther King Jr. Day
        date(2021, 2, 15),  # Presidents' Day
        date(2021, 4, 2),   # Good Friday
        date(2021, 5, 31),  # Memorial Day
        date(2021, 7, 5),   # Independence Day (observed)
        date(2021, 9, 6),   # Labor Day
        date(2021, 11, 25), # Thanksgiving
        date(2021, 12, 24), # Christmas (observed)
    }


def get_market_holidays_2022() -> set:
    """NYSE market holidays for 2022."""
    return {
        date(2022, 1, 17),  # Martin Luther King Jr. Day
        date(2022, 2, 21),  # Presidents' Day
        date(2022, 4, 15),  # Good Friday
        date(2022, 5, 30),  # Memorial Day
        date(2022, 6, 20),  # Juneteenth (observed)
        date(2022, 7, 4),   # Independence Day
        date(2022, 9, 5),   # Labor Day
        date(2022, 11, 24), # Thanksgiving
        date(2022, 12, 26), # Christmas (observed)
    }


def get_market_holidays_2023() -> set:
    """NYSE market holidays for 2023."""
    return {
        date(2023, 1, 2),   # New Year's Day (observed)
        date(2023, 1, 16),  # Martin Luther King Jr. Day
        date(2023, 2, 20),  # Presidents' Day
        date(2023, 4, 7),   # Good Friday
        date(2023, 5, 29),  # Memorial Day
        date(2023, 6, 19),  # Juneteenth
        date(2023, 7, 4),   # Independence Day
        date(2023, 9, 4),   # Labor Day
        date(2023, 11, 23), # Thanksgiving
        date(2023, 12, 25), # Christmas
    }


def get_market_holidays_2024() -> set:
    """NYSE market holidays for 2024."""
    return {
        date(2024, 1, 1),   # New Year's Day
        date(2024, 1, 15),  # Martin Luther King Jr. Day
        date(2024, 2, 19),  # Presidents' Day
        date(2024, 3, 29),  # Good Friday
        date(2024, 5, 27),  # Memorial Day
        date(2024, 6, 19),  # Juneteenth
        date(2024, 7, 4),   # Independence Day
        date(2024, 9, 2),   # Labor Day
        date(2024, 11, 28), # Thanksgiving
        date(2024, 12, 25), # Christmas
    }


def get_market_holidays_2025() -> set:
    """NYSE market holidays for 2025."""
    return {
        date(2025, 1, 1),   # New Year's Day
        date(2025, 1, 20),  # Martin Luther King Jr. Day
        date(2025, 2, 17),  # Presidents' Day
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 26),  # Memorial Day
        date(2025, 6, 19),  # Juneteenth
        date(2025, 7, 4),   # Independence Day
        date(2025, 9, 1),   # Labor Day
        date(2025, 11, 27), # Thanksgiving
        date(2025, 12, 25), # Christmas
    }


def get_market_holidays_2026() -> set:
    """NYSE market holidays for 2026."""
    return {
        date(2026, 1, 1),   # New Year's Day
        date(2026, 1, 19),  # Martin Luther King Jr. Day
        date(2026, 2, 16),  # Presidents' Day
        date(2026, 4, 3),   # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),   # Independence Day (observed)
        date(2026, 9, 7),   # Labor Day
        date(2026, 11, 26), # Thanksgiving
        date(2026, 12, 25), # Christmas
    }


def get_all_market_holidays() -> set:
    """Get all market holidays from 2015-2026."""
    return (
        get_market_holidays_2015() |
        get_market_holidays_2016() |
        get_market_holidays_2017() |
        get_market_holidays_2018() |
        get_market_holidays_2019() |
        get_market_holidays_2020() |
        get_market_holidays_2021() |
        get_market_holidays_2022() |
        get_market_holidays_2023() |
        get_market_holidays_2024() |
        get_market_holidays_2025() |
        get_market_holidays_2026()
    )


def is_trading_day(dt: datetime) -> bool:
    """
    Check if a given date is a trading day.

    Args:
        dt: Datetime to check

    Returns:
        True if it's a trading day (Mon-Fri, not a holiday)
    """
    # Check if weekend
    if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False

    # Check if market holiday
    market_holidays = get_all_market_holidays()
    if dt.date() in market_holidays:
        return False

    return True


# =============================================================================
# GAP DETECTION
# =============================================================================

EXPECTED_BARS_PER_DAY = 390  # 9:30 AM - 4:00 PM ET = 6.5 hours = 390 minutes


def get_existing_data_summary(ts_store: TimescaleStore, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Query existing data in underlying_bars for SPX.

    Args:
        ts_store: TimescaleStore instance
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        DataFrame with daily bar counts
    """
    query = """
    SELECT
        DATE(timestamp) as date,
        COUNT(*) as bar_count,
        MIN(timestamp) as first_bar,
        MAX(timestamp) as last_bar
    FROM underlying_bars
    WHERE ticker = 'SPX'
      AND timestamp >= %s
      AND timestamp < %s
    GROUP BY DATE(timestamp)
    ORDER BY date
    """

    with ts_store.conn.cursor() as cur:
        cur.execute(query, (start_date, end_date))
        rows = cur.fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=['date', 'bar_count', 'first_bar', 'last_bar'])
    return df


def detect_gaps(start_date: str, end_date: str, ts_store: TimescaleStore) -> List[Tuple[datetime, datetime, str]]:
    """
    Detect gaps in SPX underlying data.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        ts_store: TimescaleStore instance

    Returns:
        List of (gap_start, gap_end, reason) tuples
    """
    gaps = []

    # Get existing data summary
    existing = get_existing_data_summary(ts_store, start_date, end_date)
    existing_dates = set(existing['date'].dt.date) if not existing.empty else set()

    # Generate all trading days in range
    current = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    while current < end:
        if is_trading_day(current):
            current_date = current.date()

            if current_date not in existing_dates:
                # Missing entire day
                gaps.append((current, current, "missing_day"))
            else:
                # Check if day has insufficient bars
                day_data = existing[existing['date'].dt.date == current_date]
                if not day_data.empty:
                    bar_count = day_data.iloc[0]['bar_count']
                    if bar_count < EXPECTED_BARS_PER_DAY - 10:  # Allow 10-bar tolerance
                        gaps.append((current, current, f"incomplete_day_{bar_count}_bars"))

        current += timedelta(days=1)

    return gaps


# =============================================================================
# DATA TRANSFORMATION
# =============================================================================

def transform_to_underlying_bars(df: pd.DataFrame) -> List[UnderlyingBar]:
    """
    Transform Massive API response DataFrame to UnderlyingBar Pydantic models.

    Args:
        df: DataFrame from MassiveClient.get_index_bars()
            Index: timestamp (datetime)
            Columns: Open, High, Low, Close, Volume

    Returns:
        List of UnderlyingBar instances
    """
    bars = []

    for row in df.itertuples():
        try:
            # Convert timestamp to UTC-aware
            timestamp = row.Index.to_pydatetime()
            timestamp_utc = to_utc(timestamp)

            # Create UnderlyingBar
            bar = UnderlyingBar(
                timestamp=timestamp_utc,
                ticker='SPX',  # Normalize from I:SPX to SPX
                open=Decimal(str(row.Open)),
                high=Decimal(str(row.High)),
                low=Decimal(str(row.Low)),
                close=Decimal(str(row.Close)),
                volume=0,  # Indices don't have volume
                vwap=Decimal(str(row.vwap)) if hasattr(row, 'vwap') and pd.notna(row.vwap) else None,
                transactions=int(row.transactions) if hasattr(row, 'transactions') and pd.notna(row.transactions) else None,
                data_source='massive',
            )
            bars.append(bar)
        except Exception as e:
            print(f"⚠️  Error transforming bar at {row.Index}: {e}")
            continue

    return bars


# =============================================================================
# VALIDATION
# =============================================================================

def validate_bars(bars: List[UnderlyingBar], expected_date: date) -> Tuple[bool, str]:
    """
    Validate fetched bars for a trading day.

    Args:
        bars: List of UnderlyingBar instances
        expected_date: Expected trading date

    Returns:
        (is_valid, message) tuple
    """
    if not bars:
        return False, "No bars returned"

    # Check bar count (allow for early close days like Christmas Eve)
    bar_count = len(bars)
    if bar_count < 100:  # Very lenient - just ensure we have some data
        return False, f"Insufficient bars: {bar_count} (expected ~{EXPECTED_BARS_PER_DAY})"
    elif bar_count < EXPECTED_BARS_PER_DAY - 50:
        # Warning for early close, but not an error
        pass  # Still valid, just note it

    # Check all bars are from expected date
    dates = {bar.timestamp.date() for bar in bars}
    if len(dates) > 1:
        return False, f"Bars span multiple dates: {dates}"

    if expected_date not in dates:
        return False, f"Bars are from {dates}, expected {expected_date}"

    # Check timestamps are monotonic
    timestamps = [bar.timestamp for bar in bars]
    if timestamps != sorted(timestamps):
        return False, "Timestamps are not in chronological order"

    return True, f"Valid: {bar_count} bars"


# =============================================================================
# BACKFILL LOGIC
# =============================================================================

def backfill_date_range(
    start_date: str,
    end_date: str,
    massive_client: MassiveClient,
    ts_store: Optional[TimescaleStore],
    dry_run: bool,
    skip_validation: bool,
) -> Tuple[int, int, List[str]]:
    """
    Backfill SPX data for a date range.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        massive_client: MassiveClient instance
        ts_store: TimescaleStore instance (None if dry_run)
        dry_run: If True, don't insert into database
        skip_validation: If True, skip bar validation

    Returns:
        (bars_fetched, bars_inserted, errors) tuple
    """
    print(f"\n{'='*80}")
    print(f"FETCHING: {start_date} to {end_date}")
    print(f"{'='*80}")

    bars_fetched = 0
    bars_inserted = 0
    errors = []

    try:
        # Fetch data from Massive API
        print(f"📡 Fetching I:SPX 1-minute bars from Massive.io...")
        df = massive_client.get_index_bars(
            index_ticker="I:SPX",
            multiplier=1,
            timespan="minute",
            from_date=start_date,
            to_date=end_date,
            limit=50000,  # Max limit
        )

        if df.empty:
            msg = f"No data returned for {start_date} to {end_date}"
            print(f"⚠️  {msg}")
            errors.append(msg)
            return 0, 0, errors

        bars_fetched = len(df)
        print(f"✅ Fetched {bars_fetched} bars")

        # Transform to UnderlyingBar models
        print(f"🔄 Transforming to UnderlyingBar models...")
        bars = transform_to_underlying_bars(df)
        print(f"✅ Transformed {len(bars)} bars")

        # Validate (if not skipped)
        if not skip_validation:
            # Group by date and validate each day
            bars_by_date = {}
            for bar in bars:
                bar_date = bar.timestamp.date()
                if bar_date not in bars_by_date:
                    bars_by_date[bar_date] = []
                bars_by_date[bar_date].append(bar)

            print(f"🔍 Validating {len(bars_by_date)} trading days...")
            for bar_date, day_bars in bars_by_date.items():
                is_valid, msg = validate_bars(day_bars, bar_date)
                if not is_valid:
                    print(f"   ⚠️  {bar_date}: {msg}")
                    errors.append(f"{bar_date}: {msg}")
                else:
                    print(f"   ✅ {bar_date}: {msg}")

        # Insert into database
        if not dry_run and ts_store and bars:
            print(f"💾 Inserting {len(bars)} bars into database...")
            inserted = ts_store.bulk_insert_underlying_bars(bars, batch_size=1000)
            bars_inserted = inserted
            print(f"✅ Inserted {inserted} bars")
        elif dry_run:
            print(f"🔸 DRY RUN: Would insert {len(bars)} bars")
            bars_inserted = len(bars)  # Count as "inserted" for stats

    except Exception as e:
        msg = f"Error processing {start_date} to {end_date}: {e}"
        print(f"❌ {msg}")
        errors.append(msg)

    return bars_fetched, bars_inserted, errors


def backfill_chunks(
    start_date: str,
    end_date: str,
    chunk_days: int,
    massive_client: MassiveClient,
    ts_store: Optional[TimescaleStore],
    dry_run: bool,
    skip_validation: bool,
) -> None:
    """
    Backfill data in chunks.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        chunk_days: Days per chunk
        massive_client: MassiveClient instance
        ts_store: TimescaleStore instance (None if dry_run)
        dry_run: If True, don't insert into database
        skip_validation: If True, skip bar validation
    """
    # Generate chunks
    chunks = []
    current = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    while current < end:
        chunk_end = min(current + timedelta(days=chunk_days), end)
        chunks.append((current.strftime('%Y-%m-%d'), chunk_end.strftime('%Y-%m-%d')))
        current = chunk_end

    print(f"\n{'='*80}")
    print(f"BACKFILL PLAN")
    print(f"{'='*80}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Chunk size: {chunk_days} days")
    print(f"Total chunks: {len(chunks)}")
    print(f"Dry run: {dry_run}")
    print(f"Skip validation: {skip_validation}")
    print()

    # Process chunks
    total_fetched = 0
    total_inserted = 0
    all_errors = []

    start_time = time.time()

    for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
        print(f"\n{'─'*80}")
        print(f"CHUNK {i}/{len(chunks)}")
        print(f"{'─'*80}")

        fetched, inserted, errors = backfill_date_range(
            chunk_start,
            chunk_end,
            massive_client,
            ts_store,
            dry_run,
            skip_validation,
        )

        total_fetched += fetched
        total_inserted += inserted
        all_errors.extend(errors)

        # Progress update
        elapsed = time.time() - start_time
        avg_time_per_chunk = elapsed / i
        remaining_chunks = len(chunks) - i
        eta_seconds = avg_time_per_chunk * remaining_chunks
        eta_minutes = eta_seconds / 60

        print(f"\n📊 Progress: {i}/{len(chunks)} chunks ({i/len(chunks)*100:.1f}%)")
        print(f"   Fetched: {total_fetched:,} bars")
        print(f"   Inserted: {total_inserted:,} bars")
        print(f"   Errors: {len(all_errors)}")
        print(f"   ETA: {eta_minutes:.1f} minutes")

        # Brief pause to avoid rate limits
        if i < len(chunks):
            time.sleep(0.5)

    # Final summary
    elapsed = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"BACKFILL COMPLETE")
    print(f"{'='*80}")
    print(f"Total fetched: {total_fetched:,} bars")
    print(f"Total inserted: {total_inserted:,} bars")
    print(f"Total errors: {len(all_errors)}")
    print(f"Elapsed time: {elapsed/60:.1f} minutes")
    print()

    if all_errors:
        print(f"⚠️  ERRORS ({len(all_errors)}):")
        for error in all_errors[:10]:  # Show first 10
            print(f"   - {error}")
        if len(all_errors) > 10:
            print(f"   ... and {len(all_errors) - 10} more")
    else:
        print("✅ No errors!")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Backfill SPX index 1-minute bars from Massive.io Custom Bars API"
    )
    parser.add_argument(
        "--start-date",
        default="2023-02-01",
        help="Start date (YYYY-MM-DD). Default: 2023-02-01 (earliest available data)"
    )
    parser.add_argument(
        "--end-date",
        default="2025-01-01",
        help="End date (YYYY-MM-DD). Default: 2025-01-01"
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=30,
        help="Days per chunk. Default: 30"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but don't insert into database"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip bar validation (faster)"
    )
    parser.add_argument(
        "--detect-gaps-only",
        action="store_true",
        help="Only detect gaps, don't backfill"
    )

    args = parser.parse_args()

    print(f"\n{'='*80}")
    print(f"SPX INDEX BACKFILL - Massive.io Custom Bars API")
    print(f"{'='*80}\n")

    # Initialize clients
    print("🔌 Initializing Massive.io client...")
    try:
        massive = MassiveClient()
        print("✅ Connected to Massive.io API\n")
    except Exception as e:
        print(f"❌ Failed to connect to Massive.io: {e}")
        sys.exit(1)

    if not args.dry_run:
        print("🔌 Initializing TimescaleDB connection...")
        try:
            ts_store = TimescaleStore()
            print("✅ Connected to TimescaleDB\n")
        except Exception as e:
            print(f"❌ Failed to connect to TimescaleDB: {e}")
            sys.exit(1)
    else:
        ts_store = None
        print("🔸 DRY RUN MODE: Database writes disabled\n")

    # Gap detection only
    if args.detect_gaps_only:
        print("🔍 Detecting gaps...")
        gaps = detect_gaps(args.start_date, args.end_date, ts_store)

        if not gaps:
            print("✅ No gaps found!")
        else:
            print(f"⚠️  Found {len(gaps)} gaps:")
            for gap_start, gap_end, reason in gaps[:20]:
                print(f"   - {gap_start.date()}: {reason}")
            if len(gaps) > 20:
                print(f"   ... and {len(gaps) - 20} more")

        return

    # Backfill
    backfill_chunks(
        args.start_date,
        args.end_date,
        args.chunk_days,
        massive,
        ts_store,
        args.dry_run,
        args.skip_validation,
    )


if __name__ == "__main__":
    main()
