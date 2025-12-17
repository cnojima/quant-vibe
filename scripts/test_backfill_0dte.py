"""Test the 0 DTE backfill with a single expiration date."""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.massive_client import MassiveClient
from quant_vibe.data.timescale_store import TimescaleStore
from backfill_0dte_spxw import (
    get_contracts_for_expiration,
    collect_bars_for_contract,
    parse_spxw_ticker,
)


def main():
    """Test backfill for a single expiration date."""

    print("="*70)
    print("TEST 0 DTE BACKFILL - SINGLE EXPIRATION")
    print("="*70)
    print()

    # Test with July 18, 2025 (Friday)
    test_date = datetime(2025, 7, 18)
    strike_min = 5500.0
    strike_max = 5600.0  # Small range for testing

    print(f"Test Expiration: {test_date.date()} (Friday)")
    print(f"Strike Range: ${strike_min} - ${strike_max}")
    print()

    # Initialize clients
    massive_client = MassiveClient()
    ts_store = TimescaleStore()

    try:
        # Step 1: Get contracts
        print("Step 1: Fetching contracts...")
        contracts = get_contracts_for_expiration(
            massive_client,
            test_date,
            strike_min,
            strike_max,
        )

        if not contracts:
            print("❌ No contracts found")
            return

        print(f"✅ Found {len(contracts)} contracts")
        print(f"   Sample: {contracts[0]['ticker']}")
        print()

        # Step 2: Collect bars for first contract
        test_contract = contracts[0]
        ticker = test_contract['ticker']

        print(f"Step 2: Collecting bars for {ticker}...")
        bars = collect_bars_for_contract(
            massive_client,
            ticker,
            test_date,
            max_dte=2,
        )

        if not bars:
            print("❌ No bars found")
            return

        print(f"✅ Found {len(bars)} bars")

        # Show date distribution
        dates = {}
        for bar in bars:
            date = bar['timestamp'].date()
            dates[date] = dates.get(date, 0) + 1

        print(f"\nBars by date:")
        for date, count in sorted(dates.items()):
            dte = (test_date.date() - date).days
            print(f"  {date} ({dte} DTE): {count} bars")

        # Step 3: Parse ticker
        print(f"\nStep 3: Parsing ticker...")
        details = parse_spxw_ticker(ticker)
        if details:
            print(f"✅ Parsed successfully:")
            print(f"   Underlying: {details['underlying']}")
            print(f"   Expiration: {details['expiration_date']}")
            print(f"   Type: {details['contract_type']}")
            print(f"   Strike: ${details['strike_price']}")
        else:
            print("❌ Failed to parse")
            return

        # Step 4: Insert into database
        print(f"\nStep 4: Inserting {len(bars)} bars into database...")

        # Enrich bars with contract details
        for bar in bars:
            bar['underlying_ticker'] = 'SPX'
            bar['strike_price'] = details['strike_price']
            bar['contract_type'] = details['contract_type']
            bar['expiration_date'] = details['expiration_date']
            bar['data_source'] = 'massive'

        inserted = ts_store.bulk_insert_option_bars(bars)
        print(f"✅ Inserted {inserted} bars")

        # Step 5: Verify insertion
        print(f"\nStep 5: Verifying data in database...")
        from_time = datetime(2025, 7, 16)
        to_time = datetime(2025, 7, 18, 23, 59)

        verify_data = ts_store.get_option_bars(
            option_ticker=ticker,
            start_time=from_time,
            end_time=to_time,
            timeframe='1min',
        )

        if verify_data.empty:
            print("❌ No data found in database")
        else:
            print(f"✅ Found {len(verify_data)} bars in database")
            print(f"   Date range: {verify_data.index[0]} to {verify_data.index[-1]}")

            # Check for 0 DTE data
            dte_0_data = verify_data[verify_data.index.date == test_date.date()]
            if not dte_0_data.empty:
                print(f"\n🎉 SUCCESS! Found {len(dte_0_data)} bars on expiration day (0 DTE)")
                print(f"   Time range: {dte_0_data.index[0].time()} to {dte_0_data.index[-1].time()}")
            else:
                print(f"\n⚠️  No 0 DTE data on {test_date.date()}")

    finally:
        ts_store.close()

    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
