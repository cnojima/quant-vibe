#!/usr/bin/env python3
"""
Fetch Real Market Data - No API Key Required!

This script uses yfinance (Yahoo Finance) to download real historical data.
It's completely FREE and requires NO API KEY.

Usage:
    python scripts/fetch_real_data.py AAPL MSFT GOOGL
    python scripts/fetch_real_data.py --all  # Fetch popular stocks
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yfinance as yf
from quant_vibe.data import DataStore


# Popular stocks for backtesting
POPULAR_STOCKS = [
    "AAPL",  # Apple
    "MSFT",  # Microsoft
    "GOOGL", # Google
    "TSLA",  # Tesla
    "AMZN",  # Amazon
    "NVDA",  # Nvidia
    "SPY",   # S&P 500 ETF
    "QQQ",   # Nasdaq ETF
]


def fetch_stock_data(symbol: str, period: str = "2y"):
    """
    Fetch historical data for a stock.
    
    Args:
        symbol: Stock ticker symbol
        period: Time period (1mo, 3mo, 6mo, 1y, 2y, 5y, max)
        
    Returns:
        DataFrame with OHLCV data
    """
    print(f"  Fetching {symbol}...", end=" ")
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period)
        
        # Rename columns to match our format
        data = data.rename(columns={
            'Open': 'Open',
            'High': 'High', 
            'Low': 'Low',
            'Close': 'Close',
            'Volume': 'Volume'
        })
        
        # Keep only OHLCV columns
        data = data[['Open', 'High', 'Low', 'Close', 'Volume']]
        
        print(f"✓ {len(data)} days ({data.index[0].date()} to {data.index[-1].date()})")
        return data
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def main():
    print("\n" + "="*70)
    print("📊 REAL MARKET DATA FETCHER (yfinance - FREE!)")
    print("="*70)
    
    # Parse arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        symbols = POPULAR_STOCKS
        print(f"\nFetching {len(symbols)} popular stocks...")
    elif len(sys.argv) > 1:
        symbols = sys.argv[1:]
        print(f"\nFetching {len(symbols)} symbols: {', '.join(symbols)}")
    else:
        symbols = ["AAPL", "SPY"]
        print(f"\nFetching default symbols: {', '.join(symbols)}")
        print("(Use: python scripts/fetch_real_data.py SYMBOL1 SYMBOL2 ...)")
    
    # Initialize data store
    store = DataStore()
    print(f"\nData will be cached in: {store.data_dir}")
    print()
    
    # Fetch each symbol
    success_count = 0
    for symbol in symbols:
        data = fetch_stock_data(symbol, period="2y")
        
        if data is not None and len(data) > 0:
            # Save to cache
            store.save(symbol, data, format="parquet")
            success_count += 1
    
    print("\n" + "="*70)
    print(f"✅ Successfully fetched {success_count}/{len(symbols)} symbols")
    print("="*70)
    
    if success_count > 0:
        print("\nNext steps:")
        print("  1. Run: python examples/compare_strategies.py")
        print("  2. Or: python scripts/quick_demo.py --real")
        print(f"  3. Data is cached in: {store.data_dir}")
        print("\nYour strategies will now use REAL market data! 🎉")
    

if __name__ == "__main__":
    main()
