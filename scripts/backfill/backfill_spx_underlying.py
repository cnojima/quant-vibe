"""Backfill SPX underlying price data from Schwab API.

This script fetches 1-minute historical bar data for the $SPX index
and stores it in the underlying_bars table for use in backtesting.

Schwab API limitations:
- Minute data: Available for limited historical range
- Daily data: Available for longer historical range
- Index symbol format: $SPX.X
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.data.timescale_store import TimescaleStore


def fetch_spx_bars(
    schwab_client: SchwabDevClient,
    start_date: datetime,
    end_date: datetime,
    frequency_minutes: int = 1
) -> pd.DataFrame:
    """
    Fetch SPX price history from Schwab API.

    Args:
        schwab_client: Authenticated Schwab client
        start_date: Start datetime (in US Eastern timezone)
        end_date: End datetime (in US Eastern timezone)
        frequency_minutes: Bar frequency (1, 5, 10, 15, 30)

    Returns:
        DataFrame with OHLCV data
    """
    print(f"\n📊 Fetching {frequency_minutes}-minute bars for $SPX...")
    print(f"   Date range: {start_date.date()} to {end_date.date()}")

    try:
        df = schwab_client.get_index_price_history(
            index_symbol="SPX",
            start_datetime=start_date,
            end_datetime=end_date,
            frequency_minutes=frequency_minutes
        )

        if df.empty:
            print("   ⚠️  No data returned")
            return pd.DataFrame()

        print(f"   ✅ Fetched {len(df)} bars")
        print(f"   First bar: {df.index[0]}")
        print(f"   Last bar:  {df.index[-1]}")

        return df

    except Exception as e:
        print(f"   ❌ Error fetching data: {e}")
        return pd.DataFrame()


def convert_to_db_format(df: pd.DataFrame, ticker: str = "SPX") -> List[Dict[str, Any]]:
    """
    Convert Schwab DataFrame to format expected by TimescaleStore.

    Args:
        df: DataFrame from schwab_client.get_index_price_history()
        ticker: Ticker symbol (default: "SPX")

    Returns:
        List of bar dictionaries
    """
    bars = []

    for timestamp, row in df.iterrows():
        bar = {
            'timestamp': timestamp,
            'ticker': ticker,
            'open': float(row['Open']),
            'high': float(row['High']),
            'low': float(row['Low']),
            'close': float(row['Close']),
            'volume': int(row.get('Volume', 0)),
            'vwap': None,  # Not available from Schwab
            'transactions': None,  # Not available from Schwab
            'data_source': 'schwab'
        }
        bars.append(bar)

    return bars


def backfill_date_range(
    schwab_client: SchwabDevClient,
    ts_store: TimescaleStore,
    start_date: datetime,
    end_date: datetime,
    frequency_minutes: int = 1,
    chunk_days: int = 1
) -> int:
    """
    Backfill SPX data for a date range, processing in chunks.

    Schwab API has limitations on the amount of data that can be
    fetched in a single request, so we process in daily chunks.

    Args:
        schwab_client: Authenticated Schwab client
        ts_store: TimescaleDB store
        start_date: Start date
        end_date: End date
        frequency_minutes: Bar frequency (1, 5, 10, 15, 30)
        chunk_days: Number of days to fetch per request

    Returns:
        Total number of bars inserted
    """
    total_inserted = 0
    current_start = start_date

    while current_start < end_date:
        # Calculate chunk end (don't exceed overall end date)
        current_end = min(current_start + timedelta(days=chunk_days), end_date)

        # Fetch data for this chunk
        df = fetch_spx_bars(schwab_client, current_start, current_end, frequency_minutes)

        if not df.empty:
            # Convert to database format
            bars = convert_to_db_format(df)

            # Insert into database
            print(f"   💾 Inserting {len(bars)} bars into database...")
            count = ts_store.bulk_insert_underlying_bars(bars)
            total_inserted += count
            print(f"   ✅ Inserted {count} bars")

        # Move to next chunk
        current_start = current_end

    return total_inserted


def main():
    """Main execution function."""

    print("=" * 70)
    print("SPX UNDERLYING PRICE BACKFILL")
    print("=" * 70)

    # Initialize clients
    print("\n🔧 Initializing clients...")

    try:
        schwab_client = SchwabDevClient()
        print("✅ Schwab client initialized")
    except Exception as e:
        print(f"❌ Failed to initialize Schwab client: {e}")
        print("\nMake sure you have configured:")
        print("  SCHWAB_API_KEY")
        print("  SCHWAB_API_SECRET")
        print("  SCHWAB_CALLBACK_URL")
        print("  SCHWAB_TOKEN_PATH")
        return

    try:
        ts_store = TimescaleStore()
        print("✅ TimescaleDB client initialized")
    except Exception as e:
        print(f"❌ Failed to initialize TimescaleDB: {e}")
        return

    # Configuration
    print("\n⚙️  Configuration:")

    # Date range selection
    print("\nSelect date range:")
    print("1. Today (market hours only)")
    print("2. Yesterday")
    print("3. Last week (5 trading days)")
    print("4. Last month")
    print("5. Custom range")

    choice = input("\nEnter choice (1-5): ").strip()

    now = datetime.now()

    if choice == "1":
        # Today - market hours (9:30 AM - 4:00 PM ET)
        start_date = now.replace(hour=9, minute=30, second=0, microsecond=0)
        end_date = now.replace(hour=16, minute=0, second=0, microsecond=0)
    elif choice == "2":
        # Yesterday
        yesterday = now - timedelta(days=1)
        start_date = yesterday.replace(hour=9, minute=30, second=0, microsecond=0)
        end_date = yesterday.replace(hour=16, minute=0, second=0, microsecond=0)
    elif choice == "3":
        # Last week (5 trading days)
        start_date = (now - timedelta(days=7)).replace(hour=9, minute=30, second=0, microsecond=0)
        end_date = now.replace(hour=16, minute=0, second=0, microsecond=0)
    elif choice == "4":
        # Last month
        start_date = (now - timedelta(days=30)).replace(hour=9, minute=30, second=0, microsecond=0)
        end_date = now.replace(hour=16, minute=0, second=0, microsecond=0)
    elif choice == "5":
        # Custom range
        start_str = input("Enter start date (YYYY-MM-DD): ").strip()
        end_str = input("Enter end date (YYYY-MM-DD): ").strip()

        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").replace(hour=9, minute=30)
            end_date = datetime.strptime(end_str, "%Y-%m-%d").replace(hour=16, minute=0)
        except ValueError:
            print("❌ Invalid date format")
            return
    else:
        print("❌ Invalid choice")
        return

    # Frequency selection
    print("\nSelect bar frequency:")
    print("1. 1 minute")
    print("2. 5 minutes")
    print("3. 15 minutes")

    freq_choice = input("\nEnter choice (1-3): ").strip()

    if freq_choice == "1":
        frequency_minutes = 1
    elif freq_choice == "2":
        frequency_minutes = 5
    elif freq_choice == "3":
        frequency_minutes = 15
    else:
        print("❌ Invalid choice")
        return

    print(f"\n   Start: {start_date}")
    print(f"   End:   {end_date}")
    print(f"   Frequency: {frequency_minutes} minute(s)")

    # Confirm
    confirm = input("\nProceed with backfill? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Cancelled")
        return

    # Execute backfill
    print("\n" + "=" * 70)
    print("STARTING BACKFILL")
    print("=" * 70)

    total_inserted = backfill_date_range(
        schwab_client=schwab_client,
        ts_store=ts_store,
        start_date=start_date,
        end_date=end_date,
        frequency_minutes=frequency_minutes,
        chunk_days=1  # Process 1 day at a time
    )

    print("\n" + "=" * 70)
    print("BACKFILL COMPLETE")
    print("=" * 70)
    print(f"\n✅ Total bars inserted: {total_inserted}")

    # Show sample of inserted data
    if total_inserted > 0:
        print("\n📊 Verifying data in database...")
        df = ts_store.get_underlying_bars("SPX", start_date, end_date)

        if not df.empty:
            print(f"\n✅ Verification successful: {len(df)} bars retrieved")
            print(f"\nFirst 5 bars:")
            print(df.head())
            print(f"\nLast 5 bars:")
            print(df.tail())
        else:
            print("\n⚠️  Could not retrieve inserted data")


if __name__ == "__main__":
    main()
