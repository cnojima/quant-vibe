"""Test script to verify SPXW contract fetching from Schwab API."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.realtime_collector import RealtimeOptionsCollector


async def main():
    """Test contract fetching."""
    print("="*70)
    print("TESTING SPXW CONTRACT FETCHING")
    print("="*70)
    print()

    # Initialize collector with narrow parameters for testing
    collector = RealtimeOptionsCollector(
        max_dte=1,      # Only 0-1 DTE
        min_dte=0,
        strike_range_pct=0.02,  # Only ±2% from ATM
    )

    # Initialize Schwab client
    await collector.initialize()

    # Fetch active contracts
    print("\nFetching SPXW contracts...")
    contracts = await collector.get_active_spxw_contracts()

    print(f"\n{'='*70}")
    print("RESULTS")
    print(f"{'='*70}")
    print(f"Total contracts found: {len(contracts)}")

    if contracts:
        print(f"\nFirst 10 contracts:")
        for i, symbol in enumerate(contracts[:10], 1):
            details = collector.contract_details.get(symbol, {})
            print(f"  {i}. {symbol}")
            print(f"     Strike: ${details.get('strike_price', 'N/A')}")
            print(f"     Type: {details.get('option_type', 'N/A')}")
            print(f"     Expiration: {details.get('expiration_date', 'N/A')}")

    print(f"\n{'='*70}")
    print("TEST COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
