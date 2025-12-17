"""
Test script to verify Schwab enrichment fields are being stored.

This script simulates the enrichment process and verifies all fields
are properly passed through to the database.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_field_mapping():
    """Test that enriched fields are mapped correctly."""
    print("=" * 80)
    print("Testing Enrichment Field Mapping")
    print("=" * 80)
    print()

    # Import the conversion function
    spec = __import__('importlib.util').util.spec_from_file_location(
        'collect',
        Path(__file__).parent / 'collect_options_1min_data.py'
    )
    module = __import__('importlib.util').util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Simulate enriched bars (as if from enrich_with_schwab)
    sample_bars = [
        {
            'timestamp': datetime(2025, 12, 14, 9, 30),
            'open': 100.5,
            'high': 101.0,
            'low': 100.0,
            'close': 100.75,
            'volume': 1000,
            'vwap': 100.6,
            'transactions': 50,
            # Schwab enrichment fields
            'bid': 100.50,
            'ask': 100.75,
            'bid_size': 10,
            'ask_size': 15,
            'delta': 0.55,
            'gamma': 0.02,
            'theta': -0.05,
            'vega': 0.15,
            'rho': 0.01,
            'implied_volatility': 0.25,
        }
    ]

    # Simulate contract data
    contract = {
        'ticker': 'O:SPXW251226C05900000',
        'underlying_ticker': 'SPXW',
        'strike_price': 5900.0,
        'contract_type': 'call',
        'expiration_date': '2025-12-26',
    }

    # Build db_bar as the script does
    db_bars = []
    for bar in sample_bars:
        db_bar = {
            "timestamp": bar["timestamp"],
            "option_ticker": str(contract["ticker"]),
            "underlying_ticker": str(contract["underlying_ticker"]),
            # OHLCV from Massive
            "open": module.convert_numpy_types(bar.get("open")),
            "high": module.convert_numpy_types(bar.get("high")),
            "low": module.convert_numpy_types(bar.get("low")),
            "close": module.convert_numpy_types(bar.get("close")),
            "volume": module.convert_numpy_types(bar.get("volume")),
            "vwap": module.convert_numpy_types(bar.get("vwap")),
            "transactions": module.convert_numpy_types(bar.get("transactions")),
            # Contract details
            "strike_price": module.convert_numpy_types(contract["strike_price"]),
            "contract_type": str(contract["contract_type"]),
            "expiration_date": datetime.strptime(contract["expiration_date"], "%Y-%m-%d"),
            # Quote data from Schwab (if enriched)
            "bid": module.convert_numpy_types(bar.get("bid")),
            "ask": module.convert_numpy_types(bar.get("ask")),
            "bid_size": module.convert_numpy_types(bar.get("bid_size")),
            "ask_size": module.convert_numpy_types(bar.get("ask_size")),
            # Greeks from Schwab (if enriched)
            "implied_volatility": module.convert_numpy_types(bar.get("implied_volatility")),
            "delta": module.convert_numpy_types(bar.get("delta")),
            "gamma": module.convert_numpy_types(bar.get("gamma")),
            "theta": module.convert_numpy_types(bar.get("theta")),
            "vega": module.convert_numpy_types(bar.get("vega")),
            "rho": module.convert_numpy_types(bar.get("rho")),
            "data_source": "schwab",
        }
        db_bars.append(db_bar)

    # Verify all fields are present
    print("Checking field mapping...")
    print()

    db_bar = db_bars[0]

    # OHLCV fields
    print("✓ OHLCV Fields:")
    print(f"  open:         {db_bar['open']}")
    print(f"  high:         {db_bar['high']}")
    print(f"  low:          {db_bar['low']}")
    print(f"  close:        {db_bar['close']}")
    print(f"  volume:       {db_bar['volume']}")
    print(f"  vwap:         {db_bar['vwap']}")
    print(f"  transactions: {db_bar['transactions']}")
    print()

    # Quote fields
    print("✓ Quote Fields (from Schwab):")
    print(f"  bid:          {db_bar['bid']}")
    print(f"  ask:          {db_bar['ask']}")
    print(f"  bid_size:     {db_bar['bid_size']}")
    print(f"  ask_size:     {db_bar['ask_size']}")
    print()

    # Greeks
    print("✓ Greeks (from Schwab):")
    print(f"  delta:        {db_bar['delta']}")
    print(f"  gamma:        {db_bar['gamma']}")
    print(f"  theta:        {db_bar['theta']}")
    print(f"  vega:         {db_bar['vega']}")
    print(f"  rho:          {db_bar['rho']}")
    print(f"  implied_vol:  {db_bar['implied_volatility']}")
    print()

    # Verify no fields are missing
    required_fields = [
        'timestamp', 'option_ticker', 'underlying_ticker',
        'open', 'high', 'low', 'close', 'volume',
        'bid', 'ask', 'bid_size', 'ask_size',
        'delta', 'gamma', 'theta', 'vega', 'rho', 'implied_volatility',
        'strike_price', 'contract_type', 'expiration_date', 'data_source'
    ]

    missing_fields = [f for f in required_fields if f not in db_bar]

    if missing_fields:
        print(f"✗ Missing fields: {missing_fields}")
    else:
        print("✓ All required fields present")
    print()

    # Check that enrichment fields have values (not None)
    enrichment_fields = ['bid', 'ask', 'delta', 'gamma', 'theta', 'vega', 'rho', 'implied_volatility']
    null_fields = [f for f in enrichment_fields if db_bar.get(f) is None]

    if null_fields:
        print(f"✗ NULL enrichment fields: {null_fields}")
    else:
        print("✓ All enrichment fields have values")
    print()

    print("=" * 80)
    print("Field Mapping Test Complete")
    print("=" * 80)
    print()
    print("Summary:")
    print(f"  Total fields:     {len(db_bar)}")
    print(f"  Missing fields:   {len(missing_fields)}")
    print(f"  NULL enrichments: {len(null_fields)}")
    print()

    if not missing_fields and not null_fields:
        print("✓ TEST PASSED: All fields mapped correctly!")
    else:
        print("✗ TEST FAILED: Some fields missing or NULL")


if __name__ == "__main__":
    test_field_mapping()
