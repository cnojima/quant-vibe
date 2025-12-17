"""
Tutorial: Compare Different Trading Strategies

This script helps you learn by:
1. Running multiple strategies on the same data
2. Comparing performance metrics side-by-side
3. Visualizing results

Usage:
    python examples/compare_strategies.py
"""

import pandas as pd
from quant_vibe.data import DataStore
from quant_vibe.strategies import SMACrossoverStrategy
from quant_vibe.strategies.rsi_strategy import RSIStrategy
from quant_vibe.backtesting import BacktestEngine, PerformanceMetrics


def run_strategy_comparison(symbol: str = "AAPL"):
    """Compare multiple strategies on the same data."""
    
    # Load data
    store = DataStore()
    data = store.load(symbol)
    
    if data is None:
        print(f"No cached data for {symbol}.")
        print(f"Run: python scripts/fetch_real_data.py {symbol}")
        print("Or: python scripts/fetch_real_data.py --all")
        return None
    
    print(f"\nLoaded {len(data)} days of {symbol} data")
    print(f"Date range: {data.index[0]} to {data.index[-1]}\n")
    
    # Define strategies to test
    strategies = [
        SMACrossoverStrategy(fast_period=10, slow_period=50),
        SMACrossoverStrategy(fast_period=50, slow_period=200),
        RSIStrategy(rsi_period=14, oversold_threshold=30, overbought_threshold=70),
        RSIStrategy(rsi_period=14, oversold_threshold=20, overbought_threshold=80),
    ]
    
    # Backtest each strategy
    results = []
    engine = BacktestEngine(initial_capital=100000.0, commission=0.001)
    
    for strategy in strategies:
        print(f"Testing: {strategy.name}...")
        portfolio = engine.run(strategy, data)
        metrics = PerformanceMetrics.calculate(portfolio)
        
        results.append({
            'Strategy': strategy.name,
            'Total Return (%)': f"{metrics['total_return']:.2f}",
            'Annual Return (%)': f"{metrics['annual_return']:.2f}",
            'Sharpe Ratio': f"{metrics['sharpe_ratio']:.2f}",
            'Max Drawdown (%)': f"{metrics['max_drawdown']:.2f}",
            'Volatility (%)': f"{metrics['volatility']:.2f}",
            'Win Rate (%)': f"{metrics['win_rate']:.2f}",
            'Total Trades': engine.results['total_trades']
        })
    
    # Create comparison table
    results_df = pd.DataFrame(results)
    
    print("\n" + "=" * 100)
    print("STRATEGY COMPARISON RESULTS")
    print("=" * 100)
    print(results_df.to_string(index=False))
    print("=" * 100)
    
    # Identify best strategy by Sharpe ratio
    best_idx = results_df['Sharpe Ratio'].astype(float).idxmax()
    print(f"\nBest Strategy (by Sharpe Ratio): {results_df.loc[best_idx, 'Strategy']}")
    
    return results_df


if __name__ == "__main__":
    results = run_strategy_comparison("AAPL")
    
    # TODO: Add visualization
    # - Plot equity curves for all strategies
    # - Show drawdown comparison
    # - Display monthly returns heatmap
