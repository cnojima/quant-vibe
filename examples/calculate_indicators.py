"""
Example: Calculate technical indicators.

This example demonstrates how to calculate various technical indicators
on market data.
"""

from quant_vibe.data import DataStore
from quant_vibe.indicators import calculate_sma, calculate_ema, calculate_rsi, calculate_macd


def main() -> None:
    """Calculate and display technical indicators."""
    # Load data
    store = DataStore()
    symbol = "AAPL"
    data = store.load(symbol)

    if data is None:
        print(f"No data found for {symbol}. Run fetch_market_data.py first.")
        return

    # Calculate indicators
    print(f"Calculating indicators for {symbol}...")

    data["SMA_50"] = calculate_sma(data["Close"], 50)
    data["SMA_200"] = calculate_sma(data["Close"], 200)
    data["EMA_12"] = calculate_ema(data["Close"], 12)
    data["RSI"] = calculate_rsi(data["Close"], 14)

    macd, signal, histogram = calculate_macd(data["Close"])
    data["MACD"] = macd
    data["MACD_Signal"] = signal
    data["MACD_Hist"] = histogram

    # Display recent data
    print("\nRecent data with indicators:")
    print(
        data[
            [
                "Close",
                "SMA_50",
                "SMA_200",
                "EMA_12",
                "RSI",
                "MACD",
                "MACD_Signal",
            ]
        ]
        .tail(10)
        .to_string()
    )


if __name__ == "__main__":
    main()
