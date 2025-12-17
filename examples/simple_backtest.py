"""
Example: Simple SMA crossover backtest.

This example demonstrates how to:
1. Fetch market data
2. Apply a trading strategy
3. Run a backtest
4. Analyze performance
"""

from quant_vibe.data import MarketDataClient, DataStore
from quant_vibe.strategies import SMACrossoverStrategy
from quant_vibe.backtesting import BacktestEngine, PerformanceMetrics


def main() -> None:
    """Run a simple backtest example."""
    # Initialize components
    client = MarketDataClient(provider="alpha_vantage")
    store = DataStore()

    # Fetch or load data
    symbol = "AAPL"
    print(f"Fetching data for {symbol}...")

    # Try to load from cache first
    data = store.load(symbol)
    if data is None:
        # Fetch from API
        data = client.fetch_daily_data(symbol)
        store.save(symbol, data)
        print(f"Fetched {len(data)} days of data")
    else:
        print(f"Loaded {len(data)} days from cache")

    # Create strategy
    strategy = SMACrossoverStrategy(fast_period=50, slow_period=200)

    # Run backtest
    print(f"\nRunning backtest with {strategy.name}...")
    engine = BacktestEngine(initial_capital=100000.0, commission=0.001)
    portfolio = engine.run(strategy, data)

    # Calculate metrics
    metrics = PerformanceMetrics.calculate(portfolio)

    # Display results
    print("\n" + "=" * 50)
    print("BACKTEST RESULTS")
    print("=" * 50)
    print(f"Total Return: {metrics['total_return']:.2f}%")
    print(f"Annual Return: {metrics['annual_return']:.2f}%")
    print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"Max Drawdown: {metrics['max_drawdown']:.2f}%")
    print(f"Volatility: {metrics['volatility']:.2f}%")
    print(f"Win Rate: {metrics['win_rate']:.2f}%")
    print(f"Total Trades: {engine.results['total_trades']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
