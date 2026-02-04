"""Helper functions for backtest scripts."""

import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Tuple, Optional, TYPE_CHECKING

import pandas as pd
from dotenv import load_dotenv

from .output import TeeOutput
from .dataframe_utils import convert_decimals_to_float
from ..data.timescale_store import TimescaleStore
from quant_vibe.utils.timestamp_utils import market_hours, now_utc
from quant_vibe.logging import get_logger

logger = get_logger(__name__)

# Avoid circular import: models → utils.timestamp_utils → utils.__init__ → backtest_helpers
if TYPE_CHECKING:
    pass

# Load environment variables
load_dotenv()


def _convert_decimals_to_float(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert Decimal columns to float for pandas compatibility.

    Pydantic models use Decimal for precision, but pandas operations
    (like .std(), .mean()) require numeric types that support arithmetic.

    Args:
        df: DataFrame with potential Decimal columns

    Returns:
        DataFrame with Decimal columns converted to float
    """
    return convert_decimals_to_float(df)


def setup_backtest_output(
    strategy_name: str,
    base_dir: Optional[Path] = None,
) -> Tuple[Path, str, TeeOutput]:
    """Setup output directory, timestamp, and dual output logger.

    Args:
        strategy_name: Name of the strategy (used for log filename)
        base_dir: Base directory for backtest results (default: ./backtests/backtest_results)

    Returns:
        Tuple of (output_dir, timestamp, tee_output)

    Example:
        ```python
        output_dir, timestamp, tee = setup_backtest_output("my_strategy")
        sys.stdout = tee
        try:
            # Your backtest code
            pass
        finally:
            tee.close()
        ```
    """
    # Determine base directory
    if base_dir is None:
        # Default to backtests/backtest_results relative to project root
        base_dir = Path.cwd() / "backtests" / "backtest_results"

    # Create output directory
    output_dir = Path(base_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamp
    timestamp = now_utc().strftime("%Y%m%d_%H%M%S")

    # Create log file
    log_file = output_dir / f"{strategy_name}_log_{timestamp}.txt"

    # Setup TeeOutput
    tee = TeeOutput(log_file)

    return output_dir, timestamp, tee


def load_options_backtest_data(
    underlying_ticker: str,
    start_date: datetime,
    end_date: datetime,
    min_dte: int,
    max_dte: int,
    verbose: bool = True,
    db_profile: Optional[str] = None,
    timeframe: str = "1min",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load options and underlying data from TimescaleDB with validation.

    Args:
        underlying_ticker: Underlying ticker symbol (e.g., 'SPX')
        start_date: Start date for backtest
        end_date: End date for backtest
        min_dte: Minimum days to expiration
        max_dte: Maximum days to expiration
        verbose: Print detailed loading information (default: True)
        db_profile: Database profile to use - "local" or "remote" (default: auto from USE_REMOTE_TIMESCALE)
            - If None (default): Uses USE_REMOTE_TIMESCALE env var ("true" → "remote", else "local")
            - "local": Uses TIMESCALE_* environment variables
            - "remote": Uses REMOTE_TIMESCALE_* environment variables
        timeframe: Time aggregation for data (default: "1min")
            - "1min": 1-minute bars (default, highest resolution, most memory)
            - "5min": 5-minute aggregated bars (recommended for optimizations, 95% less memory)
            - "15min": 15-minute aggregated bars (98% less memory)
            - "1hour": 1-hour aggregated bars
            - "daily": Daily aggregated bars

    Returns:
        Tuple of (options_data, underlying_data) DataFrames

    Raises:
        ValueError: If no data is found or data is invalid

    Example:
        ```python
        # Load 1-minute data (default, high memory usage)
        options_data, underlying_data = load_options_backtest_data(
            'SPX',
            start_date=datetime(2025, 12, 1),
            end_date=datetime(2025, 12, 15),
            min_dte=0,
            max_dte=0,
        )

        # Load 5-minute data (recommended for optimizations - 95% less memory)
        options_data, underlying_data = load_options_backtest_data(
            'SPX',
            start_date=datetime(2025, 10, 1),
            end_date=datetime(2026, 1, 1),
            min_dte=0,
            max_dte=45,
            timeframe="5min",  # Much more memory efficient!
        )
        ```
    """
    # Determine database profile from environment variable if not explicitly provided
    if db_profile is None:
        use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"
        db_profile = "remote" if use_remote else "local"

    if verbose:
        logger.info("=" * 70)
        logger.info("LOADING DATA")
        logger.info("=" * 70)

    # Load data from TimescaleDB
    if verbose:
        db_location = "remote" if db_profile == "remote" else "local"
        logger.info(f"\n1. Loading {underlying_ticker} options data from TimescaleDB ({db_location})...")

    # Create TimescaleStore based on profile
    if db_profile == "remote":
        ts_store = TimescaleStore(
            host=os.getenv("REMOTE_TIMESCALE_HOST"),
            port=int(os.getenv("REMOTE_TIMESCALE_PORT", "5432")),
            database=os.getenv("REMOTE_TIMESCALE_DB"),
            user=os.getenv("REMOTE_TIMESCALE_USER"),
            password=os.getenv("REMOTE_TIMESCALE_PASSWORD"),
        )
    else:  # local (default)
        ts_store = TimescaleStore()  # Uses TIMESCALE_* env vars

    # Convert to UTC market hours (market open for start, market close for end)
    start_date = market_hours(start_date)[0]  # Market open time
    end_date = market_hours(end_date)[1]  # Market close time

    # Log timeframe being used
    if verbose:
        memory_savings = {"5min": "95%", "15min": "98%", "1hour": "99%", "daily": "99.9%"}
        if timeframe != "1min":
            logger.info(f"   Using {timeframe} aggregated data (saves ~{memory_savings.get(timeframe, '90%')} memory)")

    try:
        # Load options data (returns DataFrame)
        options_data = ts_store.get_options_for_backtest(
            start_date,  # Pass positionally
            end_date,    # Pass positionally
            underlying_ticker,  # Pass positionally
            min_dte=min_dte,
            max_dte=max_dte,
            timeframe=timeframe,
        )

        # Convert Decimal columns to float for pandas compatibility if needed
        if not options_data.empty:
            options_data = _convert_decimals_to_float(options_data)

        if options_data.empty:
            error_msg = (
                f"No {underlying_ticker} options data found for the specified date range!\n"
                f"   Requested: {start_date.date()} to {end_date.date()}\n"
                f"\nTroubleshooting:\n"
                f"  1. Check available data with: SELECT MIN(timestamp), MAX(timestamp) "
                f"FROM options_bars WHERE underlying_ticker='{underlying_ticker}';\n"
                f"  2. Verify data collection is complete\n"
                f"  3. Adjust start_date and end_date"
            )
            raise ValueError(error_msg)

        if verbose:
            logger.info(f"✅ Loaded {len(options_data):,} options bars")
            logger.info(f"   Unique timestamps: {options_data['timestamp'].nunique():,}")
            logger.info(f"   Unique contracts: {options_data['option_ticker'].nunique():,}")
            logger.info(
                f"   Date range: {options_data['timestamp'].min()} to "
                f"{options_data['timestamp'].max()}"
            )
            logger.info(f"   Expirations: {sorted(options_data['expiration_date'].unique())}")

        # Load underlying price data
        # Try loading from underlying_bars table first (more accurate)
        if verbose:
            logger.info(
                f"\n2. Loading {underlying_ticker} underlying price data from "
                f"underlying_bars table..."
            )

        # Load underlying bars (returns DataFrame)
        underlying_data = ts_store.get_underlying_bars(
            ticker=underlying_ticker,
            start_date=start_date,
            end_date=end_date,
        )

        # Convert Decimal columns to float for pandas compatibility if needed
        if not underlying_data.empty:
            underlying_data = _convert_decimals_to_float(underlying_data)
            # Set timestamp as index for compatibility with existing code
            underlying_data = underlying_data.set_index('timestamp')

        # Fall back to deriving from options if underlying_bars is empty
        if underlying_data.empty:
            if verbose:
                logger.warning(
                    "No data in underlying_bars table, falling back to deriving "
                    "from options bid/ask..."
                )

            # Load from options (returns List[UnderlyingBar])
            underlying_bars_from_options = ts_store.get_underlying_price_from_options(
                underlying_ticker=underlying_ticker,
                start_time=start_date,
                end_time=end_date,
            )

            # Convert Pydantic models to DataFrame
            if not underlying_bars_from_options:
                underlying_data = pd.DataFrame()
            else:
                underlying_data = pd.DataFrame([bar.model_dump() for bar in underlying_bars_from_options])
                # Convert Decimal columns to float for pandas compatibility
                underlying_data = _convert_decimals_to_float(underlying_data)
                # Set timestamp as index for compatibility with existing code
                underlying_data = underlying_data.set_index('timestamp')

            if underlying_data.empty:
                error_msg = (
                    f"No underlying price data available!\n"
                    f"   - underlying_bars table is empty for {underlying_ticker}\n"
                    f"   - Could not derive from options bid/ask data\n"
                    f"\nTroubleshooting:\n"
                    f"  1. Run backfill script: python scripts/backfill_spx_underlying_1min.py\n"
                    f"  2. Check that options data has valid bid/ask prices"
                )
                raise ValueError(error_msg)

            data_source = "options (inferred)"
        else:
            data_source = "underlying_bars (actual)"

        if verbose:
            logger.info(f"✅ Loaded {len(underlying_data):,} underlying price bars ({data_source})")
            logger.info(f"   Date range: {underlying_data.index[0]} to {underlying_data.index[-1]}")
            logger.info(
                f"   Price range: ${underlying_data['low'].min():.2f} - "
                f"${underlying_data['high'].max():.2f}"
            )
            logger.info(f"   Latest close: ${underlying_data['close'].iloc[-1]:.2f}")
            logger.info("")

        return options_data, underlying_data

    except Exception as e:
        if verbose:
            logger.error(f"Error loading data: {e}", exc_info=True)
        raise

    finally:
        ts_store.close()


def load_options_backtest_data_chunked(
    underlying_ticker: str,
    start_date: datetime,
    end_date: datetime,
    min_dte: int = 0,
    max_dte: int = 45,
    verbose: bool = True,
    db_profile: Optional[str] = None,
    timeframe: str = "5min",
    chunk_days: int = 7,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load backtest data in chunks to avoid query timeouts.

    For large date ranges, the LATERAL JOIN query can timeout. This function
    splits the date range into smaller chunks (default 7 days), loads each
    separately, and concatenates the results.

    Args:
        underlying_ticker: Underlying ticker symbol (e.g., 'SPX')
        start_date: Start date for data loading
        end_date: End date for data loading
        min_dte: Minimum days to expiration (default: 0)
        max_dte: Maximum days to expiration (default: 45)
        verbose: Print progress information (default: True)
        db_profile: Database profile ("local" or "remote")
        timeframe: Time aggregation (default: "5min")
        chunk_days: Number of days per chunk (default: 7)

    Returns:
        Tuple of (options_data, underlying_data) DataFrames

    Example:
        ```python
        # Load 3 months of data in weekly chunks
        options_data, underlying_data = load_options_backtest_data_chunked(
            underlying_ticker="SPX",
            start_date=datetime(2024, 3, 1),
            end_date=datetime(2024, 6, 1),
            min_dte=0,
            max_dte=45,
            timeframe="5min",
            chunk_days=7,  # Load 1 week at a time
        )
        ```
    """
    # Determine database profile from environment variable if not explicitly provided
    if db_profile is None:
        use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"
        db_profile = "remote" if use_remote else "local"

    # Create TimescaleStore based on profile
    if db_profile == "remote":
        ts_store = TimescaleStore(
            host=os.getenv("REMOTE_TIMESCALE_HOST"),
            port=int(os.getenv("REMOTE_TIMESCALE_PORT", "5432")),
            database=os.getenv("REMOTE_TIMESCALE_DB"),
            user=os.getenv("REMOTE_TIMESCALE_USER"),
            password=os.getenv("REMOTE_TIMESCALE_PASSWORD"),
        )
    else:
        ts_store = TimescaleStore()

    # Convert to UTC market hours
    start_dt = market_hours(start_date)[0]  # Market open time
    end_dt = market_hours(end_date)[1]  # Market close time

    # Generate chunk date ranges
    chunks = []
    current_start = start_dt
    while current_start < end_dt:
        current_end = min(current_start + timedelta(days=chunk_days), end_dt)
        chunks.append((current_start, current_end))
        current_start = current_end

    if verbose:
        logger.info("=" * 70)
        logger.info("LOADING DATA (CHUNKED)")
        logger.info("=" * 70)
        logger.info(f"Date range: {start_dt.date()} to {end_dt.date()}")
        logger.info(f"Chunk size: {chunk_days} days ({len(chunks)} chunks)")
        logger.info(f"Timeframe: {timeframe}")
        logger.info("")

    # Load each chunk
    options_chunks = []
    underlying_chunks = []

    try:
        for i, (chunk_start, chunk_end) in enumerate(chunks):
            if verbose:
                logger.info(f"Loading chunk {i+1}/{len(chunks)}: {chunk_start.date()} to {chunk_end.date()}...")

            # Load options data for this chunk (skip LATERAL JOIN for speed)
            try:
                options_chunk = ts_store.get_options_for_backtest(
                    chunk_start,
                    chunk_end,
                    underlying_ticker,
                    min_dte=min_dte,
                    max_dte=max_dte,
                    timeframe=timeframe,
                    skip_underlying_join=True,  # Fast path - join in Python
                )

                if not options_chunk.empty:
                    options_chunk = _convert_decimals_to_float(options_chunk)
                    options_chunks.append(options_chunk)
                    if verbose:
                        logger.info(f"  ✓ {len(options_chunk):,} options bars")

            except Exception as e:
                logger.warning(f"  ⚠ Chunk {i+1} options failed: {e}")

            # Load underlying data for this chunk
            try:
                underlying_chunk = ts_store.get_underlying_bars(
                    ticker=underlying_ticker,
                    start_date=chunk_start,
                    end_date=chunk_end,
                )

                if not underlying_chunk.empty:
                    underlying_chunk = _convert_decimals_to_float(underlying_chunk)
                    underlying_chunks.append(underlying_chunk)

            except Exception as e:
                logger.warning(f"  ⚠ Chunk {i+1} underlying failed: {e}")

        # Concatenate all chunks
        if options_chunks:
            options_data = pd.concat(options_chunks, ignore_index=True)
            # Remove duplicates that might occur at chunk boundaries
            options_data = options_data.drop_duplicates(
                subset=['timestamp', 'option_ticker'], keep='first'
            )
        else:
            options_data = pd.DataFrame()

        if underlying_chunks:
            underlying_data = pd.concat(underlying_chunks, ignore_index=False)
            # Remove duplicates at chunk boundaries
            underlying_data = underlying_data[~underlying_data.index.duplicated(keep='first')]
            # Ensure it has timestamp index
            if 'timestamp' in underlying_data.columns:
                underlying_data = underlying_data.set_index('timestamp')
        else:
            underlying_data = pd.DataFrame()

        # Join underlying prices using merge_asof (much faster than SQL LATERAL JOIN)
        if not options_data.empty and not underlying_data.empty:
            if verbose:
                logger.info("Joining underlying prices using merge_asof...")

            # Prepare underlying data for merge_asof
            underlying_for_merge = underlying_data.reset_index()[['timestamp', 'close']].copy()
            underlying_for_merge = underlying_for_merge.rename(columns={'close': 'underlying_price'})
            underlying_for_merge = underlying_for_merge.sort_values('timestamp')

            # Sort options by timestamp for merge_asof
            options_data = options_data.sort_values('timestamp')

            # Use merge_asof to find nearest underlying price within tolerance
            options_data = pd.merge_asof(
                options_data,
                underlying_for_merge,
                on='timestamp',
                direction='nearest',
                tolerance=pd.Timedelta('120s'),  # 2 minute tolerance
            )

            # Calculate strike_distance if underlying_price is available
            if 'underlying_price' in options_data.columns:
                options_data['strike_distance'] = abs(
                    options_data['strike_price'] - options_data['underlying_price']
                )

            if verbose:
                matched = options_data['underlying_price'].notna().sum()
                total = len(options_data)
                logger.info(f"  ✓ Matched {matched:,}/{total:,} ({matched/total*100:.1f}%) with underlying prices")

        if verbose:
            logger.info("")
            logger.info(f"✅ Total: {len(options_data):,} options bars, {len(underlying_data):,} underlying bars")
            if not options_data.empty:
                logger.info(f"   Date range: {options_data['timestamp'].min()} to {options_data['timestamp'].max()}")

        if options_data.empty:
            raise ValueError(
                f"No {underlying_ticker} options data found for the specified date range!\n"
                f"   Requested: {start_date.date()} to {end_date.date()}\n"
                f"   Data may not exist for this period."
            )

        return options_data, underlying_data

    finally:
        ts_store.close()


def load_options_backtest_data_daily(
    underlying_ticker: str,
    trade_date: datetime,
    min_dte: int,
    max_dte: int,
    timeframe: str = "1min",
    cache_enabled: bool = True,
    db_profile: Optional[str] = None,
    redis_client: Optional[Any] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load single day of backtest data with Redis caching.

    This function loads options and underlying data for a single trading day,
    with optional Redis caching to speed up repeated backtests on the same data.

    Args:
        underlying_ticker: Underlying ticker symbol (e.g., 'SPX')
        trade_date: Trading date (will be converted to market hours)
        min_dte: Minimum days to expiration
        max_dte: Maximum days to expiration
        timeframe: Time aggregation (default: "1min")
        cache_enabled: Whether to use Redis caching (default: True)
        db_profile: Database profile ("local" or "remote")
        redis_client: Optional Redis client for caching

    Returns:
        Tuple of (options_data, underlying_data) DataFrames

    Example:
        ```python
        # Load data for single day with caching
        options, underlying = load_options_backtest_data_daily(
            'SPX',
            trade_date=datetime(2024, 1, 15),
            min_dte=0,
            max_dte=45,
            timeframe="5min"
        )
        ```
    """
    # Convert to market hours for this day
    market_open = trade_date.replace(hour=14, minute=30, second=0, microsecond=0)  # 9:30 AM ET in UTC
    market_close = trade_date.replace(hour=21, minute=0, second=0, microsecond=0)  # 4:00 PM ET in UTC

    # Create cache key for this specific day
    cache_key = f"backtest:{underlying_ticker}:{trade_date.date()}:{min_dte}-{max_dte}:{timeframe}"

    # Try to get from cache if enabled
    if cache_enabled and redis_client is not None:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                logger.info(f"Using cached data for {trade_date.date()}")
                return pickle.loads(cached)
        except Exception as e:
            logger.warning(f"Cache read failed, loading from database: {e}")

    # Load from database
    options_data, underlying_data = load_options_backtest_data(
        underlying_ticker=underlying_ticker,
        start_date=market_open,
        end_date=market_close,
        min_dte=min_dte,
        max_dte=max_dte,
        verbose=False,  # Less verbose for daily loading
        db_profile=db_profile,
        timeframe=timeframe,
    )

    # Cache for next time if enabled (1 week TTL)
    if cache_enabled and redis_client is not None:
        try:
            redis_client.setex(
                cache_key,
                timedelta(days=7),
                pickle.dumps((options_data, underlying_data))
            )
            logger.debug(f"Cached data for {trade_date.date()}")
        except Exception as e:
            logger.warning(f"Cache write failed: {e}")

    return options_data, underlying_data


def save_backtest_results(
    results: Dict,
    strategy_name: str,
    output_dir: Path,
    timestamp: str,
    verbose: bool = True,
) -> Dict[str, Path]:
    """Save backtest results to CSV files.

    Args:
        results: Results dictionary from backtest engine (must contain 'trades' and 'equity_curve')
        strategy_name: Name of the strategy (used for filenames)
        output_dir: Directory to save results
        timestamp: Timestamp string for unique filenames
        verbose: Print save confirmations (default: True)

    Returns:
        Dictionary mapping result type to file path (e.g., {'trades': Path(...), 'equity': Path(...)})

    Example:
        ```python
        saved_files = save_backtest_results(
            results=results,
            strategy_name="my_strategy",
            output_dir=output_dir,
            timestamp=timestamp,
        )
        print(f"Trades saved to: {saved_files['trades']}")
        ```
    """
    saved_files = {}

    # Save trades
    if not results["trades"].empty:
        trades_file = output_dir / f"{strategy_name}_trades_{timestamp}.csv"
        results["trades"].to_csv(trades_file, index=False)
        saved_files["trades"] = trades_file

        if verbose:
            logger.info(f"\n✅ Trades saved to: {trades_file}")

    # Save equity curve
    if not results["equity_curve"].empty:
        equity_file = output_dir / f"{strategy_name}_equity_{timestamp}.csv"
        results["equity_curve"].to_csv(equity_file, index=False)
        saved_files["equity"] = equity_file

        if verbose:
            logger.info(f"✅ Equity curve saved to: {equity_file}")

    return saved_files


def save_backtest_to_db(
    backtest_id: str,
    strategy_name: str,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
    results: Dict,
    parameters: Optional[Dict] = None,
    max_positions: int = 1,
    verbose: bool = True,
    db_profile: Optional[str] = None,
) -> None:
    """Save backtest results to PostgreSQL database.

    This function persists the complete backtest results to TimescaleDB,
    including metadata, trades, equity curve, and performance metrics.

    Args:
        backtest_id: Unique identifier for this backtest run
        strategy_name: Name of the strategy
        start_date: Backtest start date
        end_date: Backtest end date
        initial_capital: Starting capital
        results: Results dictionary from backtest engine
        parameters: Strategy parameters (optional)
        max_positions: Maximum concurrent positions
        verbose: Print save confirmations (default: True)
        db_profile: Database profile to use - "local" or "remote" (default: auto from USE_REMOTE_TIMESCALE)

    Example:
        ```python
        save_backtest_to_db(
            backtest_id="bullish_vertical_put_20251230_143022",
            strategy_name="bullish_vertical_put",
            start_date=datetime(2025, 12, 1),
            end_date=datetime(2025, 12, 15),
            initial_capital=100000.0,
            results=results,
            parameters={'spread_width': 20, 'min_dte': 0, 'max_dte': 0}
        )
        ```
    """
    # Determine database profile from environment variable if not explicitly provided
    if db_profile is None:
        use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"
        db_profile = "remote" if use_remote else "local"

    # Create TimescaleStore based on profile
    if db_profile == "remote":
        ts_store = TimescaleStore(
            host=os.getenv("REMOTE_TIMESCALE_HOST"),
            port=int(os.getenv("REMOTE_TIMESCALE_PORT", "5432")),
            database=os.getenv("REMOTE_TIMESCALE_DB"),
            user=os.getenv("REMOTE_TIMESCALE_USER"),
            password=os.getenv("REMOTE_TIMESCALE_PASSWORD"),
        )
    else:  # local (default)
        ts_store = TimescaleStore()  # Uses TIMESCALE_* env vars

    try:
        if verbose:
            db_location = "remote" if db_profile == "remote" else "local"
            logger.info(f"\n💾 Saving backtest results to PostgreSQL ({db_location})...")

        # 1. Save backtest run metadata
        ts_store.save_backtest_run(
            backtest_id=backtest_id,
            end_date=end_date,
            initial_capital=initial_capital,
            max_positions=max_positions,
            parameters=parameters,
            start_date=start_date,
            status="completed",
            strategy_name=strategy_name,
            ticker="SPX",  # Currently only SPX supported
        )

        if verbose:
            logger.info(f"   ✅ Backtest metadata saved (ID: {backtest_id})")

        # 2. Save performance metrics
        # Convert NumPy types to Python native types for PostgreSQL compatibility
        def to_python_type(value: Any) -> Optional[float]:
            """Convert NumPy types to Python native types."""
            if value is None:
                return None
            # Check if it's a NumPy type
            if hasattr(value, 'item'):
                return float(value.item())  # Convert numpy scalar to Python type
            return float(value) if isinstance(value, (int, float)) else value

        final_capital = to_python_type(results.get("final_capital"))
        total_return = (final_capital - initial_capital) if final_capital is not None else None

        metrics = {
            "final_capital": final_capital,
            "total_return": total_return,
            "total_return_pct": to_python_type(results.get("total_return_pct")),
            "total_trades": to_python_type(results.get("total_trades")),
            "winning_trades": to_python_type(results.get("winning_trades")),
            "losing_trades": to_python_type(results.get("losing_trades")),
            "win_rate": to_python_type(results.get("win_rate")),
            "avg_win": to_python_type(results.get("avg_win")),
            "avg_loss": to_python_type(results.get("avg_loss")),
            "profit_factor": to_python_type(results.get("profit_factor")),
            "max_drawdown": to_python_type(results.get("max_drawdown")),
            "sharpe_ratio": to_python_type(results.get("sharpe_ratio")),
        }

        logger.debug(f"Backtest performance metrics to save: {metrics}")

        ts_store.update_backtest_metrics(backtest_id, metrics)

        if verbose:
            logger.info("   ✅ Performance metrics saved")

        # 3. Save trades
        if not results["trades"].empty:
            ts_store.save_backtest_trades(backtest_id, results["trades"])
            if verbose:
                logger.info(f"   ✅ {len(results['trades'])} trades saved")

        # 4. Save equity curve
        if not results["equity_curve"].empty:
            ts_store.save_backtest_equity_curve(backtest_id, results["equity_curve"])
            if verbose:
                logger.info(
                    f"   ✅ {len(results['equity_curve'])} equity curve points saved"
                )

        if verbose:
            logger.info("\n✅ Backtest results saved to database successfully!")

    except Exception as e:
        if verbose:
            logger.error(f"Error saving to database: {e}", exc_info=True)
        raise

    finally:
        ts_store.close()
