"""
Test script for MassiveClient integration.

This script tests the MassiveClient functionality including:
- Listing options contracts
- Getting options chain data
- Fetching historical options data
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data import MassiveClient


def test_massive_client():
    """Test MassiveClient functionality."""
    print("=" * 80)
    print("Testing Massive Client Integration")
    print("=" * 80)
    print()

    # Initialize client
    print("1. Initializing MassiveClient...")
    try:
        client = MassiveClient()
        print("   ✓ Client initialized successfully")
    except Exception as e:
        print(f"   ✗ Failed to initialize client: {e}")
        return
    print()

    # Test 1: List options contracts for SPX expiring in the next 30 days
    print("2. Testing list_options_contracts() for SPX...")
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

        contracts = client.list_options_contracts(
            underlying_ticker="SPX",
            expiration_date_gte=today,
            expiration_date_lte=future,
            limit=10
        )

        print(f"   ✓ Found {len(contracts)} contracts")
        if not contracts.empty:
            print(f"   First contract:")
            print(f"     Ticker: {contracts.iloc[0]['ticker']}")
            print(f"     Strike: {contracts.iloc[0]['strike_price']}")
            print(f"     Type: {contracts.iloc[0]['contract_type']}")
            print(f"     Expiration: {contracts.iloc[0]['expiration_date']}")
        else:
            print("   ⚠ No contracts found")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    print()

    # Test 2: Get options chain for a specific expiration date
    print("3. Testing get_option_chain()...")
    try:
        # Use a date 2 weeks out
        exp_date = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

        chain = client.get_option_chain(
            underlying_ticker="SPX",
            expiration_date=exp_date
        )

        print(f"   ✓ Found {len(chain)} contracts in chain")
        if not chain.empty:
            print(f"   Strike range: {chain['strike_price'].min()} - {chain['strike_price'].max()}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    print()

    # Test 3: Get historical bars for an option contract
    print("4. Testing get_option_bars()...")
    try:
        # First get a contract ticker
        if not contracts.empty:
            option_ticker = contracts.iloc[0]['ticker']
            print(f"   Getting bars for: {option_ticker}")

            # Get last 30 days of data
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            to_date = datetime.now().strftime("%Y-%m-%d")

            bars = client.get_option_bars(
                option_ticker=option_ticker,
                from_date=from_date,
                to_date=to_date,
                timespan="day"
            )

            print(f"   ✓ Retrieved {len(bars)} bars")
            if not bars.empty:
                print(f"   Data range: {bars.index[0]} to {bars.index[-1]}")
                print(f"   Sample data:")
                print(bars.head())
        else:
            print("   ⚠ Skipping - no contracts available")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    print()

    # Test 4: Search options by date range
    print("5. Testing search_options_by_date_range()...")
    try:
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

        results = client.search_options_by_date_range(
            underlying_ticker="SPX",
            start_date=start_date,
            end_date=end_date,
            contract_type="call",
            limit=5
        )

        print(f"   ✓ Found {len(results)} call contracts")
        if not results.empty:
            print(f"   Sample contracts:")
            print(results[['ticker', 'strike_price', 'expiration_date']].head())
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    print()

    print("=" * 80)
    print("Testing Complete")
    print("=" * 80)


if __name__ == "__main__":
    test_massive_client()
