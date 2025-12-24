#!/usr/bin/env python3
"""Backfill historical $SPX 1-minute bars from Schwab API to underlying_bars table.

This script fetches 1-minute bars for $SPX from June 1, 2025 to today
and stores them in the TimescaleDB underlying_bars table.

Usage:
    python scripts/backfill_spx_underlying_1min.py

    # Dry run (show what would be fetched without inserting)
    python scripts/backfill_spx_underlying_1min.py --dry-run

    # Custom date range
    python scripts/backfill_spx_underlying_1min.py --start-date 2025-06-01 --end-date 2025-12-24

Notes:
    - Schwab API limits: 1-minute data can only go back ~30 days per request
    - Script automatically chunks requests to handle this limitation
    - Market hours only: 9:30 AM - 4:00 PM ET
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.data.timescale_store import TimescaleStore


def backfill_spx_1min(
    start_date: datetime,
    end_date: datetime,
    dry_run: bool = False,
    chunk_days: int = 30
):
    """
    Backfill $SPX 1-minute bars from Schwab API.

    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        dry_run: If True, fetch data but don't insert into database
        chunk_days: Number of days to fetch per API request (max 30 for 1-min data)
    """
    print("=" * 80)
    print("BACKFILL $SPX 1-MINUTE UNDERLYING BARS")
    print("=" * 80)
    print(f"\nStart date: {start_date.date()}")
    print(f"End date:   {end_date.date()}")
    print(f"Dry run:    {dry_run}")
    print(f"Chunk size: {chunk_days} days per request")
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

    # Calculate total duration
    total_days = (end_date - start_date).days
    total_chunks = (total_days // chunk_days) + 1

    print(f"Total duration: {total_days} days")
    print(f"Estimated requests: {total_chunks}")
    print()

    # Track statistics
    total_bars = 0
    total_inserted = 0
    errors = []

    # Process in chunks (Schwab API limits 1-min data to ~30 days per request)
    current_start = start_date

    chunk_num = 0
    while current_start < end_date:
        chunk_num += 1
        current_end = min(current_start + timedelta(days=chunk_days), end_date)

        print("-" * 80)
        print(f"Chunk {chunk_num}/{total_chunks}: {current_start.date()} to {current_end.date()}")
        print("-" * 80)

        try:
            # Fetch data from Schwab
            print(f"Fetching 1-minute bars from Schwab API...")
            print(f"  Start: {current_start} (type: {type(current_start)})")
            print(f"  End: {current_end} (type: {type(current_end)})")

            data = schwab.get_index_price_history(
                index_symbol="$SPX", # index symbol is $SPX
                start_datetime=current_start,
                end_datetime=current_end,
                frequency_minutes=1
            )

            if data.empty:
                print(f"⚠️  No data returned for this period")
                errors.append(f"No data: {current_start.date()} to {current_end.date()}")
                current_start = current_end
                continue

            print(f"✅ Fetched {len(data):,} bars")
            total_bars += len(data)

            # Convert DataFrame to list of dicts for bulk insert
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
                # Insert into database
                print(f"Inserting {len(bars):,} bars into underlying_bars table...")
                inserted = ts_store.bulk_insert_underlying_bars(bars)
                print(f"✅ Inserted {inserted:,} bars")
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
            error_msg = f"Error processing {current_start.date()} to {current_end.date()}: {e}"
            print(f"❌ {error_msg}")
            print(f"\nFull traceback:")
            traceback.print_exc()
            errors.append(error_msg)

        # Move to next chunk
        current_start = current_end

        # Rate limiting: wait 1 second between requests to be nice to Schwab API
        if current_start < end_date:
            print("Waiting 1 second before next request...")
            time.sleep(1)
            print()

    # Final summary
    print("=" * 80)
    print("BACKFILL SUMMARY")
    print("=" * 80)
    print(f"Total bars fetched: {total_bars:,}")
    if not dry_run:
        print(f"Total bars inserted: {total_inserted:,}")
    print(f"Chunks processed: {chunk_num}/{total_chunks}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\nErrors encountered:")
        for error in errors:
            print(f"  - {error}")

    if not dry_run and total_inserted > 0:
        # Verify data in database
        print("\nVerifying data in database...")
        verify_data = ts_store.get_underlying_bars(
            ticker='SPX',
            start_time=start_date,
            end_time=end_date
        )
        print(f"✅ Found {len(verify_data):,} bars in database")
        if not verify_data.empty:
            print(f"   Date range: {verify_data.index[0]} to {verify_data.index[-1]}")
            print(f"   Price range: ${verify_data['Low'].min():.2f} - ${verify_data['High'].max():.2f}")
            print(f"   Latest close: ${verify_data['Close'].iloc[-1]:.2f}")

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
        description="Backfill historical $SPX 1-minute bars to underlying_bars table"
    )

    parser.add_argument(
        '--start-date',
        type=str,
        default='2025-06-01',
        help='Start date (YYYY-MM-DD) - default: 2025-06-01'
    )

    parser.add_argument(
        '--end-date',
        type=str,
        default=None,
        help='End date (YYYY-MM-DD) - default: today'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Fetch data but do not insert into database'
    )

    parser.add_argument(
        '--chunk-days',
        type=int,
        default=30,
        help='Number of days per API request (default: 30, max for 1-min data)'
    )

    args = parser.parse_args()

    # Parse dates
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    else:
        end_date = datetime.now()

    # Ensure timezone aware (UTC)
    start_date = start_date.replace(tzinfo=timezone.utc)
    end_date = end_date.replace(tzinfo=timezone.utc)

    # Run backfill
    backfill_spx_1min(
        start_date=start_date,
        end_date=end_date,
        dry_run=args.dry_run,
        chunk_days=args.chunk_days
    )


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
