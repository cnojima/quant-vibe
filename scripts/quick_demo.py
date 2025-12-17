#!/usr/bin/env python3
"""
Quick Demo - Test the platform in 30 seconds

This script demonstrates the basic workflow without needing API keys.
It generates sample data and runs a quick backtest comparison.
"""

import pandas as pd
import numpy as np
from datetime import datetime

# Set up path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.strategies import SMACrossoverStrategy, RSIStrategy
from quant_vibe.backtesting import BacktestEngine, PerformanceMetrics


def generate_sample_data(days=365):
    """Generate sample price data for testing."""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # Generate somewhat realistic price movement
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.02, days)
    price = 100 * (1 + returns).cumprod()
    
    # Add some volatility
    high = price * (1 + np.random.uniform(0, 0.02, days))
    low = price * (1 - np.random.uniform(0, 0.02, days))
    
    data = pd.DataFrame({
        'Open': price * (1 + np.random.uniform(-0.01, 0.01, days)),
        'High': high,
        'Low': low,
        'Close': price,
        'Volume': np.random.randint(1000000, 10000000, days)
    }, index=dates)
    
    return data


def main():
    print("\n" + "="*70)
    print("🚀 QUANT-VIBE QUICK DEMO")
    print("="*70)
    
    # Generate sample data
    print("\n📊 Generating sample market data (365 days)...")
    data = generate_sample_data(365)
    print(f"   ✓ Data generated: ${data['Close'].iloc[0]:.2f} → ${data['Close'].iloc[-1]:.2f}")
    print(f"   ✓ Return: {((data['Close'].iloc[-1] / data['Close'].iloc[0] - 1) * 100):.2f}%")
    
    # Define strategies
    strategies = [
        ("SMA Fast (10/50)", SMACrossoverStrategy(fast_period=10, slow_period=50)),
        ("SMA Slow (50/200)", SMACrossoverStrategy(fast_period=50, slow_period=200)),
        ("RSI Standard (30/70)", RSIStrategy(rsi_period=14, oversold_threshold=30, overbought_threshold=70)),
        ("RSI Aggressive (20/80)", RSIStrategy(rsi_period=14, oversold_threshold=20, overbought_threshold=80)),
    ]
    
    # Backtest each strategy
    print("\n⚙️  Running backtests...")
    engine = BacktestEngine(initial_capital=100000.0, commission=0.001)
    results = []
    
    for name, strategy in strategies:
        portfolio = engine.run(strategy, data)
        metrics = PerformanceMetrics.calculate(portfolio)
        
        results.append({
            'Strategy': name,
            'Return (%)': metrics['total_return'],
            'Sharpe': metrics['sharpe_ratio'],
            'Max DD (%)': metrics['max_drawdown'],
            'Trades': engine.results['total_trades']
        })
        print(f"   ✓ {name}")
    
    # Display results
    print("\n" + "="*70)
    print("📈 RESULTS")
    print("="*70)
    
    results_df = pd.DataFrame(results)
    
    # Format for nice display
    for idx, row in results_df.iterrows():
        print(f"\n{row['Strategy']}")
        print(f"  Return:       {row['Return (%)']:>7.2f}%")
        print(f"  Sharpe Ratio: {row['Sharpe']:>7.2f}")
        print(f"  Max Drawdown: {row['Max DD (%)']:>7.2f}%")
        print(f"  Total Trades: {row['Trades']:>7.0f}")
    
    # Find best strategy
    best_idx = results_df['Sharpe'].idxmax()
    best_strategy = results_df.loc[best_idx]
    
    print("\n" + "="*70)
    print(f"🏆 Best Strategy: {best_strategy['Strategy']}")
    print(f"   (Highest Sharpe Ratio: {best_strategy['Sharpe']:.2f})")
    print("="*70)
    
    print("\n✅ Demo complete!")
    print("\nNext steps:")
    print("  1. Read QUICKSTART.md for your learning path")
    print("  2. Run: python examples/compare_strategies.py")
    print("  3. Try modifying src/quant_vibe/strategies/rsi_strategy.py")
    print("\n")


if __name__ == "__main__":
    main()
