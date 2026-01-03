"""Fetch 10 years of daily $SPX data from Schwab API."""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.utils import now_utc

def fetch_spx_10years():
    """Fetch 10 years of daily bars for $SPX."""
    
    print("="*70)
    print("FETCHING 10 YEARS OF DAILY $SPX DATA")
    print("="*70)
    
    # Initialize Schwab client
    print("\nConnecting to Schwab API...")
    schwab = SchwabDevClient()
    print("✅ Connected!\n")
    
    # Calculate date range
    end_date = now_utc()
    start_date = end_date - timedelta(days=365 * 10)  # 10 years
    
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print("Symbol: $SPX (S&P 500 Index)")
    print("Frequency: Daily bars\n")
    
    # For daily data, Schwab allows up to 20 years in a single request
    # We'll fetch all 10 years at once using YEAR period type
    
    print("Fetching all 10 years in a single request...\n")
    
    try:
        data = schwab.get_price_history(
            "$SPX",
            period_type="year",
            period=10,
            frequency_type="daily",
            frequency=1
        )
        
        if data.empty:
            print("❌ No data returned")
            return None
            
        print(f"✅ Successfully fetched {len(data):,} bars\n")
    except Exception as e:
        print(f"❌ Error: {e}")
        return None
    
    # Display results
    print("="*70)
    print("DOWNLOAD SUMMARY")
    print("="*70)
    print(f"Total bars: {len(data):,}")
    print(f"Date range: {data.index[0].date()} to {data.index[-1].date()}")
    print(f"Duration: {(data.index[-1] - data.index[0]).days} days")
    print("Status: Success")
    print()
    
    # Display statistics
    print("Price Statistics:")
    print(f"  Open:  ${data['Open'].min():.2f} - ${data['Open'].max():.2f}")
    print(f"  High:  ${data['High'].min():.2f} - ${data['High'].max():.2f}")
    print(f"  Low:   ${data['Low'].min():.2f} - ${data['Low'].max():.2f}")
    print(f"  Close: ${data['Close'].min():.2f} - ${data['Close'].max():.2f}")
    print(f"  Latest Close: ${data['Close'].iloc[-1]:.2f}")
    print()
    
    # Display sample data
    print("First 5 bars:")
    print(data.head())
    print("\nLast 5 bars:")
    print(data.tail())
    
    # Save to CSV
    output_dir = Path(__file__).parent.parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "spx_daily_10years.csv"
    
    data.to_csv(output_file)
    file_size = output_file.stat().st_size
    print(f"\n✅ Data saved to: {output_file}")
    print(f"   File size: {file_size / 1024:.1f} KB ({file_size / (1024*1024):.2f} MB)")
    
    # Save to SQLite database
    db_dir = Path(__file__).parent.parent / "data" / "backtest_db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "spx_daily.db"
    
    print(f"\n{'='*70}")
    print("SAVING TO SQLITE DATABASE")
    print(f"{'='*70}")
    print(f"Database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table with same schema as multi_symbol.db and spx_1min.db
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_bars (
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
    """)
    
    # Prepare data for insertion
    records = []
    for timestamp, row in data.iterrows():
        records.append((
            '$SPX',  # symbol
            'daily',  # frequency
            int(timestamp.timestamp()),
            float(row['Open']),
            float(row['High']),
            float(row['Low']),
            float(row['Close']),
            int(row['Volume'])
        ))
    
    # Insert or replace (upsert)
    cursor.executemany("""
        INSERT OR REPLACE INTO price_bars 
        (symbol, frequency, timestamp, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, records)
    
    conn.commit()
    
    # Verify storage
    cursor.execute("SELECT COUNT(*) FROM price_bars WHERE symbol = '$SPX' AND frequency = 'daily'")
    total_bars = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT datetime(MIN(timestamp), 'unixepoch'), 
               datetime(MAX(timestamp), 'unixepoch')
        FROM price_bars WHERE symbol = '$SPX' AND frequency = 'daily'
    """)
    min_date, max_date = cursor.fetchone()
    
    conn.close()
    
    db_size = db_path.stat().st_size
    print(f"\n✅ Stored {len(records):,} bars in database")
    print("   Symbol: $SPX")
    print("   Frequency: daily")
    print(f"   Total bars: {total_bars:,}")
    print(f"   Date range: {min_date} to {max_date}")
    print(f"   Database size: {db_size / 1024:.1f} KB ({db_size / (1024*1024):.2f} MB)")
    print(f"{'='*70}")
    
    return data

if __name__ == "__main__":
    fetch_spx_10years()
