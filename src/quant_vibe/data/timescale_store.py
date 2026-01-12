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

from typing import Optional, List, Dict, Any, Tuple, TYPE_CHECKING
from datetime import datetime, timedelta
from contextlib import contextmanager
import pandas as pd
from psycopg2.extras import execute_batch, RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv
from quant_vibe.logging.unified_logging import get_logger
from quant_vibe.utils.timestamp_utils import now_utc

if TYPE_CHECKING:
    from quant_vibe.models import OptionsBar, UnderlyingBar

load_dotenv()

logger = get_logger(__name__)

class TimescaleStore:
    """
    TimescaleDB storage client for options timeseries data.

    This class handles all database operations including:
    - Inserting options bars (1-minute resolution)
    - Querying data by time range, ticker, strike, etc.
    - Accessing continuous aggregates for higher timeframes
    - Bulk operations for efficient data loading
    """

    @staticmethod
    def normalize_contract_symbol(symbol: str) -> str:
        """
        Normalize option contract symbols to a canonical format.

        Handles multiple formats:
        - Massive API: "O:SPXW251223P06865000" → "SPXW251223P06865000"
        - Schwab API: "SPXW  260122C07025000" → "SPXW260122C07025000"

        Canonical format: {UNDERLYING}{YYMMDD}{C|P}{STRIKE8DIGITS}
        Example: "SPXW251223P06865000"

        Args:
            symbol: Raw contract symbol from any data source

        Returns:
            Normalized contract symbol
        """
        if not symbol:
            return symbol

        # Remove "O:" prefix (Massive format)
        if symbol.startswith("O:"):
            symbol = symbol[2:]

        # Remove extra spaces (Schwab format)
        symbol = symbol.replace(" ", "")

        return symbol

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
            # Add connection options for query timeout (10 minutes for large queries)
            self._engine = create_engine(
                connection_string,
                poolclass=NullPool,
                connect_args={
                    "options": "-c statement_timeout=600000"  # 10 minutes in milliseconds
                }
            )
        return self._engine

    @contextmanager
    def get_connection(self):
        """Get a connection from the pool."""
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    def insert_option_bar(self, bar: "OptionsBar") -> None:
        """
        Insert a single options bar into the database using Pydantic model.

        Args:
            bar: OptionsBar Pydantic model instance

        Example:
            >>> from quant_vibe.models import OptionsBar
            >>> from quant_vibe.utils import now_utc
            >>> from datetime import date
            >>> from decimal import Decimal
            >>> bar = OptionsBar(
            ...     timestamp=now_utc(),
            ...     contract_symbol="SPXW260123P06860000",
            ...     underlying_ticker="SPX",
            ...     strike_price=Decimal("6860.0"),
            ...     contract_type="put",
            ...     expiration_date=date(2026, 1, 23),
            ...     open=Decimal("10.2"),
            ...     high=Decimal("10.8"),
            ...     low=Decimal("10.0"),
            ...     close=Decimal("10.5"),
            ...     volume=100,
            ...     bid=Decimal("10.4"),
            ...     ask=Decimal("10.6"),
            ...     mark=Decimal("10.5"),
            ... )
            >>> store.insert_option_bar(bar)
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
        """

        # Normalize contract symbol to canonical format
        option_ticker = self.normalize_contract_symbol(bar.contract_symbol)

        # Coerce Greek values to fit database constraints
        implied_volatility = self._coerce_greek_value(
            float(bar.implied_volatility) if bar.implied_volatility is not None else None,
            "implied_volatility",
            option_ticker
        )
        delta = self._coerce_greek_value(
            float(bar.delta) if bar.delta is not None else None,
            "delta",
            option_ticker
        )
        gamma = self._coerce_greek_value(
            float(bar.gamma) if bar.gamma is not None else None,
            "gamma",
            option_ticker
        )
        theta = self._coerce_greek_value(
            float(bar.theta) if bar.theta is not None else None,
            "theta",
            option_ticker
        )
        vega = self._coerce_greek_value(
            float(bar.vega) if bar.vega is not None else None,
            "vega",
            option_ticker
        )
        rho = self._coerce_greek_value(
            float(bar.rho) if bar.rho is not None else None,
            "rho",
            option_ticker
        )

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        bar.timestamp,
                        option_ticker,
                        bar.underlying_ticker,
                        float(bar.open),
                        float(bar.high),
                        float(bar.low),
                        float(bar.close),
                        bar.volume,
                        float(bar.vwap) if bar.vwap is not None else None,
                        bar.transactions,
                        float(bar.bid) if bar.bid is not None else None,
                        float(bar.ask) if bar.ask is not None else None,
                        bar.bid_size,
                        bar.ask_size,
                        float(bar.strike_price),
                        bar.contract_type,
                        bar.expiration_date,
                        implied_volatility,
                        delta,
                        gamma,
                        theta,
                        vega,
                        rho,
                        bar.data_source,
                    ),
                )
            conn.commit()

    def _coerce_greek_value(self, value: Optional[float], field_name: str, option_ticker: str) -> Optional[float]:
        """
        Coerce Greek values to fit database constraints (numeric(8,6): -99.999999 to 99.999999).

        Args:
            value: The value to coerce
            field_name: Name of the field (for logging)
            option_ticker: Option ticker (for logging)

        Returns:
            Coerced value or None
        """
        if value is None:
            return None

        # Database constraint: numeric(8,6) allows values from -99.999999 to 99.999999
        # Total 8 digits, 6 after decimal point = max 2 digits before decimal
        MIN_VALUE = -99.999999
        MAX_VALUE = 99.999999

        if value < MIN_VALUE or value > MAX_VALUE:
            logger.warning(
                f"Greek value overflow - Field: {field_name}, "
                f"Value: {value}, Ticker: {option_ticker}, "
                f"Coercing to range [{MIN_VALUE}, {MAX_VALUE}]"
            )
            # Coerce to valid range
            return max(MIN_VALUE, min(MAX_VALUE, value))

        return value

    def bulk_insert_option_bars(self, bars: List["OptionsBar"], batch_size: int = 1000) -> int:
        """
        Bulk insert options bars for efficient data loading.

        Args:
            bars: List of OptionsBar Pydantic model instances
            batch_size: Number of rows to insert per batch

        Returns:
            Number of rows inserted

        Example:
            >>> from quant_vibe.models import OptionsBar
            >>> from quant_vibe.utils import now_utc
            >>> from datetime import date
            >>> from decimal import Decimal
            >>> bars = [
            ...     OptionsBar(
            ...         timestamp=now_utc(),
            ...         contract_symbol='SPXW260123P06860000',
            ...         underlying_ticker='SPX',
            ...         strike_price=Decimal('6860.0'),
            ...         contract_type='put',
            ...         expiration_date=date(2026, 1, 23),
            ...         open=Decimal('100.5'),
            ...         high=Decimal('101.0'),
            ...         low=Decimal('100.0'),
            ...         close=Decimal('100.75'),
            ...         volume=1000,
            ...         bid=Decimal('100.4'),
            ...         ask=Decimal('100.6'),
            ...         mark=Decimal('100.5'),
            ...     ),
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
        """

        rows = []
        for bar in bars:
            # Normalize contract symbol to canonical format
            option_ticker = self.normalize_contract_symbol(bar.contract_symbol)

            # Coerce Greek values to fit database constraints
            implied_volatility = self._coerce_greek_value(
                float(bar.implied_volatility) if bar.implied_volatility is not None else None,
                "implied_volatility",
                option_ticker
            )
            delta = self._coerce_greek_value(
                float(bar.delta) if bar.delta is not None else None,
                "delta",
                option_ticker
            )
            gamma = self._coerce_greek_value(
                float(bar.gamma) if bar.gamma is not None else None,
                "gamma",
                option_ticker
            )
            theta = self._coerce_greek_value(
                float(bar.theta) if bar.theta is not None else None,
                "theta",
                option_ticker
            )
            vega = self._coerce_greek_value(
                float(bar.vega) if bar.vega is not None else None,
                "vega",
                option_ticker
            )
            rho = self._coerce_greek_value(
                float(bar.rho) if bar.rho is not None else None,
                "rho",
                option_ticker
            )

            rows.append(
                (
                    bar.timestamp,
                    option_ticker,
                    bar.underlying_ticker,
                    float(bar.open),
                    float(bar.high),
                    float(bar.low),
                    float(bar.close),
                    bar.volume,
                    float(bar.vwap) if bar.vwap is not None else None,
                    bar.transactions,
                    float(bar.bid) if bar.bid is not None else None,
                    float(bar.ask) if bar.ask is not None else None,
                    bar.bid_size,
                    bar.ask_size,
                    float(bar.strike_price),
                    bar.contract_type,
                    bar.expiration_date,
                    implied_volatility,
                    delta,
                    gamma,
                    theta,
                    vega,
                    rho,
                    bar.data_source,
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
            end_time = now_utc()
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
        timeframe: str = "1min",
    ) -> List["OptionsBar"]:
        """
        Get options data optimized for backtesting.

        Args:
            underlying_ticker: Underlying ticker (e.g., 'SPXW')
            start_time: Start time for backtest
            end_time: End time for backtest
            min_dte: Minimum days to expiration filter
            max_dte: Maximum days to expiration filter
            strike_range_pct: Optional percentage range around ATM (e.g., 0.1 for ±10%)
            timeframe: Time aggregation - "1min" (default), "5min", "15min", "1hour", "daily"
                      Using 5min or 15min dramatically reduces memory usage for optimizations

        Returns:
            List of OptionsBar Pydantic model instances with all options data in the time range.
            Each bar contains: timestamp, contract_symbol, strike_price, contract_type,
            expiration_date, OHLCV data, bid/ask quotes, Greeks, etc.

            Note: contract_type values are lowercase enum: 'call', 'put'
        """
        # Map timeframe to table/view name
        table_map = {
            "1min": "options_bars",
            "5min": "options_bars_5min",
            "15min": "options_bars_15min",
            "1hour": "options_bars_1hour",
            "daily": "options_bars_daily",
        }

        table_name = table_map.get(timeframe, "options_bars")

        # Log which timeframe and table is being used
        logger.info(f"Loading options data with timeframe='{timeframe}' from table '{table_name}'")

        # For aggregated views, use 'bucket' column; for base table use 'timestamp'
        time_column = "bucket" if timeframe != "1min" else "timestamp"

        query = f"""
        SELECT
            {time_column} as timestamp,
            option_ticker as contract_symbol,
            strike_price,
            contract_type,
            expiration_date,
            open, high, low, close, volume,
            bid, ask,
            (bid + ask) / 2.0 as mark,
            bid_size, ask_size,
            delta, gamma, theta, vega, rho,
            implied_volatility,
            COALESCE(expired, false) as expired
        FROM {table_name}
        WHERE underlying_ticker = %s
            AND {time_column} >= %s
            AND {time_column} <= %s
            AND COALESCE(expired, false) = false
        """

        params = [underlying_ticker, start_time, end_time]

        # Add DTE filters if specified
        if min_dte is not None:
            query += f" AND (expiration_date - {time_column}::date) >= %s"
            params.append(min_dte)

        if max_dte is not None:
            query += f" AND (expiration_date - {time_column}::date) <= %s"
            params.append(max_dte)

        query += " ORDER BY timestamp, expiration_date, strike_price, contract_type"

        logger.debug("Executing options backtest query with params: %s", params)
        logger.debug("Query: %s", query)

        # Estimate query size and warn if it might be slow
        import time
        from sqlalchemy.exc import OperationalError

        logger.info(f"Fetching data for {underlying_ticker} from {start_time.date()} to {end_time.date()} (DTE: {min_dte}-{max_dte})...")
        query_start = time.time()

        try:
            df = pd.read_sql_query(query, self.engine, params=tuple(params), parse_dates=['timestamp', 'expiration_date'])
        except OperationalError as e:
            if "statement timeout" in str(e).lower():
                elapsed = time.time() - query_start
                raise TimeoutError(
                    f"Query timeout after {elapsed:.1f}s loading data from {start_time.date()} to {end_time.date()}.\n"
                    f"Try one of these solutions:\n"
                    f"  1. Use a smaller date range (currently {(end_time - start_time).days} days)\n"
                    f"  2. Use aggregated timeframe: timeframe='5min' (reduces data by ~95%)\n"
                    f"  3. Increase statement_timeout in TimescaleStore.engine property"
                ) from e
            raise

        query_elapsed = time.time() - query_start

        # Log how much data was loaded
        if not df.empty:
            estimated_mb = len(df) * 200 / 1024 / 1024  # Rough estimate: 200 bytes per row
            logger.info(f"Loaded {len(df):,} rows (~{estimated_mb:.1f} MB) from {table_name} in {query_elapsed:.1f}s")

            # Warn if dataset is very large and suggest using aggregated timeframe
            if len(df) > 500000 and timeframe == "1min":
                logger.warning(
                    f"Large dataset detected ({len(df):,} rows). "
                    f"Consider using timeframe='5min' to reduce memory usage by ~95% "
                    f"(reduces {len(df):,} rows to ~{len(df)//5:,} rows)"
                )
        else:
            logger.warning(f"No data found in {table_name}")

        # Convert DataFrame to list of Pydantic models using vectorized operations
        from quant_vibe.models import OptionsBar
        from decimal import Decimal

        if df.empty:
            return []

        # Normalize contract symbols in bulk (vectorized)
        df['contract_symbol'] = df['contract_symbol'].apply(self.normalize_contract_symbol)

        # Convert expiration_date to date objects (vectorized)
        # pd.read_sql_query with parse_dates returns Timestamp objects, convert to date
        # This matches the OptionsBar Pydantic model which expects date (not datetime)
        import datetime as dt
        df['expiration_date'] = df['expiration_date'].apply(
            lambda x: x.date() if isinstance(x, (pd.Timestamp, dt.datetime)) else x
        )

        # Pre-fill data_source if not present
        if 'data_source' not in df.columns:
            df['data_source'] = 'combined'

        # Use model_validate to create Pydantic models from dict records (much faster than iterrows)
        # Convert to dict records and batch process
        records = df.to_dict('records')

        # Batch convert to Pydantic models
        bars = []
        for record in records:
            # Add underlying_ticker since it's not in the query result
            record['underlying_ticker'] = underlying_ticker

            # Convert numeric fields to Decimal where needed
            # Pydantic will handle type coercion, but we need to ensure Decimal for precision fields
            for field in ['strike_price', 'open', 'high', 'low', 'close', 'bid', 'ask', 'mark', 'vwap',
                         'implied_volatility', 'delta', 'gamma', 'theta', 'vega', 'rho']:
                if field in record and pd.notna(record[field]):
                    record[field] = Decimal(str(record[field]))
                elif field in record:
                    record[field] = None

            # Convert integer fields
            for field in ['volume', 'bid_size', 'ask_size', 'transactions']:
                if field in record and pd.notna(record[field]):
                    record[field] = int(record[field])
                elif field in record:
                    record[field] = None if field != 'volume' else 0

            try:
                bar = OptionsBar.model_validate(record)
                bars.append(bar)
            except Exception as e:
                # Skip invalid records (e.g., NULL strike_price from bad data collection)
                # This is expected for ~5% of records with incomplete data
                logger.debug(f"Skipped invalid OptionsBar record: {e}")
                continue

        return bars

    def get_underlying_price_from_options(
        self,
        underlying_ticker: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List["UnderlyingBar"]:
        """
        Estimate underlying price from ATM options using bid/ask data.

        This finds the strike where call and put prices are closest (ATM),
        which gives us a good estimate of the underlying price.

        Args:
            underlying_ticker: Underlying ticker (e.g., 'SPX')
            start_time: Start time
            end_time: End time

        Returns:
            List of UnderlyingBar Pydantic model instances with estimated underlying prices.
            Each bar has OHLC set to the estimated price (since we derive from a single point).
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
            return []

        # Group by timestamp and take median strike as best ATM estimate
        result = df.groupby('timestamp').agg({
            'price': 'median'
        }).reset_index()

        # Convert to UnderlyingBar Pydantic models using vectorized operations
        from quant_vibe.models import UnderlyingBar
        from decimal import Decimal

        # Convert to dict records for batch processing (much faster than iterrows)
        records = result.to_dict('records')

        # Batch convert to Pydantic models
        bars = []
        for record in records:
            price = Decimal(str(record['price']))
            record['ticker'] = underlying_ticker
            record['open'] = price
            record['high'] = price
            record['low'] = price
            record['close'] = price
            record['volume'] = 0
            record['data_source'] = 'derived_from_options'
            # Remove 'price' as it's not a field in UnderlyingBar
            del record['price']

            try:
                bar = UnderlyingBar.model_validate(record)
                bars.append(bar)
            except Exception as e:
                logger.warning(f"Failed to create UnderlyingBar from record: {e}")
                continue

        return bars

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
            as_of = now_utc()

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

    # ========================================================================
    # UNDERLYING PRICE DATA METHODS
    # ========================================================================

    def insert_underlying_bar(self, bar: "UnderlyingBar") -> None:
        """
        Insert a single underlying price bar using Pydantic model.

        Args:
            bar: UnderlyingBar Pydantic model instance

        Example:
            >>> from quant_vibe.models import UnderlyingBar
            >>> from quant_vibe.utils import now_utc
            >>> from decimal import Decimal
            >>> bar = UnderlyingBar(
            ...     timestamp=now_utc(),
            ...     ticker="SPX",
            ...     open=Decimal("6100.0"),
            ...     high=Decimal("6120.0"),
            ...     low=Decimal("6090.0"),
            ...     close=Decimal("6110.0"),
            ...     volume=1000000,
            ... )
            >>> store.insert_underlying_bar(bar)
        """
        query = """
        INSERT INTO underlying_bars (
            timestamp, ticker,
            open, high, low, close, volume, vwap, transactions,
            data_source
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (timestamp, ticker) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            vwap = EXCLUDED.vwap,
            transactions = EXCLUDED.transactions,
            data_source = EXCLUDED.data_source
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (
                    bar.timestamp,
                    bar.ticker,
                    float(bar.open),
                    float(bar.high),
                    float(bar.low),
                    float(bar.close),
                    bar.volume,
                    float(bar.vwap) if bar.vwap is not None else None,
                    bar.transactions,
                    bar.data_source,
                ))
            conn.commit()

    def bulk_insert_underlying_bars(self, bars: List["UnderlyingBar"], batch_size: int = 1000) -> int:
        """
        Bulk insert underlying price bars using Pydantic models.

        Args:
            bars: List of UnderlyingBar Pydantic model instances
            batch_size: Number of bars per batch (default: 1000)

        Returns:
            Number of bars inserted

        Example:
            >>> from quant_vibe.models import UnderlyingBar
            >>> from quant_vibe.utils import now_utc
            >>> from decimal import Decimal
            >>> bars = [
            ...     UnderlyingBar(
            ...         timestamp=now_utc(),
            ...         ticker="SPX",
            ...         open=Decimal("6850.0"),
            ...         high=Decimal("6855.0"),
            ...         low=Decimal("6848.0"),
            ...         close=Decimal("6852.0"),
            ...         volume=0,
            ...     ),
            ... ]
            >>> store.bulk_insert_underlying_bars(bars)
        """
        query = """
        INSERT INTO underlying_bars (
            timestamp, ticker,
            open, high, low, close, volume, vwap, transactions,
            data_source
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (timestamp, ticker) DO UPDATE SET
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            vwap = EXCLUDED.vwap,
            transactions = EXCLUDED.transactions,
            data_source = EXCLUDED.data_source
        """

        total_inserted = 0

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for i in range(0, len(bars), batch_size):
                    batch = bars[i:i + batch_size]

                    values = []
                    for bar in batch:
                        values.append((
                            bar.timestamp,
                            bar.ticker,
                            float(bar.open),
                            float(bar.high),
                            float(bar.low),
                            float(bar.close),
                            bar.volume,
                            float(bar.vwap) if bar.vwap is not None else None,
                            bar.transactions,
                            bar.data_source,
                        ))

                    cur.executemany(query, values)
                    total_inserted += len(batch)

            conn.commit()

        return total_inserted

    def get_underlying_bars(
        self,
        ticker: str,
        start_time: datetime,
        end_time: datetime
    ) -> List["UnderlyingBar"]:
        """
        Get underlying price bars for a ticker and time range.

        Args:
            ticker: Ticker symbol (e.g., 'SPX', 'SPY')
            start_time: Start timestamp
            end_time: End timestamp

        Returns:
            List of UnderlyingBar Pydantic model instances

        Example:
            >>> from quant_vibe.data import TimescaleStore
            >>> from quant_vibe.utils import now_utc
            >>> from datetime import timedelta
            >>> store = TimescaleStore()
            >>> bars = store.get_underlying_bars(
            ...     'SPX',
            ...     now_utc() - timedelta(hours=1),
            ...     now_utc()
            ... )
        """
        query = """
        SELECT
            timestamp,
            open,
            high,
            low,
            close,
            volume,
            vwap,
            transactions
        FROM underlying_bars
        WHERE ticker = %s
            AND timestamp >= %s
            AND timestamp <= %s
        ORDER BY timestamp ASC
        """

        df = pd.read_sql_query(
            query,
            self.engine,
            params=(ticker, start_time, end_time),
            parse_dates=['timestamp']
        )

        if df.empty:
            return []

        # Convert to UnderlyingBar Pydantic models using vectorized operations
        from quant_vibe.models import UnderlyingBar
        from decimal import Decimal

        # Pre-fill data_source if not present
        if 'data_source' not in df.columns:
            df['data_source'] = 'schwab'

        # Convert to dict records for batch processing (much faster than iterrows)
        records = df.to_dict('records')

        # Batch convert to Pydantic models
        bars = []
        for record in records:
            # Add ticker since it's not in the query result
            record['ticker'] = ticker

            # Convert numeric fields to Decimal
            for field in ['open', 'high', 'low', 'close', 'vwap']:
                if field in record and pd.notna(record[field]):
                    record[field] = Decimal(str(record[field]))
                elif field in record:
                    record[field] = None

            # Convert integer fields
            for field in ['volume', 'transactions']:
                if field in record and pd.notna(record[field]):
                    record[field] = int(record[field])
                elif field in record:
                    record[field] = None if field != 'volume' else 0

            try:
                bar = UnderlyingBar.model_validate(record)
                bars.append(bar)
            except Exception as e:
                logger.warning(f"Failed to create UnderlyingBar from record: {e}")
                continue

        return bars

    # ========================================================================
    # BACKTEST RESULTS PERSISTENCE
    # ========================================================================

    def save_backtest_run(
        self,
        backtest_id: str,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        parameters: Optional[Dict[str, Any]] = None,
        max_positions: int = 1,
        status: str = "pending",
        created_by: Optional[str] = None,
    ) -> None:
        """
        Save backtest run metadata to database.

        Args:
            backtest_id: Unique identifier for this backtest run
            strategy_name: Name of the strategy
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Starting capital
            parameters: Strategy parameters (stored as JSON)
            max_positions: Maximum concurrent positions
            status: Execution status ('pending', 'running', 'completed', 'failed')
            created_by: Username of who created this backtest

        Example:
            >>> store = TimescaleStore()
            >>> store.save_backtest_run(
            ...     backtest_id='bullish_vertical_put_20251230_143022',
            ...     strategy_name='bullish_vertical_put',
            ...     start_date=datetime(2025, 12, 1),
            ...     end_date=datetime(2025, 12, 15),
            ...     initial_capital=100000.0,
            ...     parameters={'spread_width': 20, 'min_dte': 0, 'max_dte': 0}
            ... )
        """
        import json

        query = """
        INSERT INTO backtest_runs (
            backtest_id, strategy_name, start_date, end_date, initial_capital,
            parameters, max_positions, status, created_by
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (backtest_id) DO UPDATE SET
            status = EXCLUDED.status,
            parameters = EXCLUDED.parameters
        """

        params = (
            backtest_id,
            strategy_name,
            start_date,
            end_date,
            initial_capital,
            json.dumps(parameters) if parameters else None,
            max_positions,
            status,
            created_by,
        )

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
            conn.commit()

    def update_backtest_status(
        self,
        backtest_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update backtest execution status.

        Args:
            backtest_id: Backtest identifier
            status: New status ('running', 'completed', 'failed')
            error_message: Error message if status is 'failed'
        """
        if status == "running":
            query = """
            UPDATE backtest_runs
            SET status = %s, started_at = NOW()
            WHERE backtest_id = %s
            """
            params = (status, backtest_id)
        elif status in ("completed", "failed"):
            query = """
            UPDATE backtest_runs
            SET status = %s, completed_at = NOW(), error_message = %s
            WHERE backtest_id = %s
            """
            params = (status, error_message, backtest_id)
        else:
            query = """
            UPDATE backtest_runs
            SET status = %s
            WHERE backtest_id = %s
            """
            params = (status, backtest_id)

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
            conn.commit()

    def update_backtest_metrics(
        self,
        backtest_id: str,
        metrics: Dict[str, Any],
    ) -> None:
        """
        Update backtest summary metrics.

        Args:
            backtest_id: Backtest identifier
            metrics: Dictionary of performance metrics

        Example:
            >>> metrics = {
            ...     'final_capital': 105000.0,
            ...     'total_return': 5000.0,
            ...     'total_return_pct': 5.0,
            ...     'num_trades': 10,
            ...     'win_rate': 70.0,
            ...     'sharpe_ratio': 1.5,
            ... }
            >>> store.update_backtest_metrics(backtest_id, metrics)
        """
        query = """
        UPDATE backtest_runs
        SET
            final_capital = %(final_capital)s,
            total_return = %(total_return)s,
            total_return_pct = %(total_return_pct)s,
            num_trades = %(num_trades)s,
            num_winning_trades = %(num_winning_trades)s,
            num_losing_trades = %(num_losing_trades)s,
            win_rate = %(win_rate)s,
            avg_win = %(avg_win)s,
            avg_loss = %(avg_loss)s,
            profit_factor = %(profit_factor)s,
            max_drawdown = %(max_drawdown)s,
            sharpe_ratio = %(sharpe_ratio)s
        WHERE backtest_id = %(backtest_id)s
        """

        params = {**metrics, "backtest_id": backtest_id}

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
            conn.commit()

    def save_backtest_trades(
        self,
        backtest_id: str,
        trades_df: pd.DataFrame,
    ) -> None:
        """
        Save trade records to database.

        Args:
            backtest_id: Backtest identifier
            trades_df: DataFrame with trade records (matches Trade Pydantic model)

        Expected columns (matching Trade model in src/quant_vibe/models/market_data.py):
            - position_id, strategy_name, spread_type
            - entry_time, exit_time, duration_minutes (optional)
            - entry_premium, exit_premium, pnl, pnl_pct
            - entry_trigger, exit_reason
            - entry_underlying_price, exit_underlying_price
            - max_risk, max_profit, peak_value
            - legs (as list of dicts or JSON string)
        """
        import json

        if trades_df.empty:
            return

        query = """
        INSERT INTO backtest_trades (
            backtest_id, position_id, strategy_name, spread_type, entry_time, exit_time,
            duration_minutes, entry_premium, exit_premium, pnl, pnl_pct,
            entry_trigger, exit_reason, entry_underlying_price, exit_underlying_price,
            max_risk, max_profit, peak_value, legs
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """

        def convert_to_serializable(obj):
            """
            Convert pandas/numpy/datetime types to JSON-serializable types.

            This follows the Pydantic pattern for handling complex types at data boundaries.
            See: docs/SIMPLIFICATION_PLAN.md for the long-term Pydantic migration plan.
            """
            from datetime import datetime, date
            from decimal import Decimal

            if obj is None:
                return None

            # Handle datetime types (timestamp normalization)
            if isinstance(obj, pd.Timestamp):
                return obj.isoformat()
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, date):
                return obj.isoformat()

            # Handle numeric types
            if isinstance(obj, Decimal):
                return float(obj)
            if hasattr(obj, 'item'):  # NumPy scalar
                return obj.item()

            # Recursively handle collections
            if isinstance(obj, dict):
                return {k: convert_to_serializable(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [convert_to_serializable(item) for item in obj]

            return obj

        # Prepare records for batch insert
        records = []
        for _, row in trades_df.iterrows():
            # Convert legs to JSON if it's a list of dicts
            legs_json = row.get('legs', [])
            if isinstance(legs_json, str):
                legs_json = json.loads(legs_json)

            # Convert all pandas/numpy types to serializable types
            legs_json = convert_to_serializable(legs_json)

            records.append((
                backtest_id,
                row.get('position_id'),
                row.get('strategy_name'),
                row.get('spread_type'),
                row.get('entry_time'),
                row.get('exit_time'),
                row.get('duration_minutes'),
                row.get('entry_premium'),
                row.get('exit_premium'),
                row.get('pnl'),
                row.get('pnl_pct'),
                row.get('entry_trigger'),
                row.get('exit_reason'),
                row.get('entry_underlying_price'),
                row.get('exit_underlying_price'),
                row.get('max_risk'),
                row.get('max_profit'),
                row.get('peak_value'),
                json.dumps(legs_json),
            ))

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                execute_batch(cursor, query, records, page_size=100)
            conn.commit()

    def save_backtest_equity_curve(
        self,
        backtest_id: str,
        equity_df: pd.DataFrame,
    ) -> None:
        """
        Save equity curve data to database.

        Args:
            backtest_id: Backtest identifier
            equity_df: DataFrame with equity curve snapshots

        Expected columns or index:
            - timestamp (as index or column), cash, portfolio_value, active_position
            - returns, cummax, drawdown (optional)
        """
        if equity_df.empty:
            return

        # Reset index to get timestamp as a column if it's the index
        df = equity_df.copy()
        if df.index.name == 'timestamp' or 'timestamp' not in df.columns:
            df = df.reset_index()

        query = """
        INSERT INTO backtest_equity_curve (
            backtest_id, timestamp, cash, portfolio_value, active_position,
            returns, cummax, drawdown
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        """

        # Prepare records for batch insert
        records = []
        for _, row in df.iterrows():
            records.append((
                backtest_id,
                row.get('timestamp'),
                row.get('cash'),
                row.get('portfolio_value'),
                row.get('active_position', False),
                row.get('returns'),
                row.get('cummax'),
                row.get('drawdown'),
            ))

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                execute_batch(cursor, query, records, page_size=1000)
            conn.commit()

    def get_backtest_run(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backtest run metadata.

        Args:
            backtest_id: Backtest identifier

        Returns:
            Dictionary with backtest metadata or None if not found
        """
        query = """
        SELECT * FROM backtest_runs
        WHERE backtest_id = %s
        """

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, (backtest_id,))
                result = cursor.fetchone()
                return dict(result) if result else None

    def get_backtest_trades(self, backtest_id: str) -> pd.DataFrame:
        """
        Get trade records for a backtest.

        Args:
            backtest_id: Backtest identifier

        Returns:
            DataFrame with trade records (matching Trade Pydantic model)
        """
        query = """
        SELECT
            trade_id, position_id, strategy_name, spread_type, entry_time, exit_time,
            duration_minutes, entry_premium, exit_premium, pnl, pnl_pct,
            entry_trigger, exit_reason, entry_underlying_price, exit_underlying_price,
            max_risk, max_profit, peak_value, legs
        FROM backtest_trades
        WHERE backtest_id = %s
        ORDER BY entry_time ASC
        """

        df = pd.read_sql_query(
            query,
            self.engine,
            params=(backtest_id,),
            parse_dates=['entry_time', 'exit_time']
        )

        return df

    def get_backtest_equity_curve(self, backtest_id: str) -> pd.DataFrame:
        """
        Get equity curve for a backtest.

        Args:
            backtest_id: Backtest identifier

        Returns:
            DataFrame with equity curve data
        """
        query = """
        SELECT
            timestamp, cash, portfolio_value, active_position,
            returns, cummax, drawdown
        FROM backtest_equity_curve
        WHERE backtest_id = %s
        ORDER BY timestamp ASC
        """

        df = pd.read_sql_query(
            query,
            self.engine,
            params=(backtest_id,),
            parse_dates=['timestamp']
        )

        return df

    def get_backtest_history(
        self,
        strategy_name: Optional[str] = None,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get backtest execution history.

        Args:
            strategy_name: Filter by strategy name (optional)
            limit: Maximum number of results
            status: Filter by status (optional)

        Returns:
            List of backtest metadata dictionaries
        """
        query = """
        SELECT * FROM backtest_runs
        WHERE 1=1
        """
        params = []

        if strategy_name:
            query += " AND strategy_name = %s"
            params.append(strategy_name)

        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                return [dict(row) for row in results]

    def delete_backtest(self, backtest_id: str) -> bool:
        """
        Delete a backtest and all associated data (trades, equity curve).

        Args:
            backtest_id: Unique backtest identifier

        Returns:
            True if deletion was successful, False if backtest not found
        """
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Delete trades first (foreign key constraint)
                cursor.execute(
                    "DELETE FROM backtest_trades WHERE backtest_id = %s",
                    (backtest_id,)
                )

                # Delete equity curve
                cursor.execute(
                    "DELETE FROM backtest_equity_curve WHERE backtest_id = %s",
                    (backtest_id,)
                )

                # Delete backtest run
                cursor.execute(
                    "DELETE FROM backtest_runs WHERE backtest_id = %s",
                    (backtest_id,)
                )

                deleted_count = cursor.rowcount
                conn.commit()

                return deleted_count > 0

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

    # ==================== Backtest Analysis Methods ====================

    def save_backtest_analysis(
        self,
        backtest_id: str,
        total_trades: int,
        outlier_threshold_pct: float,
        num_big_winners: int,
        num_big_losers: int,
        findings: Dict[str, Any],
        summary_markdown: str,
        recommendations_markdown: str,
        analyzer_version: str = "1.0.0",
    ) -> int:
        """
        Save backtest analysis results to database.

        Args:
            backtest_id: Backtest identifier
            total_trades: Total number of trades analyzed
            outlier_threshold_pct: Standard deviation threshold used
            num_big_winners: Number of outlier winners found
            num_big_losers: Number of outlier losers found
            findings: JSONB structured findings
            summary_markdown: Markdown summary
            recommendations_markdown: Markdown recommendations
            analyzer_version: Version of analyzer

        Returns:
            analysis_id: Database ID of created analysis record

        Raises:
            psycopg2.Error: If database operation fails
        """
        import json

        query = """
            INSERT INTO backtest_analysis (
                backtest_id,
                total_trades,
                outlier_threshold_pct,
                num_big_winners,
                num_big_losers,
                findings,
                summary_markdown,
                recommendations_markdown,
                analyzer_version
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING analysis_id;
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    query,
                    (
                        backtest_id,
                        total_trades,
                        outlier_threshold_pct,
                        num_big_winners,
                        num_big_losers,
                        json.dumps(findings),
                        summary_markdown,
                        recommendations_markdown,
                        analyzer_version,
                    ),
                )
                analysis_id = cursor.fetchone()[0]
                conn.commit()
                logger.info(f"Saved analysis {analysis_id} for backtest {backtest_id}")
                return analysis_id
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to save backtest analysis: {e}")
                raise

    def get_backtest_analysis(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backtest analysis results from database.

        Args:
            backtest_id: Backtest identifier

        Returns:
            Dictionary with analysis data, or None if not found
        """
        query = """
            SELECT
                analysis_id,
                backtest_id,
                analyzed_at,
                total_trades,
                outlier_threshold_pct,
                num_big_winners,
                num_big_losers,
                findings,
                summary_markdown,
                recommendations_markdown,
                analyzer_version,
                created_at,
                updated_at
            FROM backtest_analysis
            WHERE backtest_id = %s
            ORDER BY analyzed_at DESC
            LIMIT 1;
        """

        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                cursor.execute(query, (backtest_id,))
                result = cursor.fetchone()
                if result:
                    # Convert to regular dict and handle datetime objects
                    analysis = dict(result)
                    # Convert datetime objects to ISO format strings
                    for key in ["analyzed_at", "created_at", "updated_at"]:
                        if key in analysis and analysis[key]:
                            analysis[key] = analysis[key].isoformat()
                    return analysis
                return None
            except Exception as e:
                logger.error(f"Failed to get backtest analysis: {e}")
                raise

    def delete_backtest_analysis(self, backtest_id: str) -> int:
        """
        Delete backtest analysis for a specific backtest.

        Note: This is also handled automatically by ON DELETE CASCADE
        when a backtest is deleted.

        Args:
            backtest_id: Backtest identifier

        Returns:
            Number of analysis records deleted
        """
        query = "DELETE FROM backtest_analysis WHERE backtest_id = %s;"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, (backtest_id,))
                deleted_count = cursor.rowcount
                conn.commit()
                logger.info(f"Deleted {deleted_count} analysis records for backtest {backtest_id}")
                return deleted_count
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to delete backtest analysis: {e}")
                raise

    def update_backtest_analysis(
        self,
        analysis_id: int,
        findings: Optional[Dict[str, Any]] = None,
        summary_markdown: Optional[str] = None,
        recommendations_markdown: Optional[str] = None,
    ) -> bool:
        """
        Update an existing backtest analysis.

        Args:
            analysis_id: Analysis record ID
            findings: Optional updated findings JSONB
            summary_markdown: Optional updated summary
            recommendations_markdown: Optional updated recommendations

        Returns:
            True if update successful, False if record not found
        """
        import json

        # Build dynamic UPDATE query based on provided fields
        updates = []
        params = []

        if findings is not None:
            updates.append("findings = %s")
            params.append(json.dumps(findings))

        if summary_markdown is not None:
            updates.append("summary_markdown = %s")
            params.append(summary_markdown)

        if recommendations_markdown is not None:
            updates.append("recommendations_markdown = %s")
            params.append(recommendations_markdown)

        if not updates:
            logger.warning("No fields to update in backtest analysis")
            return False

        # Add analysis_id to params
        params.append(analysis_id)

        query = f"""
            UPDATE backtest_analysis
            SET {', '.join(updates)}
            WHERE analysis_id = %s;
        """

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                updated = cursor.rowcount > 0
                conn.commit()
                if updated:
                    logger.info(f"Updated analysis {analysis_id}")
                else:
                    logger.warning(f"Analysis {analysis_id} not found for update")
                return updated
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to update backtest analysis: {e}")
                raise
