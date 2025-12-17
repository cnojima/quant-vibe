"""Merge all databases into a single backtest.db."""

import sqlite3
from pathlib import Path

def merge_databases():
    """Merge spx_daily.db, spx_1min.db, and multi_symbol.db into backtest.db."""
    
    db_dir = Path(__file__).parent.parent / "data" / "backtest_db"
    
    # Source databases
    sources = {
        'spx_daily.db': db_dir / 'spx_daily.db',
        'spx_1min.db': db_dir / 'spx_1min.db',
        'multi_symbol.db': db_dir / 'multi_symbol.db'
    }
    
    # Target database
    target_db = db_dir / 'backtest.db'
    
    print("="*70)
    print("MERGING DATABASES INTO backtest.db")
    print("="*70)
    
    # Create target database
    target_conn = sqlite3.connect(target_db)
    target_cursor = target_conn.cursor()
    
    # Create table with unified schema
    target_cursor.execute("""
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
    
    # Create index for faster queries
    target_cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_symbol_freq_timestamp 
    ON price_bars(symbol, frequency, timestamp DESC)
    """)
    
    target_conn.commit()
    
    # Merge data from each source
    total_inserted = 0
    
    for db_name, db_path in sources.items():
        if not db_path.exists():
            print(f"\n⚠️  {db_name}: NOT FOUND, skipping")
            continue
        
        print(f"\n{'='*70}")
        print(f"Processing: {db_name}")
        print('-'*70)
        
        source_conn = sqlite3.connect(db_path)
        source_cursor = source_conn.cursor()
        
        # Get all data from source
        source_cursor.execute("""
            SELECT symbol, frequency, timestamp, open, high, low, close, volume 
            FROM price_bars
        """)
        
        rows = source_cursor.fetchall()
        
        if rows:
            # Insert into target (using INSERT OR IGNORE to avoid duplicates)
            target_cursor.executemany("""
                INSERT OR IGNORE INTO price_bars 
                (symbol, frequency, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            
            inserted = target_cursor.rowcount
            total_inserted += inserted
            
            # Show what was in this database
            source_cursor.execute("""
                SELECT symbol, frequency, COUNT(*) 
                FROM price_bars 
                GROUP BY symbol, frequency 
                ORDER BY symbol, frequency
            """)
            
            print("Source data:")
            for row in source_cursor.fetchall():
                print(f"  {row[0]:8} {row[1]:8} {row[2]:,} bars")
            
            print(f"\n✅ Inserted {inserted:,} rows from {db_name}")
        else:
            print(f"⚠️  No data found in {db_name}")
        
        source_conn.close()
    
    target_conn.commit()
    
    # Verify merged database
    print(f"\n{'='*70}")
    print("MERGED DATABASE SUMMARY")
    print("="*70)
    
    target_cursor.execute("SELECT COUNT(*) FROM price_bars")
    total_count = target_cursor.fetchone()[0]
    
    target_cursor.execute("""
        SELECT symbol, frequency, COUNT(*), 
               datetime(MIN(timestamp), 'unixepoch'),
               datetime(MAX(timestamp), 'unixepoch')
        FROM price_bars 
        GROUP BY symbol, frequency 
        ORDER BY symbol, frequency
    """)
    
    print(f"\nTotal rows: {total_count:,}")
    print("\nBreakdown by symbol and frequency:")
    print(f"{'Symbol':<10} {'Freq':<10} {'Bars':<12} {'Date Range'}")
    print("-"*70)
    
    for row in target_cursor.fetchall():
        symbol, freq, count, min_date, max_date = row
        date_range = f"{min_date[:10]} to {max_date[:10]}"
        print(f"{symbol:<10} {freq:<10} {count:<12,} {date_range}")
    
    # Get unique symbols and frequencies
    target_cursor.execute("SELECT DISTINCT symbol FROM price_bars ORDER BY symbol")
    symbols = [r[0] for r in target_cursor.fetchall()]
    
    target_cursor.execute("SELECT DISTINCT frequency FROM price_bars ORDER BY frequency")
    frequencies = [r[0] for r in target_cursor.fetchall()]
    
    db_size = target_db.stat().st_size
    
    print(f"\n{'='*70}")
    print(f"Database: {target_db}")
    print(f"Size: {db_size / 1024:.1f} KB ({db_size / (1024*1024):.2f} MB)")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Frequencies: {', '.join(frequencies)}")
    print("="*70)
    
    target_conn.close()
    
    print(f"\n✅ Successfully merged {len(sources)} databases into backtest.db")
    print(f"   Total unique bars: {total_count:,}")

if __name__ == "__main__":
    merge_databases()
