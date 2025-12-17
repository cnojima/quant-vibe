import sys
sys.path.insert(0, 'src')

import sqlite3
import pandas as pd
from quant_vibe.backtesting import BacktestEngine
from quant_vibe.strategies import EMACrossoverStrategy

# Load small sample
conn = sqlite3.connect('data/backtest_db/multi_symbol.db')
df = pd.read_sql_query('SELECT timestamp, open, high, low, close, volume FROM price_bars WHERE symbol = ? AND frequency = ? ORDER BY timestamp LIMIT 500', conn, params=('SPY', '5min'))
conn.close()
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
df.set_index('timestamp', inplace=True)
df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

# Run backtest
strategy = EMACrossoverStrategy(fast_period=5, slow_period=10)
engine = BacktestEngine(initial_capital=10000, commission=0.001)
portfolio = engine.run(strategy, df)

# Check portfolio
print('Portfolio Total column sample:')
print(portfolio[['Price', 'Signal', 'Shares', 'Holdings', 'Cash', 'Total']].head(20))
print(f'\nInitial Capital: {portfolio["Total"].iloc[0]:.2f}')
print(f'Final Capital: {portfolio["Total"].iloc[-1]:.2f}')
print(f'Return: {(portfolio["Total"].iloc[-1] / portfolio["Total"].iloc[0] - 1) * 100:.2f}%')

# Check returns
returns = portfolio["Returns"].dropna()
print('\nReturns stats:')
print(f'Count: {len(returns)}')
print(f'Positive: {(returns > 0).sum()}')
print(f'Negative: {(returns < 0).sum()}')
print(f'Win Rate (current calc): {(returns > 0).sum() / len(returns) * 100:.2f}%')

# Check trades
trades = portfolio[portfolio['Signal'] != 0]
print(f'\nTrades: {len(trades)}')
print(trades[['Price', 'Signal', 'Shares', 'Total']].head(10))
