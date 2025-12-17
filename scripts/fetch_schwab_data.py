#!/usr/bin/env python3
"""
Fetch Market Data from Schwab API

This script uses your Schwab bearer token to fetch real historical data
and save it for backtesting.

Usage:
    python scripts/fetch_schwab_data.py AAPL MSFT
    python scripts/fetch_schwab_data.py --popular
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data import DataStore
from quant_vibe.data.schwab_client import SchwabClient

# Popular stocks for backtesting
POPULAR_STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "TSLA", "META", "SPY", "QQQ", "DIA"
]


def fetch_symbols(symbols: list, period_years: int = 2):
    """Fetch data for list of symbols."""
    try:
        client = SchwabClient()
        store = DataStore()
        
        print(f"\n📊 Fetching {len(symbols)} symbols from Schwab API")
        print(f"Period: {period_years} years")
        print(f"Data will be cached in: {store.data_dir}\n")
        
        success = 0
        for symbol in symbols:
            try:
                print(f"Fetching {symbol}...", end=" ")
                data = client.get_price_history(
                    symbol,
                    period_type="year",
                    period=period_years
                )
                
                if not data.empty:
                    store.save(symbol, data)
                    print(f"✓ {len(data)} days ({data.index[0].date()} to {data.index[-1].date()})")
                    success += 1
                else:
                    print("✗ No data returned")
                    
            except Exception as e:
                print(f"✗ Error: {e}")
        
        print(f"\n✅ Successfully fetched {success}/{len(symbols)} symbols")
        return success
        
    except ValueError as e:
        print(f"\n❌ {e}")
        print("\nMake sure SCHWAB_BEARER_TOKEN is set in .env file!")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 0


def main():
    print("="*70)
    print("SCHWAB DATA FETCHER")
    print("="*70)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--popular":
        symbols = POPULAR_STOCKS
        print(f"\nFetching {len(symbols)} popular stocks...")
    elif len(sys.argv) > 1:
        symbols = [s.upper() for s in sys.argv[1:]]
        print(f"\nFetching: {', '.join(symbols)}")
    else:
        symbols = ["AAPL", "SPY"]
        print(f"\nFetching default: {', '.join(symbols)}")
        print("(Use: python scripts/fetch_schwab_data.py SYMBOL1 SYMBOL2)")
        print("(Or: python scripts/fetch_schwab_data.py --popular)")
    
    success = fetch_symbols(symbols)
    
    if success > 0:
        print("\n" + "="*70)
        print("Next steps:")
        print("  python examples/compare_strategies.py")
        print("  # Your strategies now use real Schwab data!")
        print("="*70)


if __name__ == "__main__":
    main()
