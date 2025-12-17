"""Test if Massive API has 0 DTE options data available."""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.massive_client import MassiveClient


def test_0dte_availability():
    """Test if we can fetch 0 DTE options data from Massive API."""

    print("="*70)
    print("TESTING 0 DTE DATA AVAILABILITY FROM MASSIVE API")
    print("="*70)
    print()

    # Initialize Massive client
    try:
        client = MassiveClient()
        print("✅ Connected to Massive API\n")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return

    # Test for a past expiration date
    # SPX has Mon/Wed/Fri expirations (SPXW)
    # Let's test for a Friday in early July 2025 (we have data from July 1)
    test_date = datetime(2025, 7, 18)  # Friday, July 18, 2025
    test_date_str = test_date.strftime("%Y-%m-%d")

    print(f"Test Expiration Date: {test_date_str} (Friday)")
    print(f"This should have SPXW contracts expiring on this date")
    print()

    # Step 1: Check if contracts exist for this expiration
    print("Step 1: Checking for contracts expiring on this date...")
    try:
        contracts = client.list_options_contracts(
            underlying_ticker="SPX",
            expiration_date=test_date_str,
            contract_type="call",
            expired=True,  # Need to include expired contracts for historical data
            limit=10,
        )

        if contracts.empty:
            print(f"❌ No contracts found for expiration {test_date_str}")
            print("   This might mean:")
            print("   1. No SPX options expired on this date")
            print("   2. The date is too far in the future")
            print("   3. Your Massive API subscription doesn't include this data")
            return

        print(f"✅ Found {len(contracts)} call contracts")
        print(f"\nSample contracts:")
        print(contracts[['ticker', 'strike_price', 'expiration_date']].head())
        print()

        # Pick a contract to test
        test_ticker = contracts.iloc[0]['ticker']
        test_strike = contracts.iloc[0]['strike_price']
        print(f"Selected test contract: {test_ticker} (Strike: ${test_strike})")
        print()

    except Exception as e:
        print(f"❌ Error fetching contracts: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 2: Try to fetch 0 DTE data (same day as expiration)
    print(f"\nStep 2: Testing 0 DTE data (expiration day: {test_date_str})...")
    try:
        # Fetch 1-minute bars for the expiration day only
        bars_0dte = client.get_option_bars(
            option_ticker=test_ticker,
            multiplier=1,
            timespan="minute",
            from_date=test_date_str,
            to_date=test_date_str,
            limit=500,
        )

        if bars_0dte.empty:
            print(f"❌ No 0 DTE data available for {test_date_str}")
            print("   Reasons:")
            print("   - SPX AM-settled options expire at market open")
            print("   - Data may not be available until after expiration")
            print("   - Historical 0 DTE data might be limited")
        else:
            print(f"✅ Found {len(bars_0dte)} minute bars on expiration day!")
            print(f"\n0 DTE Data Sample:")
            print(bars_0dte.head(10))
            print(f"\nTime range: {bars_0dte.index[0]} to {bars_0dte.index[-1]}")

    except Exception as e:
        print(f"❌ Error fetching 0 DTE bars: {e}")
        import traceback
        traceback.print_exc()

    # Step 3: Try to fetch 1 DTE data (day before expiration)
    day_before = test_date - timedelta(days=1)
    day_before_str = day_before.strftime("%Y-%m-%d")

    print(f"\n\nStep 3: Testing 1 DTE data (day before: {day_before_str})...")
    try:
        bars_1dte = client.get_option_bars(
            option_ticker=test_ticker,
            multiplier=1,
            timespan="minute",
            from_date=day_before_str,
            to_date=day_before_str,
            limit=500,
        )

        if bars_1dte.empty:
            print(f"❌ No 1 DTE data available for {day_before_str}")
        else:
            print(f"✅ Found {len(bars_1dte)} minute bars one day before expiration!")
            print(f"\n1 DTE Data Sample:")
            print(bars_1dte.head(10))
            print(f"\nTime range: {bars_1dte.index[0]} to {bars_1dte.index[-1]}")

    except Exception as e:
        print(f"❌ Error fetching 1 DTE bars: {e}")
        import traceback
        traceback.print_exc()

    # Step 4: Try a wider date range including expiration
    print(f"\n\nStep 4: Testing wider date range (3 days before to expiration)...")
    try:
        three_days_before = test_date - timedelta(days=3)
        three_days_before_str = three_days_before.strftime("%Y-%m-%d")

        bars_range = client.get_option_bars(
            option_ticker=test_ticker,
            multiplier=1,
            timespan="minute",
            from_date=three_days_before_str,
            to_date=test_date_str,
            limit=5000,
        )

        if bars_range.empty:
            print(f"❌ No data available for range {three_days_before_str} to {test_date_str}")
        else:
            print(f"✅ Found {len(bars_range)} minute bars across the range!")

            # Check which dates have data
            if hasattr(bars_range.index, 'date'):
                unique_dates = bars_range.index.date
            else:
                unique_dates = [d.date() for d in bars_range.index]

            unique_dates = sorted(set(unique_dates))
            print(f"\nDates with data: {unique_dates}")

            # Check if expiration day has data
            if test_date.date() in unique_dates:
                expiry_bars = bars_range[bars_range.index.date == test_date.date()]
                print(f"\n✅ EXPIRATION DAY HAS DATA!")
                print(f"   Bars on {test_date_str}: {len(expiry_bars)}")
                print(f"   Time range: {expiry_bars.index[0]} to {expiry_bars.index[-1]}")
            else:
                print(f"\n❌ No data on expiration day {test_date_str}")
                print(f"   Last date with data: {unique_dates[-1]}")

    except Exception as e:
        print(f"❌ Error fetching range: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    test_0dte_availability()
