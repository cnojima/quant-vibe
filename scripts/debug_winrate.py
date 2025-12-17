import sys
sys.path.insert(0, 'src')

import sqlite3
import pandas as pd
from quant_vibe.backtesting import BacktestEngine
from quant_vibe.strategies import EMACrossoverStrategy

# Load small sample
conn = sqlite3.connect('data/backtest_db/multi_symbol.db')
df = pd.read_sql_query('SELECT timestamp, open, high, low, close, volume FROM price_bars WHERE symbol = ? AND frequency = ? ORDER BY timestamp LIMIT 1000', conn, params=('SPY', '5min'))
conn.close()
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
df.set_index('timestamp', inplace=True)
df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

# Run backtest
strategy = EMACrossoverStrategy(fast_period=12, slow_period=26)
engine = BacktestEngine(initial_capital=10000, commission=0.001)
portfolio = engine.run(strategy, df)

# Check the signals
buy_signals = portfolio[portfolio['Signal'] == 1]
sell_signals = portfolio[portfolio['Signal'] == -1]

print(f"Total Buy signals: {len(buy_signals)}")
print(f"Total Sell signals: {len(sell_signals)}")

# Manual calculation
buy_idxs = buy_signals.index.tolist()
sell_idxs = sell_signals.index.tolist()
used_buys = set()
winning_trades = 0
total_trades = 0

for sell_idx in sell_idxs:
    matching_buy = None
    for buy_idx in reversed(buy_idxs):
        if buy_idx < sell_idx and buy_idx not in used_buys:
            matching_buy = buy_idx
            break
    
    if matching_buy is not None:
        buy_value = portfolio.loc[matching_buy, 'Total']
        sell_value = portfolio.loc[sell_idx, 'Total']
        profit = sell_value - buy_value
        
        if sell_value > buy_value:
            winning_trades += 1
        
        total_trades += 1
        used_buys.add(matching_buy)
        
        if total_trades <= 5:  # Show first 5 trades
            print(f"\nTrade {total_trades}:")
            print(f"  Buy at {matching_buy}: ${buy_value:.2f}")
            print(f"  Sell at {sell_idx}: ${sell_value:.2f}")
            print(f"  Profit: ${profit:.2f} {'WIN' if profit > 0 else 'LOSS'}")

print(f"\nTotal Trades: {total_trades}")
print(f"Winning Trades: {winning_trades}")
print(f"Win Rate: {(winning_trades / total_trades * 100):.2f}% (should be 0-100%)")
