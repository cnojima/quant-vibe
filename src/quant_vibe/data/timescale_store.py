"""TimescaleDB storage for high-frequency options data.

Provides TimescaleDB integration for:
- 1-minute options bars (OHLCV)
- Quote data (bid/ask)
- Greeks (delta, gamma, theta, vega, etc.)
- Backtest management and analysis
"""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import pandas as pd
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor, execute_batch
from psycopg2.pool import SimpleConnectionPool
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from quant_vibe.logging.unified_logging import get_logger
from quant_vibe.utils.timestamp_utils import now_utc
from quant_vibe.utils.json_utils import sanitize_for_json

if TYPE_CHECKING:
    from quant_vibe.models import OptionsBar, UnderlyingBar

load_dotenv()
logger = get_logger(__name__)

# Greek value constraints for database numeric(8,6)
GREEK_MIN_VALUE = -99.999999
GREEK_MAX_VALUE = 99.999999


class TimescaleStore:
    """TimescaleDB storage client for options timeseries data."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        pool_size: int = 5,
    ):
        """Initialize TimescaleDB connection."""
        self.host = host or os.getenv("TIMESCALE_HOST", "localhost")
        self.port = port or int(os.getenv("TIMESCALE_PORT", "5432"))
        self.database = database or os.getenv("TIMESCALE_DB", "options_data")
        self.user = user or os.getenv("TIMESCALE_USER", "quantvibe")
        self.password = password or os.getenv("TIMESCALE_PASSWORD", "quantvibe_dev")

        self.pool = SimpleConnectionPool(
            minconn=1,
            maxconn=pool_size,
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
        )
        self._engine = None

    @property
    def engine(self):
        """Get SQLAlchemy engine for pandas operations (lazy initialization)."""
        if self._engine is None:
            connection_string = (
                f"postgresql://{self.user}:{self.password}@"
                f"{self.host}:{self.port}/{self.database}"
            )
            self._engine = create_engine(
                connection_string,
                poolclass=NullPool,
                connect_args={"options": "-c statement_timeout=600000"}  # 10 minutes
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

    @staticmethod
    def normalize_option_ticker(symbol: str) -> str:
        """Normalize option contract symbols to canonical format.

        Format: {UNDERLYING}{YYMMDD}{C|P}{STRIKE8DIGITS}
        Example: "SPXW251223P06865000"
        """
        if not symbol:
            return symbol

        # Remove "O:" prefix (Massive format)
        if symbol.startswith("O:"):
            symbol = symbol[2:]

        # Remove extra spaces (Schwab format)
        return symbol.replace(" ", "")

    def _coerce_greek_value(
        self, value: Optional[float], field_name: str, option_ticker: str
    ) -> Optional[float]:
        """Coerce Greek values to fit database constraints."""
        if value is None:
            return None

        if value < GREEK_MIN_VALUE or value > GREEK_MAX_VALUE:
            logger.warning(
                f"Greek value overflow - Field: {field_name}, "
                f"Value: {value}, Ticker: {option_ticker}, "
                f"Coercing to range [{GREEK_MIN_VALUE}, {GREEK_MAX_VALUE}]"
            )
            return max(GREEK_MIN_VALUE, min(GREEK_MAX_VALUE, value))

        return value

    def _prepare_option_bar_values(self, bar: "OptionsBar") -> tuple:
        """Prepare values from OptionsBar for database insertion."""
        option_ticker = self.normalize_option_ticker(bar.option_ticker)

        return (
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
            self._coerce_greek_value(
                float(bar.implied_volatility) if bar.implied_volatility is not None else None,
                "implied_volatility", option_ticker
            ),
            self._coerce_greek_value(
                float(bar.delta) if bar.delta is not None else None,
                "delta", option_ticker
            ),
            self._coerce_greek_value(
                float(bar.gamma) if bar.gamma is not None else None,
                "gamma", option_ticker
            ),
            self._coerce_greek_value(
                float(bar.theta) if bar.theta is not None else None,
                "theta", option_ticker
            ),
            self._coerce_greek_value(
                float(bar.vega) if bar.vega is not None else None,
                "vega", option_ticker
            ),
            self._coerce_greek_value(
                float(bar.rho) if bar.rho is not None else None,
                "rho", option_ticker
            ),
            bar.data_source,
        )

    def insert_option_bar(self, bar: "OptionsBar") -> None:
        """Insert a single options bar into the database."""
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

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, self._prepare_option_bar_values(bar))
            conn.commit()

    def bulk_insert_option_bars(
        self, bars: List["OptionsBar"], batch_size: int = 1000
    ) -> int:
        """Bulk insert options bars for efficient data loading."""
        if not bars:
            return 0

        query = """
        INSERT INTO options_bars (
            timestamp, option_ticker, underlying_ticker,
            open, high, low, close, volume, vwap, transactions,
            bid, ask, bid_size, ask_size,
            strike_price, contract_type, expiration_date,
            implied_volatility, delta, gamma, theta, vega, rho,
            data_source
        ) VALUES %s
        ON CONFLICT (timestamp, option_ticker) DO NOTHING
        """

        total_inserted = 0
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for i in range(0, len(bars), batch_size):
                    batch = bars[i : i + batch_size]
                    values = [self._prepare_option_bar_values(bar) for bar in batch]

                    execute_batch(cur, query.replace("%s", "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"), values)
                    total_inserted += cur.rowcount

            conn.commit()

        logger.info(f"Bulk inserted {total_inserted} option bars")
        return total_inserted

    def get_option_bars(
        self,
        start_date: datetime,
        end_date: datetime,
        option_ticker: Optional[str] = None,
        underlying_ticker: Optional[str] = None,
        strike: Optional[float] = None,
        contract_type: Optional[str] = None,
        expiration_date: Optional[datetime] = None,
        timeframe: str = "1min",
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Get option bars from database with flexible filtering."""
        table_map = {
            "1min": "options_bars",
            "5min": "options_bars_5min",
            "15min": "options_bars_15min",
            "1hour": "options_bars_1hour",
            "daily": "options_bars_daily",
        }

        if timeframe not in table_map:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        query = f"""
        SELECT
            timestamp, option_ticker, underlying_ticker,
            open, high, low, close, volume,
            bid, ask, bid_size, ask_size,
            strike_price, contract_type, expiration_date,
            implied_volatility, delta, gamma, theta, vega, rho
        FROM {table_map[timeframe]}
        WHERE timestamp >= %s AND timestamp <= %s
        """

        params = [start_date, end_date]

        if option_ticker:
            query += " AND option_ticker = %s"
            params.append(self.normalize_option_ticker(option_ticker))

        if underlying_ticker:
            query += " AND underlying_ticker = %s"
            params.append(underlying_ticker)

        if strike is not None:
            query += " AND strike_price = %s"
            params.append(strike)

        if contract_type:
            query += " AND contract_type = %s"
            params.append(contract_type)

        if expiration_date:
            query += " AND expiration_date = %s"
            params.append(expiration_date)

        query += " ORDER BY timestamp"

        if limit:
            query += f" LIMIT {limit}"

        return pd.read_sql(query, self.engine, params=tuple(params), parse_dates=["timestamp"])

    def get_options_chain_bars(
        self,
        timestamp: datetime,
        underlying_ticker: str,
        expiration_date: Optional[datetime] = None,
        contract_type: Optional[str] = None,
        min_strike: Optional[float] = None,
        max_strike: Optional[float] = None,
    ) -> pd.DataFrame:
        """Get all option bars at a specific timestamp (chain snapshot)."""
        query = """
        SELECT
            timestamp, option_ticker, underlying_ticker,
            open, high, low, close, volume,
            bid, ask, bid_size, ask_size,
            strike_price, contract_type, expiration_date,
            implied_volatility, delta, gamma, theta, vega, rho
        FROM options_bars
        WHERE timestamp = %s AND underlying_ticker = %s
        """

        params = [timestamp, underlying_ticker]

        if expiration_date:
            query += " AND expiration_date = %s"
            params.append(expiration_date)

        if contract_type:
            query += " AND contract_type = %s"
            params.append(contract_type)

        if min_strike is not None:
            query += " AND strike_price >= %s"
            params.append(min_strike)

        if max_strike is not None:
            query += " AND strike_price <= %s"
            params.append(max_strike)

        query += " ORDER BY strike_price, contract_type"

        return pd.read_sql(query, self.engine, params=tuple(params), parse_dates=["timestamp"])

    def get_options_for_backtest(
        self,
        start_date: datetime,
        end_date: datetime,
        underlying_ticker: str,
        min_dte: int = 0,
        max_dte: int = 45,
        strike_delta: float = 0.0,
        contract_types: Optional[List[str]] = None,
        min_volume: int = 0,
        min_bid: float = 0.0,
        timeframe: str = "5min",
        additional_filters: Optional[str] = None,
        timestamp_tolerance_seconds: int = 120,
    ) -> pd.DataFrame:
        """Get options data optimized for backtesting with DTE and filtering.

        Args:
            timestamp_tolerance_seconds: Maximum time difference (in seconds) between
                options bars and underlying bars for matching. Default is 120 seconds
                (±2 minutes). Uses LATERAL JOIN to find closest underlying timestamp
                within this window.
        """
        table_map = {
            "1min": "options_bars",
            "5min": "options_bars_5min",
            "15min": "options_bars_15min",
            "1hour": "options_bars_1hour",
            "daily": "options_bars_daily",
        }

        if timeframe not in table_map:
            raise ValueError(f"Invalid timeframe: {timeframe}")

        table_name = table_map[timeframe]

        # Build column selection with aggregation for non-1min timeframes
        if timeframe == "1min":
            columns = """
                ob.timestamp,
                ob.option_ticker,
                ob.underlying_ticker,
                ob.open,
                ob.high,
                ob.low,
                ob.close,
                ob.volume,
                ob.bid,
                ob.ask,
                ob.bid_size,
                ob.ask_size,
                ob.strike_price,
                ob.contract_type,
                ob.expiration_date,
                ob.implied_volatility,
                ob.delta,
                ob.gamma,
                ob.theta,
                ob.vega,
                ob.rho
            """
        else:
            # Aggregated tables have simpler column names
            columns = """
                ob.bucket as timestamp,
                ob.option_ticker,
                ob.underlying_ticker,
                ob.open,
                ob.high,
                ob.low,
                ob.close,
                ob.volume,
                ob.bid,
                ob.ask,
                ob.bid_size,
                ob.ask_size,
                ob.strike_price,
                ob.contract_type,
                ob.expiration_date,
                ob.implied_volatility,
                ob.delta,
                ob.gamma,
                ob.theta,
                ob.vega,
                ob.rho
            """

        # Use appropriate timestamp column name based on timeframe
        timestamp_col = "timestamp" if timeframe == "1min" else "bucket"

        query = f"""
        WITH filtered_options AS (
            SELECT DISTINCT
                {columns},
                (ob.expiration_date::date - ob.{timestamp_col}::date) as dte,
                ub.close as underlying_price,
                ABS(ob.strike_price - ub.close) as strike_distance,
                ABS(EXTRACT(EPOCH FROM (ub.timestamp - ob.{timestamp_col}))) as time_diff_seconds
            FROM {table_name} ob
            LEFT JOIN LATERAL (
                SELECT
                    timestamp,
                    close,
                    ticker
                FROM underlying_bars
                WHERE ticker = ob.underlying_ticker
                  AND timestamp >= ob.{timestamp_col} - INTERVAL '{timestamp_tolerance_seconds} seconds'
                  AND timestamp <= ob.{timestamp_col} + INTERVAL '{timestamp_tolerance_seconds} seconds'
                ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - ob.{timestamp_col})))
                LIMIT 1
            ) ub ON TRUE
            WHERE ob.{timestamp_col} >= %s
                AND ob.{timestamp_col} <= %s
                AND ob.underlying_ticker = %s
                AND (ob.expiration_date::date - ob.{timestamp_col}::date) >= %s
                AND (ob.expiration_date::date - ob.{timestamp_col}::date) <= %s
                AND ub.timestamp IS NOT NULL
        """

        params = [start_date, end_date, underlying_ticker, min_dte, max_dte]

        # Add optional filters
        if contract_types:
            query += f" AND ob.contract_type IN ({','.join(['%s'] * len(contract_types))})"
            params.extend(contract_types)

        if min_volume > 0:
            query += " AND ob.volume >= %s"
            params.append(min_volume)

        if min_bid > 0:
            # All tables now use "bid" column name
            query += " AND ob.bid >= %s"
            params.append(min_bid)

        if strike_delta > 0:
            query += " AND ABS(ob.strike_price - ub.close) <= %s"
            params.append(strike_delta)

        if additional_filters:
            query += f" AND {additional_filters}"

        query += """
        )
        SELECT * FROM filtered_options
        ORDER BY timestamp, strike_price, contract_type
        """

        df = pd.read_sql(
            query,
            self.engine,
            params=tuple(params),
            parse_dates=["timestamp", "expiration_date"]
        )

        # Log match quality statistics
        if not df.empty and 'time_diff_seconds' in df.columns:
            avg_diff = df['time_diff_seconds'].mean()
            max_diff = df['time_diff_seconds'].max()
            perfect_matches = (df['time_diff_seconds'] == 0).sum()
            close_matches = (df['time_diff_seconds'] <= 5).sum()  # Within 5 seconds

            logger.info(
                f"Retrieved {len(df)} option bars for backtest "
                f"({underlying_ticker}, {start_date} to {end_date}, "
                f"DTE {min_dte}-{max_dte}, timeframe={timeframe})"
            )
            logger.info(
                f"Timestamp match quality: "
                f"perfect={perfect_matches} ({perfect_matches/len(df)*100:.1f}%), "
                f"within_5s={close_matches} ({close_matches/len(df)*100:.1f}%), "
                f"avg_diff={avg_diff:.2f}s, max_diff={max_diff:.2f}s"
            )
        else:
            logger.info(
                f"Retrieved {len(df)} option bars for backtest "
                f"({underlying_ticker}, {start_date} to {end_date}, "
                f"DTE {min_dte}-{max_dte}, timeframe={timeframe})"
            )

        return df

    def get_underlying_price_from_options(
        self,
        timestamp: datetime,
        underlying_ticker: str,
        lookback_minutes: int = 5,
    ) -> Optional[float]:
        """Estimate underlying price from ATM options at given timestamp."""
        query = """
        WITH recent_bars AS (
            SELECT
                strike_price,
                contract_type,
                bid,
                ask,
                ABS(EXTRACT(EPOCH FROM (timestamp - %s))) as seconds_away
            FROM options_bars
            WHERE underlying_ticker = %s
                AND timestamp >= %s
                AND timestamp <= %s
                AND bid IS NOT NULL
                AND ask IS NOT NULL
                AND bid > 0
                AND ask > 0
        ),
        atm_spreads AS (
            SELECT
                strike_price,
                AVG(CASE WHEN contract_type = 'call' THEN (bid + ask) / 2 END) as call_mid,
                AVG(CASE WHEN contract_type = 'put' THEN (bid + ask) / 2 END) as put_mid,
                MIN(seconds_away) as seconds_away
            FROM recent_bars
            GROUP BY strike_price
            HAVING COUNT(DISTINCT contract_type) = 2
        )
        SELECT
            strike_price as underlying_price
        FROM atm_spreads
        WHERE call_mid IS NOT NULL AND put_mid IS NOT NULL
        ORDER BY ABS(call_mid - put_mid), seconds_away
        LIMIT 1
        """

        lookback_start = timestamp - timedelta(minutes=lookback_minutes)
        lookback_end = timestamp + timedelta(minutes=lookback_minutes)

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (timestamp, underlying_ticker, lookback_start, lookback_end)
                )
                result = cur.fetchone()
                return float(result[0]) if result else None

    def get_available_expirations(
        self, underlying_ticker: str, as_of_date: Optional[datetime] = None
    ) -> List[datetime]:
        """Get list of available expiration dates for an underlying."""
        query = """
        SELECT DISTINCT expiration_date
        FROM options_bars
        WHERE underlying_ticker = %s
        """

        params = [underlying_ticker]

        if as_of_date:
            query += " AND timestamp <= %s"
            params.append(as_of_date)

        query += " ORDER BY expiration_date"

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [row[0] for row in cur.fetchall()]

    def get_data_range(self, option_ticker: str) -> Optional[Tuple[datetime, datetime]]:
        """Get the date range of available data for a specific option."""
        query = """
        SELECT MIN(timestamp), MAX(timestamp)
        FROM options_bars
        WHERE option_ticker = %s
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (self.normalize_option_ticker(option_ticker),))
                result = cur.fetchone()
                return result if result[0] else None

    def delete_option_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        option_ticker: Optional[str] = None,
        underlying_ticker: Optional[str] = None,
    ) -> int:
        """Delete option data with flexible filtering."""
        if not any([start_date, end_date, option_ticker, underlying_ticker]):
            raise ValueError("At least one filter parameter must be specified")

        query = "DELETE FROM options_bars WHERE 1=1"
        params = []

        if start_date:
            query += " AND timestamp >= %s"
            params.append(start_date)

        if end_date:
            query += " AND timestamp <= %s"
            params.append(end_date)

        if option_ticker:
            query += " AND option_ticker = %s"
            params.append(self.normalize_option_ticker(option_ticker))

        if underlying_ticker:
            query += " AND underlying_ticker = %s"
            params.append(underlying_ticker)

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                deleted_count = cur.rowcount
                conn.commit()

        logger.info(f"Deleted {deleted_count} option bars")
        return deleted_count

    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics and metadata."""
        stats = {}

        queries = {
            "total_options_bars": "SELECT COUNT(*) FROM options_bars",
            "unique_contracts": "SELECT COUNT(DISTINCT option_ticker) FROM options_bars",
            "unique_underlyings": "SELECT COUNT(DISTINCT underlying_ticker) FROM options_bars",
            "date_range": "SELECT MIN(timestamp), MAX(timestamp) FROM options_bars",
            "total_size_mb": """
                SELECT pg_size_pretty(pg_total_relation_size('options_bars'))
            """,
            "compressed_chunks": """
                SELECT COUNT(*)
                FROM timescaledb_information.chunks
                WHERE hypertable_name = 'options_bars'
                    AND is_compressed = true
            """,
        }

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for key, query in queries.items():
                    cur.execute(query)
                    result = cur.fetchone()
                    if key == "date_range" and result[0]:
                        stats["oldest_data"] = result[0]
                        stats["newest_data"] = result[1]
                    elif key == "total_size_mb":
                        stats[key] = result[0]
                    elif result:
                        stats[key] = result[0]

        return stats

    # ==================== Underlying Bars Methods ====================

    def insert_underlying_bar(self, bar: "UnderlyingBar") -> None:
        """Insert a single underlying bar."""
        query = """
        INSERT INTO underlying_bars (
            timestamp, ticker, open, high, low, close, volume, vwap, transactions
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (timestamp, ticker) DO NOTHING
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        bar.timestamp,
                        bar.ticker,
                        float(bar.open),
                        float(bar.high),
                        float(bar.low),
                        float(bar.close),
                        bar.volume,
                        float(bar.vwap) if bar.vwap is not None else None,
                        bar.transactions,
                    ),
                )
            conn.commit()

    def bulk_insert_underlying_bars(
        self, bars: List["UnderlyingBar"], batch_size: int = 1000
    ) -> int:
        """Bulk insert underlying bars."""
        if not bars:
            return 0

        query = """
        INSERT INTO underlying_bars (
            timestamp, ticker, open, high, low, close, volume, vwap, transactions
        ) VALUES %s
        ON CONFLICT (timestamp, ticker) DO NOTHING
        """

        total_inserted = 0
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for i in range(0, len(bars), batch_size):
                    batch = bars[i : i + batch_size]
                    values = [
                        (
                            bar.timestamp,
                            bar.ticker,
                            float(bar.open),
                            float(bar.high),
                            float(bar.low),
                            float(bar.close),
                            bar.volume,
                            float(bar.vwap) if bar.vwap is not None else None,
                            bar.transactions,
                        )
                        for bar in batch
                    ]

                    execute_batch(
                        cur,
                        query.replace("%s", "(%s, %s, %s, %s, %s, %s, %s, %s, %s)"),
                        values
                    )
                    total_inserted += cur.rowcount

            conn.commit()

        logger.info(f"Bulk inserted {total_inserted} underlying bars")
        return total_inserted

    def get_underlying_bars(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1min",
        columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Get underlying bars from database."""
        # For now, we only have one underlying_bars table
        # TODO: Add support for aggregated underlying tables when they exist

        if columns:
            cols = ", ".join(columns)
        else:
            cols = "timestamp, ticker, open, high, low, close, volume"

        query = f"""
        SELECT {cols}
        FROM underlying_bars
        WHERE ticker = %s
            AND timestamp >= %s
            AND timestamp <= %s
        ORDER BY timestamp
        """

        return pd.read_sql(
            query,
            self.engine,
            params=(ticker, start_date, end_date),
            parse_dates=["timestamp"]
        )

    # ==================== Backtest Methods ====================

    def save_backtest_run(
        self,
        backtest_id: str,
        strategy_name: str,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        parameters: Dict[str, Any],
        final_capital: Optional[float] = None,
        total_return: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
        total_trades: Optional[int] = None,
        winning_trades: Optional[int] = None,
        losing_trades: Optional[int] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
        profit_factor: Optional[float] = None,
        win_rate: Optional[float] = None,
        status: str = "running",
        error_message: Optional[str] = None,
        max_positions: Optional[int] = 1,
    ) -> None:
        """Save backtest run metadata and metrics."""
        query = """
        INSERT INTO backtest_runs (
            backtest_id, strategy_name, ticker, start_date, end_date,
            initial_capital, parameters, final_capital, total_return,
            max_drawdown, sharpe_ratio, total_trades, winning_trades,
            losing_trades, avg_win, avg_loss, profit_factor, win_rate,
            status, error_message, max_positions, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (backtest_id) DO UPDATE SET
            final_capital = EXCLUDED.final_capital,
            total_return = EXCLUDED.total_return,
            max_drawdown = EXCLUDED.max_drawdown,
            sharpe_ratio = EXCLUDED.sharpe_ratio,
            total_trades = EXCLUDED.total_trades,
            winning_trades = EXCLUDED.winning_trades,
            losing_trades = EXCLUDED.losing_trades,
            avg_win = EXCLUDED.avg_win,
            avg_loss = EXCLUDED.avg_loss,
            profit_factor = EXCLUDED.profit_factor,
            win_rate = EXCLUDED.win_rate,
            status = EXCLUDED.status,
            error_message = EXCLUDED.error_message,
            max_positions = EXCLUDED.max_positions,
            updated_at = NOW()
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        backtest_id, strategy_name, ticker, start_date, end_date,
                        initial_capital, json.dumps(parameters), final_capital,
                        total_return, max_drawdown, sharpe_ratio, total_trades,
                        winning_trades, losing_trades, avg_win, avg_loss,
                        profit_factor, win_rate, status, error_message, max_positions, now_utc(), now_utc()
                    ),
                )
            conn.commit()

        logger.info(f"Saved backtest run {backtest_id} with status {status}")

    def update_backtest_status(
        self,
        backtest_id: str,
        status: str,
        error_message: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Update backtest run status."""
        query = """
        UPDATE backtest_runs
        SET status = %s,
            error_message = %s,
            completed_at = %s,
            updated_at = NOW()
        WHERE backtest_id = %s
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (status, error_message, completed_at, backtest_id))
            conn.commit()

        logger.info(f"Updated backtest {backtest_id} status to {status}")

    def update_backtest_metrics(
        self, backtest_id: str, metrics: Dict[str, Any]
    ) -> None:
        """Update backtest metrics after completion."""
        allowed_fields = [
            "final_capital", "total_return", "max_drawdown", "sharpe_ratio",
            "total_trades", "winning_trades", "losing_trades", "avg_win",
            "avg_loss", "profit_factor", "win_rate"
        ]

        updates = []
        params = []

        for field, value in metrics.items():
            if field in allowed_fields:
                updates.append(f"{field} = %s")
                params.append(value)

        if not updates:
            return

        params.append(backtest_id)
        query = f"""
        UPDATE backtest_runs
        SET {', '.join(updates)}, updated_at = NOW()
        WHERE backtest_id = %s
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()

        logger.info(f"Updated metrics for backtest {backtest_id}")

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
        """Get backtest run details."""
        query = """
        SELECT * FROM backtest_runs WHERE backtest_id = %s
        """

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (backtest_id,))
                result = cur.fetchone()
                return dict(result) if result else None

    def get_backtest_trades(self, backtest_id: str) -> pd.DataFrame:
        """Get backtest trade history."""
        query = """
        SELECT * FROM backtest_trades
        WHERE backtest_id = %s
        """
        # ORDER BY trade_number

        df = pd.read_sql(query, self.engine, params=(backtest_id,))

        # Parse metadata JSON if present
        if "metadata" in df.columns and not df.empty:
            df["metadata"] = df["metadata"].apply(
                lambda x: json.loads(x) if x else {}
            )

        return df

    def get_backtest_equity_curve(self, backtest_id: str) -> pd.DataFrame:
        """Get backtest equity curve."""
        query = """
        SELECT * FROM backtest_equity_curve
        WHERE backtest_id = %s
        ORDER BY timestamp
        """

        return pd.read_sql(
            query,
            self.engine,
            params=(backtest_id,),
            parse_dates=["timestamp"]
        )

    def get_backtest_history(
        self,
        strategy_name: Optional[str] = None,
        ticker: Optional[str] = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Get historical backtest runs."""
        query = """
        SELECT * FROM backtest_runs WHERE 1=1
        """

        params = []

        if strategy_name:
            query += " AND strategy_name = %s"
            params.append(strategy_name)

        if ticker:
            query += " AND ticker = %s"
            params.append(ticker)

        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)

        return pd.read_sql(
            query,
            self.engine,
            params=tuple(params),
            parse_dates=["start_date", "end_date", "created_at", "updated_at"]
        )

    def delete_backtest(self, backtest_id: str) -> bool:
        """Delete backtest and all related data."""
        query = "DELETE FROM backtest_runs WHERE backtest_id = %s"
        logger.info(f"Deleting backtest {backtest_id} from database")
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (backtest_id,))
                deleted = cur.rowcount > 0
                conn.commit()

        if deleted:
            logger.info(f"Deleted backtest {backtest_id}")

        return deleted

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
        """Save backtest analysis results."""
        query = """
        INSERT INTO backtest_analysis (
            backtest_id, total_trades, outlier_threshold_pct,
            num_big_winners, num_big_losers, findings,
            summary_markdown, recommendations_markdown, analyzer_version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING analysis_id
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        backtest_id, total_trades, outlier_threshold_pct,
                        num_big_winners, num_big_losers, json.dumps(findings),
                        summary_markdown, recommendations_markdown, analyzer_version
                    ),
                )
                analysis_id = cur.fetchone()[0]
                conn.commit()

        logger.info(f"Saved analysis {analysis_id} for backtest {backtest_id}")
        return analysis_id

    def get_backtest_analysis(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """Get backtest analysis results."""
        query = """
        SELECT * FROM backtest_analysis
        WHERE backtest_id = %s
        ORDER BY analyzed_at DESC
        LIMIT 1
        """

        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (backtest_id,))
                result = cur.fetchone()

                if result:
                    analysis = dict(result)
                    # Convert datetime objects to ISO format strings
                    for key in ["analyzed_at", "created_at", "updated_at"]:
                        if key in analysis and analysis[key]:
                            analysis[key] = analysis[key].isoformat()
                    return analysis

                return None

    def delete_backtest_analysis(self, backtest_id: str) -> int:
        """Delete backtest analysis records."""
        query = "DELETE FROM backtest_analysis WHERE backtest_id = %s"

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (backtest_id,))
                deleted_count = cur.rowcount
                conn.commit()

        logger.info(f"Deleted {deleted_count} analysis records for backtest {backtest_id}")
        return deleted_count

    def update_backtest_analysis(
        self,
        analysis_id: int,
        findings: Optional[Dict[str, Any]] = None,
        summary_markdown: Optional[str] = None,
        recommendations_markdown: Optional[str] = None,
    ) -> bool:
        """Update an existing backtest analysis."""
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

        params.append(analysis_id)
        query = f"""
        UPDATE backtest_analysis
        SET {', '.join(updates)}
        WHERE analysis_id = %s
        """

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                updated = cur.rowcount > 0
                conn.commit()

        if updated:
            logger.info(f"Updated analysis {analysis_id}")
        else:
            logger.warning(f"Analysis {analysis_id} not found for update")

        return updated

    # ==================== Context Manager Methods ====================

    def close(self) -> None:
        """Close all connections and dispose of resources."""
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