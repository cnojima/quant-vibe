"""Test the updated polling script that only uses Schwab API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from poll_spxw_quotes import OptionsQuotePoller
from datetime import datetime


def test_contract_discovery():
    """Test contract discovery using only Schwab API."""
    print("="*70)
    print("TEST: Contract Discovery (Schwab API Only)")
    print("="*70)

    try:
        poller = OptionsQuotePoller(
            poll_interval=60,
            max_dte=5,  # Only 0-5 DTE for faster testing
            min_dte=0,
            strike_range_pct=0.05,  # ±5% for fewer contracts
        )

        print("\nGetting active contracts...")
        contracts = poller.get_active_contracts()

        if not contracts:
            print("\n❌ No contracts found")
            return False

        print(f"\n✅ Found {len(contracts)} contracts")
        print(f"\nFirst 5 contracts:")
        for i, contract in enumerate(contracts[:5]):
            print(f"  {i+1}. {contract['ticker']}")
            print(f"     Strike: ${contract['strike_price']:.2f}")
            print(f"     Type: {contract['contract_type']}")
            print(f"     Expiration: {contract['expiration_date']}")

        # Test quote fetching for one contract
        print(f"\n📊 Testing quote fetch for first contract...")
        test_ticker = contracts[0]['ticker']
        quote = poller.schwab.get_quote(test_ticker)

        if test_ticker in quote:
            quote_data = quote[test_ticker].get('quote', {})
            print(f"  Ticker: {test_ticker}")
            print(f"  Bid: ${quote_data.get('bidPrice', 0):.2f}")
            print(f"  Ask: ${quote_data.get('askPrice', 0):.2f}")
            print(f"  Last: ${quote_data.get('lastPrice', 0):.2f}")
            print(f"  Delta: {quote_data.get('delta')}")
            print("  ✅ Quote fetch works!")
        else:
            print(f"  ⚠️  No quote data for {test_ticker}")

        # Test batch quote fetching
        print(f"\n📊 Testing batch quote fetch (first 10 contracts)...")
        batch_tickers = [c['ticker'] for c in contracts[:10]]
        batch_quotes = poller.schwab.get_quotes(batch_tickers)

        valid_quotes = sum(1 for t in batch_tickers if t in batch_quotes)
        print(f"  ✅ Got {valid_quotes}/{len(batch_tickers)} valid quotes")

        poller.cleanup()
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run the test."""
    result = test_contract_discovery()

    print("\n" + "="*70)
    if result:
        print("✅ POLLING SCRIPT READY!")
        print("\nYou can now run the full polling script:")
        print("  python scripts/poll_spxw_quotes.py")
        print("\nThe script will:")
        print("  1. Discover SPXW contracts using Schwab API")
        print("  2. Poll quotes every 60 seconds")
        print("  3. Aggregate into 1-minute bars")
        print("  4. Store in TimescaleDB")
    else:
        print("❌ POLLING SCRIPT HAS ISSUES - Fix before running")
    print("="*70)


if __name__ == "__main__":
    main()
