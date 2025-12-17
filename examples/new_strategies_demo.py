"""Demo of the new trading strategies.

This script demonstrates how to use all the newly implemented strategies
in the backtester.
"""

import sys
from pathlib import Path
import sqlite3
import pandas as pd

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.backtesting import BacktestEngine, PerformanceMetrics
from quant_vibe.strategies import (
    EMACrossoverStrategy,
    MACDCrossoverStrategy,
    MACDHistogramStrategy,
    RSIMAFilterStrategy,
    TripleMAStrategy,
    BollingerBandsStrategy,
    MultiRSIStrategy,
    RSIMACDConfirmationStrategy,
)


def load_data_from_db(db_path: str, symbol: str, frequency: str = "5min") -> pd.DataFrame:
    """Load price data from SQLite database."""
    conn = sqlite3.connect(db_path)
    
    query = """
    SELECT timestamp, open, high, low, close, volume
    FROM price_bars
    WHERE symbol = ? AND frequency = ?
    ORDER BY timestamp
    """
    
    df = pd.read_sql_query(query, conn, params=(symbol, frequency))
    conn.close()
    
    # Convert timestamp to datetime and set as index
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    df.set_index('timestamp', inplace=True)
    
    # Rename columns to match expected format (OHLCV with capital letters)
    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    
    return df


def main():
    """Run backtest demo with all new strategies."""
    
    # Load data from SQLite database
    db_path = "./data/backtest_db/multi_symbol.db"
    symbol = "SPY"
    frequency = "5min"
    
    print(f"Loading {symbol} data from database...")
    try:
        data = load_data_from_db(db_path, symbol, frequency)
    except Exception as e:
        print(f"Error loading data: {e}")
        print(f"Please ensure {db_path} exists and contains data.")
        return
    
    if data is None or data.empty:
        print(f"No data found for {symbol} at {frequency} frequency")
        return
    
    print(f"Loaded {len(data)} bars of {symbol} data ({frequency})")
    print(f"Date range: {data.index[0]} to {data.index[-1]}\n")
    
    # Define all strategies to test
    strategies = [
        EMACrossoverStrategy(fast_period=12, slow_period=26),
        MACDCrossoverStrategy(),
        MACDHistogramStrategy(),
        RSIMAFilterStrategy(ma_period=200),
        TripleMAStrategy(short_period=5, medium_period=20, long_period=50),
        BollingerBandsStrategy(period=20, num_std=2.0),
        MultiRSIStrategy(rsi_periods=(7, 14, 21)),
        RSIMACDConfirmationStrategy(),
    ]
    
    # Run backtest for each strategy
    initial_capital = 10000
    results = []
    
    print("=" * 80)
    print(f"Running backtests with ${initial_capital:,.2f} initial capital")
    print("=" * 80)
    
    # Create backtest engine once
    engine = BacktestEngine(
        initial_capital=initial_capital,
        commission=0.001  # 0.1% commission
    )
    
    for strategy in strategies:
        print(f"\n{strategy.name}")
        print("-" * 80)
        
        # Run backtest
        portfolio = engine.run(strategy, data)
        metrics = PerformanceMetrics.calculate(portfolio)
        results.append((strategy.name, portfolio, metrics))
        
        # Display metrics
        print(f"Total Return:     {metrics['total_return']:.2%}")
        print(f"Sharpe Ratio:     {metrics['sharpe_ratio']:.2f}")
        print(f"Max Drawdown:     {metrics['max_drawdown']:.2%}")
        print(f"Win Rate:         {metrics['win_rate']:.2%}")
        print(f"Total Trades:     {engine.results['total_trades']}")
        print(f"Final Capital:    ${portfolio['Total'].iloc[-1]:,.2f}")
    
    # Summary comparison
    print("\n" + "=" * 80)
    print("SUMMARY - Sorted by Total Return")
    print("=" * 80)
    print(f"{'Strategy':<40} {'Return':>12} {'Sharpe':>10} {'Trades':>8}")
    print("-" * 80)
    
    # Sort by total return
    sorted_results = sorted(
        results,
        key=lambda x: x[2]['total_return'],
        reverse=True
    )
    
    for name, portfolio, metrics in sorted_results:
        trades = (portfolio['Signal'] != 0).sum()
        print(
            f"{name:<40} "
            f"{metrics['total_return']:>11.2%} "
            f"{metrics['sharpe_ratio']:>10.2f} "
            f"{trades:>8}"
        )
    
    print("\n" + "=" * 80)
    print("Demo complete! You can now:")
    print("1. Modify strategy parameters to optimize performance")
    print("2. Combine strategies or create your own variations")
    print("3. Test on different symbols and timeframes")
    print("=" * 80)


if __name__ == "__main__":
    main()
