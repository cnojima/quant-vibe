"""Data storage and caching using SQLite."""

from pathlib import Path
from typing import Optional
import sqlite3

import pandas as pd


class DataStore:
    """Local storage for market data using SQLite database."""

    def __init__(self, db_path: str = "./data/backtest_db/backtest.db") -> None:
        """
        Initialize data store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database schema if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
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
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol_freq_timestamp
            ON price_bars(symbol, frequency, timestamp DESC)
        """)
        
        conn.commit()
        conn.close()

    def save(self, symbol: str, data: pd.DataFrame, frequency: str = "1d") -> None:
        """
        Save market data to SQLite database.

        Args:
            symbol: Stock ticker symbol
            data: DataFrame with OHLCV data (index should be datetime)
            frequency: Data frequency ('1d', '5min', '1min', etc.)
        """
        conn = sqlite3.connect(self.db_path)
        
        # Prepare data for insertion
        df = data.copy()
        df.columns = [col.lower() for col in df.columns]  # Normalize to lowercase
        
        # Convert datetime index to unix timestamp
        df['timestamp'] = df.index.astype('int64') // 10**9
        df['symbol'] = symbol
        df['frequency'] = frequency
        
        # Reorder columns to match schema
        df = df[['symbol', 'frequency', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
        # Insert or replace data
        df.to_sql('price_bars', conn, if_exists='append', index=False)
        
        conn.commit()
        conn.close()

    def load(self, symbol: str, frequency: str = "1d", 
             start_date: Optional[str] = None, 
             end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Load market data from SQLite database.

        Args:
            symbol: Stock ticker symbol
            frequency: Data frequency ('1d', '5min', '1min', etc.)
            start_date: Optional start date filter (ISO format: 'YYYY-MM-DD')
            end_date: Optional end date filter (ISO format: 'YYYY-MM-DD')

        Returns:
            DataFrame with OHLCV data if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        
        query = """
        SELECT timestamp, open, high, low, close, volume
        FROM price_bars
        WHERE symbol = ? AND frequency = ?
        """
        params = [symbol, frequency]
        
        if start_date:
            start_ts = pd.Timestamp(start_date).timestamp()
            query += " AND timestamp >= ?"
            params.append(start_ts)
        
        if end_date:
            end_ts = pd.Timestamp(end_date).timestamp()
            query += " AND timestamp <= ?"
            params.append(end_ts)
        
        query += " ORDER BY timestamp"
        
        try:
            df = pd.read_sql_query(query, conn, params=params)
        except pd.io.sql.DatabaseError:
            conn.close()
            return None
        
        conn.close()
        
        if df.empty:
            return None
        
        # Convert timestamp to datetime and set as index
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
        df.set_index('timestamp', inplace=True)
        
        # Capitalize column names to match expected format
        df.columns = [col.capitalize() for col in df.columns]
        
        return df

    def list_symbols(self, frequency: Optional[str] = None) -> list[str]:
        """
        List all symbols available in the database.

        Args:
            frequency: Optional frequency filter

        Returns:
            List of symbol strings
        """
        conn = sqlite3.connect(self.db_path)
        
        if frequency:
            query = "SELECT DISTINCT symbol FROM price_bars WHERE frequency = ? ORDER BY symbol"
            params = (frequency,)
        else:
            query = "SELECT DISTINCT symbol FROM price_bars ORDER BY symbol"
            params = ()
        
        cursor = conn.cursor()
        cursor.execute(query, params)
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return symbols

    def get_date_range(self, symbol: str, frequency: str = "1d") -> Optional[tuple[pd.Timestamp, pd.Timestamp]]:
        """
        Get the date range available for a symbol.

        Args:
            symbol: Stock ticker symbol
            frequency: Data frequency

        Returns:
            Tuple of (start_date, end_date) or None if no data
        """
        conn = sqlite3.connect(self.db_path)
        
        query = """
        SELECT MIN(timestamp), MAX(timestamp)
        FROM price_bars
        WHERE symbol = ? AND frequency = ?
        """
        
        cursor = conn.cursor()
        cursor.execute(query, (symbol, frequency))
        result = cursor.fetchone()
        conn.close()
        
        if result[0] is None:
            return None
        
        start_date = pd.to_datetime(result[0], unit='s')
        end_date = pd.to_datetime(result[1], unit='s')
        
        return (start_date, end_date)
