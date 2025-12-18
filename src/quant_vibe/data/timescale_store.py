"""
TimescaleDB data storage for high-frequency options data.

This module provides TimescaleDB integration for storing and querying:
- 1-minute options bars (OHLCV)
- Quote data (bid/ask)
- Greeks (delta, gamma, theta, vega, etc.)

Features:
- Automatic compression for older data
- Continuous aggregates for higher timeframes (5min, 15min, 1hour, daily)
- Optimized indexes for fast queries
- Bulk insert capabilities for efficient data loading
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch, RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

load_dotenv()


class TimescaleStore:
    """
    TimescaleDB storage client for options timeseries data.

    This class handles all database operations including:
    - Inserting options bars (1-minute resolution)
    - Querying data by time range, ticker, strike, etc.
    - Accessing continuous aggregates for higher timeframes
    - Bulk operations for efficient data loading
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        pool_size: int = 5,
    ):
        """
        Initialize TimescaleDB connection.

        Args:
            host: Database host (defaults to TIMESCALE_HOST env var or 'localhost')
            port: Database port (defaults to TIMESCALE_PORT env var or 5432)
            database: Database name (defaults to TIMESCALE_DB env var or 'options_data')
            user: Database user (defaults to TIMESCALE_USER env var or 'quantvibe')
            password: Database password (defaults to TIMESCALE_PASSWORD env var)
            pool_size: Connection pool size
        """
        self.host = host or os.getenv("TIMESCALE_HOST", "localhost")
        self.port = port or int(os.getenv("TIMESCALE_PORT", "5432"))
        self.database = database or os.getenv("TIMESCALE_DB", "options_data")
        self.user = user or os.getenv("TIMESCALE_USER", "quantvibe")
        self.password = password or os.getenv("TIMESCALE_PASSWORD", "quantvibe_dev")

        # Create connection pool
        self.pool = SimpleConnectionPool(
            minconn=1,
            maxconn=pool_size,
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
        )

        # SQLAlchemy engine (lazy initialization)
        self._engine = None

    @property
    def engine(self):
        """Get SQLAlchemy engine for pandas operations (lazy initialization)."""
        if self._engine is None:
            connection_string = (
                f"postgresql://{self.user}:{self.password}@"
                f"{self.host}:{self.port}/{self.database}"
            )
            # Use NullPool to avoid connection pool conflicts with psycopg2 pool
            self._engine = create_engine(connection_string, poolclass=NullPool)
        return self._engine

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool."""
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    def insert_option_bar(
        self,
        timestamp: datetime,
        option_ticker: str,
        underlying_ticker: str,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        strike_price: float,
        contract_type: str,
        expiration_date: datetime,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        bid_size: Optional[int] = None,
        ask_size: Optional[int] = None,
        vwap: Optional[float] = None,
        transactions: Optional[int] = None,
        implied_volatility: Optional[float] = None,
        delta: Optional[float] = None,
        gamma: Optional[float] = None,
        theta: Optional[float] = None,
        vega: Optional[float] = None,
        rho: Optional[float] = None,
        data_source: str = "combined",
    ) -> None:
        """
        Insert a single options bar into the database.

        Args:
            timestamp: Bar timestamp
            option_ticker: Option contract ticker (e.g., 'O:SPX241220C04500000')
            underlying_ticker: Underlying ticker (e.g., 'SPX')
            open_price: Opening price
            high: High price
            low: Low price
            close: Closing price
            volume: Volume
            strike_price: Strike price
            contract_type: 'call' or 'put'
            expiration_date: Contract expiration date
            bid: Bid price (optional)
            ask: Ask price (optional)
            bid_size: Bid size (optional)
            ask_size: Ask size (optional)
            vwap: Volume-weighted average price (optional)
            transactions: Number of transactions (optional)
            implied_volatility: Implied volatility (optional)
            delta: Delta greek (optional)
            gamma: Gamma greek (optional)
            theta: Theta greek (optional)
            vega: Vega greek (optional)
            rho: Rho greek (optional)
            data_source: Source of data ('massive', 'schwab', or 'combined')
        """
        query = """
        INSERT INTO options_bars (
            timestamp, option_ticker, underlying_ticker,
            open, high, low, close, volume, vwap, transactions,
            bid, ask, bid_size, ask_size,
            strike_price, contract_type, expiration_date,
            implied_volatility, delta, gamma, theta, vega, rho,
            data_source
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (timestamp, option_ticker) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            vwap = EXCLUDED.vwap,
            transactions = EXCLUDED.transactions,
            bid = EXCLUDED.bid,
            ask = EXCLUDED.ask,
            bid_size = EXCLUDED.bid_size,
            ask_size = EXCLUDED.ask_size,
            implied_volatility = EXCLUDED.implied_volatility,
            delta = EXCLUDED.delta,
            gamma = EXCLUDED.gamma,
            theta = EXCLUDED.theta,
            vega = EXCLUDED.vega,
            rho = EXCLUDED.rho,
            data_source = EXCLUDED.data_source
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        timestamp,
                        option_ticker,
                        underlying_ticker,
                        open_price,
                        high,
                        low,
                        close,
                        volume,
                        vwap,
                        transactions,
                        bid,
                        ask,
                        bid_size,
                        ask_size,
                        strike_price,
                        contract_type,
                        expiration_date,
                        implied_volatility,
                        delta,
                        gamma,
                        theta,
                        vega,
                        rho,
                        data_source,
                    ),
                )
            conn.commit()

    def bulk_insert_option_bars(self, bars: List[Dict[str, Any]], batch_size: int = 1000) -> int:
        """
        Bulk insert options bars for efficient data loading.

        Args:
            bars: List of dictionaries containing bar data
            batch_size: Number of rows to insert per batch

        Returns:
            Number of rows inserted

        Example:
            >>> bars = [
            ...     {
            ...         'timestamp': datetime(2024, 1, 1, 9, 30),
            ...         'option_ticker': 'O:SPX241220C04500000',
            ...         'underlying_ticker': 'SPX',
            ...         'open': 100.5,
            ...         'high': 101.0,
            ...         'low': 100.0,
            ...         'close': 100.75,
            ...         'volume': 1000,
            ...         'strike_price': 4500.0,
            ...         'contract_type': 'call',
            ...         'expiration_date': datetime(2024, 12, 20),
            ...     },
            ...     ...
            ... ]
            >>> store.bulk_insert_option_bars(bars)
        """
        query = """
        INSERT INTO options_bars (
            timestamp, option_ticker, underlying_ticker,
            open, high, low, close, volume, vwap, transactions,
            bid, ask, bid_size, ask_size,
            strike_price, contract_type, expiration_date,
            implied_volatility, delta, gamma, theta, vega, rho,
            data_source
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        ON CONFLICT (timestamp, option_ticker) DO NOTHING
        """

        rows = []
        for bar in bars:
            rows.append(
                (
                    bar["timestamp"],
                    bar["option_ticker"],
                    bar["underlying_ticker"],
                    bar.get("open"),
                    bar.get("high"),
                    bar.get("low"),
                    bar.get("close"),
                    bar.get("volume"),
                    bar.get("vwap"),
                    bar.get("transactions"),
                    bar.get("bid"),
                    bar.get("ask"),
                    bar.get("bid_size"),
                    bar.get("ask_size"),
                    bar.get("strike_price"),
                    bar.get("contract_type"),
                    bar.get("expiration_date"),
                    bar.get("implied_volatility"),
                    bar.get("delta"),
                    bar.get("gamma"),
                    bar.get("theta"),
                    bar.get("vega"),
                    bar.get("rho"),
                    bar.get("data_source", "combined"),
                )
            )

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                execute_batch(cur, query, rows, page_size=batch_size)
            conn.commit()

        return len(rows)

    def get_option_bars(
        self,
        option_ticker: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        timeframe: str = "1min",
    ) -> pd.DataFrame:
        """
        Get options bars for a specific contract.

        Args:
            option_ticker: Option contract ticker
            start_time: Start time (defaults to 30 days ago)
            end_time: End time (defaults to now)
            timeframe: Timeframe ('1min', '5min', '15min', '1hour', 'daily')

        Returns:
            DataFrame with OHLCV and quote data
        """
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(days=30)

        # Map timeframe to table/view
        table_map = {
            "1min": "options_bars",
            "5min": "options_bars_5min",
            "15min": "options_bars_15min",
            "1hour": "options_bars_1hour",
            "daily": "options_bars_daily",
        }

        table = table_map.get(timeframe, "options_bars")
        time_col = "timestamp" if timeframe == "1min" else "bucket"

        query = f"""
        SELECT
            {time_col} as timestamp,
            open, high, low, close, volume, vwap, transactions,
            bid, ask, bid_size, ask_size,
            implied_volatility, delta, gamma, theta, vega, rho
        FROM {table}
        WHERE option_ticker = %s
            AND {time_col} >= %s
            AND {time_col} <= %s
        ORDER BY {time_col} ASC
        """

        df = pd.read_sql_query(
            query, self.engine, params=(option_ticker, start_time, end_time), parse_dates=["timestamp"]
        )

        if not df.empty:
            df.set_index("timestamp", inplace=True)

        return df

    def get_options_chain_bars(
        self,
        underlying_ticker: str,
        expiration_date: datetime,
        timestamp: datetime,
        strike_min: Optional[float] = None,
        strike_max: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Get options chain data for a specific point in time.

        Args:
            underlying_ticker: Underlying ticker (e.g., 'SPX')
            expiration_date: Contract expiration date
            timestamp: Specific timestamp to query
            strike_min: Minimum strike price filter
            strike_max: Maximum strike price filter

        Returns:
            DataFrame with chain data at the specified timestamp
        """
        query = """
        SELECT
            option_ticker, strike_price, contract_type,
            open, high, low, close, volume, vwap,
            bid, ask, bid_size, ask_size,
            implied_volatility, delta, gamma, theta, vega, rho
        FROM options_bars
        WHERE underlying_ticker = %s
            AND expiration_date = %s
            AND timestamp = %s
        """

        params = [underlying_ticker, expiration_date, timestamp]

        if strike_min is not None:
            query += " AND strike_price >= %s"
            params.append(strike_min)

        if strike_max is not None:
            query += " AND strike_price <= %s"
            params.append(strike_max)

        query += " ORDER BY strike_price, contract_type"

        df = pd.read_sql_query(query, self.engine, params=tuple(params))

        return df

    def get_options_for_backtest(
        self,
        underlying_ticker: str,
        start_time: datetime,
        end_time: datetime,
        min_dte: Optional[int] = None,
        max_dte: Optional[int] = None,
        strike_range_pct: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Get options data optimized for backtesting.

        Args:
            underlying_ticker: Underlying ticker (e.g., 'SPXW')
            start_time: Start time for backtest
            end_time: End time for backtest
            min_dte: Minimum days to expiration filter
            max_dte: Maximum days to expiration filter
            strike_range_pct: Optional percentage range around ATM (e.g., 0.1 for ±10%)

        Returns:
            DataFrame with all options data in the time range, with columns:
            - timestamp, option_ticker (contract_symbol), strike_price, contract_type
            - expiration_date, open, high, low, close, volume
            - bid, ask, mark (calculated as mid), bid_size, ask_size
            - delta, gamma, theta, vega, rho, implied_volatility
        """
        query = """
        SELECT
            timestamp,
            option_ticker as contract_symbol,
            strike_price,
            contract_type as option_type,
            expiration_date,
            open, high, low, close, volume,
            bid, ask,
            (bid + ask) / 2.0 as mark,
            bid_size, ask_size,
            delta, gamma, theta, vega, rho,
            implied_volatility
        FROM options_bars
        WHERE underlying_ticker = %s
            AND timestamp >= %s
            AND timestamp <= %s
        """

        params = [underlying_ticker, start_time, end_time]

        # Add DTE filters if specified
        if min_dte is not None:
            query += " AND (expiration_date - timestamp::date) >= %s"
            params.append(min_dte)

        if max_dte is not None:
            query += " AND (expiration_date - timestamp::date) <= %s"
            params.append(max_dte)

        query += " ORDER BY timestamp, expiration_date, strike_price, contract_type"

        df = pd.read_sql_query(query, self.engine, params=tuple(params), parse_dates=['timestamp', 'expiration_date'])

        # Convert contract_type to uppercase for consistency
        if not df.empty and 'option_type' in df.columns:
            df['option_type'] = df['option_type'].str.upper()

        return df

    def get_underlying_price_from_options(
        self,
        underlying_ticker: str,
        start_time: datetime,
        end_time: datetime,
    ) -> pd.DataFrame:
        """
        Estimate underlying price from ATM options using bid/ask data.

        This finds the strike where call and put prices are closest (ATM),
        which gives us a good estimate of the underlying price.

        Args:
            underlying_ticker: Underlying ticker (e.g., 'SPX')
            start_time: Start time
            end_time: End time

        Returns:
            DataFrame with OHLCV structure using estimated underlying prices
            Index: DatetimeIndex
            Columns: Open, High, Low, Close, Volume
        """
        query = """
        WITH nearest_expiry AS (
            SELECT timestamp, MIN(expiration_date) as exp_date
            FROM options_bars
            WHERE underlying_ticker = %s
                AND timestamp >= %s
                AND timestamp <= %s
            GROUP BY timestamp
        ),
        atm_strikes AS (
            SELECT DISTINCT
                o.timestamp,
                o.strike_price,
                AVG((o.bid + o.ask) / 2.0) as mark_price
            FROM options_bars o
            INNER JOIN nearest_expiry ne
                ON o.timestamp = ne.timestamp
                AND o.expiration_date = ne.exp_date
            WHERE o.underlying_ticker = %s
                AND o.bid IS NOT NULL
                AND o.ask IS NOT NULL
                AND o.bid > 0
                AND o.ask > 0
            GROUP BY o.timestamp, o.strike_price
            HAVING COUNT(*) >= 2
        )
        SELECT
            timestamp,
            strike_price as price
        FROM atm_strikes
        WHERE mark_price > 0
        ORDER BY timestamp, mark_price DESC
        """

        df = pd.read_sql_query(
            query,
            self.engine,
            params=(underlying_ticker, start_time, end_time, underlying_ticker),
            parse_dates=['timestamp']
        )

        if df.empty:
            return pd.DataFrame()

        # Group by timestamp and take median strike as best ATM estimate
        result = df.groupby('timestamp').agg({
            'price': 'median'
        }).reset_index()

        # Create OHLCV structure
        result['Open'] = result['price']
        result['High'] = result['price']
        result['Low'] = result['price']
        result['Close'] = result['price']
        result['Volume'] = 0

        result = result[['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']]
        result.set_index('timestamp', inplace=True)

        return result

    def get_available_expirations(
        self, underlying_ticker: str, as_of: Optional[datetime] = None
    ) -> List[datetime]:
        """
        Get list of available expiration dates for an underlying ticker.

        Args:
            underlying_ticker: Underlying ticker
            as_of: Optional date to query expirations as of (defaults to now)

        Returns:
            List of expiration dates
        """
        if not as_of:
            as_of = datetime.now()

        query = """
        SELECT DISTINCT expiration_date
        FROM options_bars
        WHERE underlying_ticker = %s
            AND expiration_date >= %s
        ORDER BY expiration_date
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (underlying_ticker, as_of))
                rows = cur.fetchall()

        return [row[0] for row in rows]

    def get_data_range(self, option_ticker: str) -> Optional[Tuple[datetime, datetime]]:
        """
        Get the time range of available data for an option ticker.

        Args:
            option_ticker: Option contract ticker

        Returns:
            Tuple of (min_timestamp, max_timestamp) or None if no data
        """
        query = """
        SELECT MIN(timestamp), MAX(timestamp)
        FROM options_bars
        WHERE option_ticker = %s
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (option_ticker,))
                row = cur.fetchone()

        if row and row[0] and row[1]:
            return (row[0], row[1])
        return None

    def delete_option_data(
        self,
        option_ticker: Optional[str] = None,
        underlying_ticker: Optional[str] = None,
        before_date: Optional[datetime] = None,
    ) -> int:
        """
        Delete option data based on filters.

        Args:
            option_ticker: Specific option ticker to delete
            underlying_ticker: Delete all data for an underlying
            before_date: Delete data before this date

        Returns:
            Number of rows deleted
        """
        query = "DELETE FROM options_bars WHERE 1=1"
        params = []

        if option_ticker:
            query += " AND option_ticker = %s"
            params.append(option_ticker)

        if underlying_ticker:
            query += " AND underlying_ticker = %s"
            params.append(underlying_ticker)

        if before_date:
            query += " AND timestamp < %s"
            params.append(before_date)

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows_deleted = cur.rowcount
            conn.commit()

        return rows_deleted

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics (size, row counts, compression info).

        Returns:
            Dictionary with database statistics
        """
        stats = {}

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Total row count
                cur.execute("SELECT COUNT(*) as count FROM options_bars")
                stats["total_rows"] = cur.fetchone()["count"]

                # Database size
                cur.execute(
                    "SELECT pg_size_pretty(pg_database_size(%s)) as size", (self.database,)
                )
                stats["database_size"] = cur.fetchone()["size"]

                # Table size
                cur.execute("SELECT pg_size_pretty(pg_total_relation_size('options_bars')) as size")
                stats["table_size"] = cur.fetchone()["size"]

                # Compression stats
                cur.execute("""
                    SELECT
                        COUNT(*) as compressed_chunks
                    FROM timescaledb_information.chunks
                    WHERE hypertable_name = 'options_bars'
                        AND is_compressed = TRUE
                """)
                stats["compressed_chunks"] = cur.fetchone()["compressed_chunks"]

                # Time range
                cur.execute("SELECT MIN(timestamp) as min_time, MAX(timestamp) as max_time FROM options_bars")
                row = cur.fetchone()
                stats["min_timestamp"] = row["min_time"]
                stats["max_timestamp"] = row["max_time"]

        return stats

    def close(self) -> None:
        """Close all connections in the pool and dispose of SQLAlchemy engine."""
        if self.pool:
            self.pool.closeall()
        if self._engine is not None:
            self._engine.dispose()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
