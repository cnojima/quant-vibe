"""Export database contents as markdown."""

import sqlite3
from pathlib import Path
from datetime import datetime

def export_contents():
    db_path = Path(__file__).parent.parent / "data" / "backtest_db" / "backtest.db"
    output_path = Path(__file__).parent.parent / "data" / "backtest_db" / "DATABASE_CONTENTS.md"
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get database info
    cursor.execute('SELECT COUNT(*) FROM price_bars')
    total_count = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT symbol, frequency, COUNT(*), 
               datetime(MIN(timestamp), 'unixepoch'),
               datetime(MAX(timestamp), 'unixepoch')
        FROM price_bars 
        GROUP BY symbol, frequency 
        ORDER BY symbol, frequency
    """)
    rows = cursor.fetchall()
    
    cursor.execute('SELECT DISTINCT symbol FROM price_bars ORDER BY symbol')
    symbols = [r[0] for r in cursor.fetchall()]
    
    cursor.execute('SELECT DISTINCT frequency FROM price_bars ORDER BY frequency')
    frequencies = [r[0] for r in cursor.fetchall()]
    
    db_size = db_path.stat().st_size
    
    # Generate markdown
    md_content = f"""# Backtest Database Contents

**Database:** `backtest.db`  
**Location:** `{db_path}`  
**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Size:** {db_size / 1024:.1f} KB ({db_size / (1024*1024):.2f} MB)  
**Total Bars:** {total_count:,}

## Summary

- **Symbols:** {', '.join(symbols)}
- **Frequencies:** {', '.join(frequencies)}

## Contents by Symbol and Frequency

| Symbol | Frequency | Bars | Start Date | End Date |
|--------|-----------|------|------------|----------|
"""
    
    for row in rows:
        symbol, freq, count, min_date, max_date = row
        start_date = min_date.split()[0]  # Extract date only
        end_date = max_date.split()[0]
        md_content += f"| {symbol} | {freq} | {count:,} | {start_date} | {end_date} |\n"
    
    md_content += """
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
query = \"\"\"
    SELECT timestamp, open, high, low, close, volume 
    FROM price_bars 
    WHERE symbol = ? AND frequency = ?
    ORDER BY timestamp ASC
\"\"\"
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
"""
    
    # Write to file
    with open(output_path, 'w') as f:
        f.write(md_content)
    
    conn.close()
    
    print(f"✅ Exported database contents to: {output_path}")
    print(f"   File size: {output_path.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    export_contents()
