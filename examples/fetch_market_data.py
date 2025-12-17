"""
Example: Fetch and save market data.

This example shows how to fetch market data from various providers
and save it locally for later use.
"""

from quant_vibe.data import MarketDataClient, DataStore


def main() -> None:
    """Fetch and save market data."""
    # Initialize client and storage
    client = MarketDataClient(provider="alpha_vantage")
    store = DataStore()

    # Symbols to fetch
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA"]

    for symbol in symbols:
        print(f"Fetching data for {symbol}...")
        try:
            data = client.fetch_daily_data(symbol)
            store.save(symbol, data, format="parquet")
            print(f"  Saved {len(data)} days of data")
        except Exception as e:
            print(f"  Error: {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()
