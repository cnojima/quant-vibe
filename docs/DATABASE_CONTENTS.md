# Backtest Database Contents

**Database:** `backtest.db`  
**Location:** `quant-vibe/data/backtest_db/backtest.db`  
**Last Updated:** 2025-12-14 07:14:45  
**Size:** 13508.0 KB (13.19 MB)  
**Total Bars:** 106,741

## Summary

- **Symbols:** $SPX, QQQ, SPY
- **Frequencies:** 1min, 5min, daily

## Contents by Symbol and Frequency

| Symbol | Frequency | Bars | Start Date | End Date |
|--------|-----------|------|------------|----------|
| $SPX | 1min | 13,765 | 2025-10-27 | 2025-12-12 |
| $SPX | 5min | 10,462 | 2025-06-16 | 2025-12-12 |
| $SPX | daily | 2,515 | 2015-12-14 | 2025-12-12 |
| QQQ | 5min | 40,000 | 2025-05-27 | 2025-12-13 |
| SPY | 5min | 39,999 | 2025-05-22 | 2025-12-13 |

## Schema

```sql
CREATE TABLE price_bars (
    symbol TEXT NOT NULL,
    frequency TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    PRIMARY KEY (symbol, frequency, timestamp)
)
```

## Usage

Load data for backtesting:

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect('data/backtest_db/backtest.db')

# Load SPY 5-minute data
query = """
    SELECT timestamp, open, high, low, close, volume 
    FROM price_bars 
    WHERE symbol = ? AND frequency = ?
    ORDER BY timestamp ASC
"""
df = pd.read_sql_query(query, conn, params=['SPY', '5min'])
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
df.set_index('timestamp', inplace=True)

conn.close()
```

## Data Sources

- **$SPX Daily:** 10 years of S&P 500 Index daily bars (2015-2025)
- **$SPX Intraday:** 1-minute and 5-minute bars (recent data)
- **SPY:** S&P 500 ETF 5-minute bars (6+ months)
- **QQQ:** Nasdaq-100 ETF 5-minute bars (6+ months)

All data fetched from Schwab API.
