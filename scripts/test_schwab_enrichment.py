"""
Test script for Schwab quote enrichment.

This script demonstrates how to:
1. Parse Massive option ticker format
2. Convert to Schwab ticker format
3. Fetch quotes from Schwab API
4. Enrich data with bid/ask/Greeks

Usage:
    python scripts/test_schwab_enrichment.py

Prerequisites:
    - Install Schwab dependencies: pip install -e ".[schwab]"
    - Configure Schwab API credentials in .env
    - Complete OAuth authentication
"""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.schwab_py_client import SchwabPyClient


def test_ticker_conversion():
    """Test Massive to Schwab ticker conversion."""
    # Import conversion functions from collect script
    spec = __import__('importlib.util').util.spec_from_file_location(
        'collect',
        Path(__file__).parent / 'collect_options_1min_data.py'
    )
    module = __import__('importlib.util').util.module_from_spec(spec)
    spec.loader.exec_module(module)

    print("=" * 80)
    print("Testing Ticker Conversion")
    print("=" * 80)
    print()

    test_tickers = [
        'O:SPXW251226P02000000',  # SPX weekly put
        'O:SPX250117C04500000',   # SPX monthly call
        'O:AAPL260117C00150000',  # AAPL call
    ]

    for massive_ticker in test_tickers:
        parsed = module.parse_massive_option_ticker(massive_ticker)
        schwab_ticker = module.convert_to_schwab_ticker(massive_ticker)

        print(f"Massive: {massive_ticker}")
        print(f"Schwab:  {schwab_ticker}")
        print(f"  Underlying: {parsed['underlying']}")
        print(f"  Expiration: {parsed['expiration_date']}")
        print(f"  Type:       {parsed['option_type']}")
        print(f"  Strike:     ${parsed['strike_price']:.2f}")
        print()


def test_schwab_quote():
    """Test fetching quote from Schwab API."""
    print("=" * 80)
    print("Testing Schwab Quote Fetching")
    print("=" * 80)
    print()

    try:
        # Initialize Schwab client
        print("Initializing Schwab client...")
        client = SchwabPyClient()
        print("✓ Client initialized")
        print()

        # Test with a recent SPX option
        # Note: Adjust this to an actual current contract
        test_ticker = "SPXW  251226C04500000"

        print(f"Fetching quote for: {test_ticker}")
        quote_response = client.get_quote(test_ticker)

        if test_ticker in quote_response:
            quote = quote_response[test_ticker].get('quote', {})

            print("✓ Quote received:")
            print(f"  Bid:           ${quote.get('bidPrice', 'N/A')}")
            print(f"  Ask:           ${quote.get('askPrice', 'N/A')}")
            print(f"  Last:          ${quote.get('lastPrice', 'N/A')}")
            print(f"  Bid Size:      {quote.get('bidSize', 'N/A')}")
            print(f"  Ask Size:      {quote.get('askSize', 'N/A')}")
            print(f"  Volume:        {quote.get('totalVolume', 'N/A')}")
            print()

            print("Greeks:")
            print(f"  Delta:         {quote.get('delta', 'N/A')}")
            print(f"  Gamma:         {quote.get('gamma', 'N/A')}")
            print(f"  Theta:         {quote.get('theta', 'N/A')}")
            print(f"  Vega:          {quote.get('vega', 'N/A')}")
            print(f"  Rho:           {quote.get('rho', 'N/A')}")
            print(f"  Implied Vol:   {quote.get('volatility', 'N/A')}")
            print()

            # Show full response structure
            print("Available fields:")
            for key in sorted(quote.keys()):
                print(f"  - {key}")
        else:
            print(f"✗ No quote data found for {test_ticker}")
            print("Available tickers in response:")
            for ticker in quote_response.keys():
                print(f"  - {ticker}")

    except ImportError:
        print("✗ Schwab client not available")
        print("  Install with: pip install -e '.[schwab]'")
    except Exception as e:
        print(f"✗ Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Ensure SCHWAB_API_KEY and SCHWAB_API_SECRET are set in .env")
        print("2. Complete OAuth authentication if this is your first time")
        print("3. Check that the option ticker is valid and currently trading")


def test_enrichment_flow():
    """Test the full enrichment flow."""
    print("=" * 80)
    print("Testing Full Enrichment Flow")
    print("=" * 80)
    print()

    # Import enrichment function
    spec = __import__('importlib.util').util.spec_from_file_location(
        'collect',
        Path(__file__).parent / 'collect_options_1min_data.py'
    )
    module = __import__('importlib.util').util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Create sample bars (as if from Massive)
    sample_bars = [
        {
            'timestamp': datetime(2025, 12, 14, 9, 30),
            'open': 100.5,
            'high': 101.0,
            'low': 100.0,
            'close': 100.75,
            'volume': 1000,
        },
        {
            'timestamp': datetime(2025, 12, 14, 9, 31),
            'open': 100.75,
            'high': 101.5,
            'low': 100.5,
            'close': 101.25,
            'volume': 1500,
        },
    ]

    print("Sample bars (before enrichment):")
    for bar in sample_bars:
        print(f"  {bar['timestamp']}: O={bar['open']}, H={bar['high']}, L={bar['low']}, C={bar['close']}")
    print()

    try:
        # Initialize client
        client = SchwabPyClient()

        # Enrich bars
        massive_ticker = "O:SPXW251226C04500000"
        enriched_bars = module.enrich_with_schwab(client, massive_ticker, sample_bars)

        print("Enriched bars:")
        for bar in enriched_bars:
            print(f"  {bar['timestamp']}:")
            print(f"    OHLCV: O={bar['open']}, H={bar['high']}, L={bar['low']}, C={bar['close']}, V={bar['volume']}")
            if 'bid' in bar and bar['bid'] is not None:
                print(f"    Quote: Bid={bar['bid']}, Ask={bar['ask']}")
            if 'delta' in bar and bar['delta'] is not None:
                print(f"    Greeks: δ={bar['delta']}, γ={bar['gamma']}, θ={bar['theta']}, ν={bar['vega']}")
            print()

    except ImportError:
        print("✗ Schwab client not available")
        print("  Install with: pip install -e '.[schwab]'")
    except Exception as e:
        print(f"✗ Error: {e}")


def main():
    """Run all tests."""
    test_ticker_conversion()
    print()

    test_schwab_quote()
    print()

    test_enrichment_flow()
    print()

    print("=" * 80)
    print("Testing Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()
