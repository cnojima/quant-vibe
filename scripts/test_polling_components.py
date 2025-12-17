"""Test all components needed for polling script."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime, timedelta


def test_schwab_client():
    """Test SchwabPyClient."""
    print("\n" + "="*70)
    print("TEST 1: SchwabPyClient")
    print("="*70)

    try:
        from quant_vibe.data.schwab_py_client import SchwabPyClient

        client = SchwabPyClient()
        print("✅ SchwabPyClient initialized")

        # Test single quote
        print("\n  Testing get_quote()...")
        quote = client.get_quote("$SPX")
        spx_price = quote.get("$SPX", {}).get("quote", {}).get("lastPrice")
        print(f"  SPX Price: ${spx_price:.2f}")
        print("  ✅ get_quote() works")

        # Test multiple quotes
        print("\n  Testing get_quotes()...")
        quotes = client.get_quotes(["$SPX", "AAPL"])
        print(f"  Got quotes for {len(quotes)} symbols")
        print("  ✅ get_quotes() works")

        return True

    except Exception as e:
        print(f"  ❌ SchwabPyClient failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_massive_client():
    """Test MassiveClient."""
    print("\n" + "="*70)
    print("TEST 2: MassiveClient")
    print("="*70)

    try:
        from quant_vibe.data.massive_client import MassiveClient

        client = MassiveClient()
        print("✅ MassiveClient initialized")

        # Test listing contracts
        print("\n  Testing list_options_contracts()...")
        today = datetime.now()
        tomorrow = today + timedelta(days=1)

        contracts = client.list_options_contracts(
            underlying_ticker="SPX",
            expiration_date_gte=today.strftime("%Y-%m-%d"),
            expiration_date_lte=tomorrow.strftime("%Y-%m-%d"),
            strike_price_gte=6800,
            strike_price_lte=6900,
            limit=10,
        )

        print(f"  Found {len(contracts)} contracts")
        if not contracts.empty:
            print(f"  Sample contract: {contracts.iloc[0]['ticker']}")
            print("  ✅ list_options_contracts() works")
        else:
            print("  ⚠️  No contracts found (might be valid if no contracts in range)")
            print("  ✅ list_options_contracts() works (no errors)")

        return True

    except Exception as e:
        print(f"  ❌ MassiveClient failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_timescale_store():
    """Test TimescaleStore."""
    print("\n" + "="*70)
    print("TEST 3: TimescaleStore")
    print("="*70)

    try:
        from quant_vibe.data.timescale_store import TimescaleStore

        store = TimescaleStore()
        print("✅ TimescaleStore initialized")

        # Test connection
        print("\n  Testing database connection...")
        with store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                if result[0] == 1:
                    print("  ✅ Database connection works")

        # Check if bulk_insert_option_bars exists
        print("\n  Checking bulk_insert_option_bars method...")
        if hasattr(store, 'bulk_insert_option_bars'):
            print("  ✅ bulk_insert_option_bars() method exists")
        else:
            print("  ❌ bulk_insert_option_bars() method NOT found")
            return False

        store.close()
        return True

    except Exception as e:
        print(f"  ❌ TimescaleStore failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_polling_script_imports():
    """Test that polling script can be imported."""
    print("\n" + "="*70)
    print("TEST 4: Polling Script Imports")
    print("="*70)

    try:
        # Import the script
        sys.path.insert(0, str(Path(__file__).parent))
        from poll_spxw_quotes import OptionsQuotePoller

        print("✅ OptionsQuotePoller imported successfully")

        # Try to instantiate
        print("\n  Testing instantiation...")
        poller = OptionsQuotePoller(
            poll_interval=60,
            max_dte=5,
            min_dte=0,
            strike_range_pct=0.10,
        )
        print("  ✅ OptionsQuotePoller instantiated")

        return True

    except Exception as e:
        print(f"  ❌ Polling script import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("POLLING SCRIPT COMPONENT TESTS")
    print("="*70)

    results = {
        "SchwabPyClient": test_schwab_client(),
        "MassiveClient": test_massive_client(),
        "TimescaleStore": test_timescale_store(),
        "Polling Script": test_polling_script_imports(),
    }

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    all_passed = True
    for component, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {component}")
        if not passed:
            all_passed = False

    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL TESTS PASSED - Polling script should work!")
        print("\nYou can now run:")
        print("  python scripts/poll_spxw_quotes.py")
    else:
        print("❌ SOME TESTS FAILED - Fix issues before running polling script")
    print("="*70)


if __name__ == "__main__":
    main()
