"""Helper functions for backtest scripts."""

import os
from datetime import datetime
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
            options_data = convert_decimals_to_float(options_data)

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
            underlying_data = convert_decimals_to_float(underlying_data)
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
                underlying_data = convert_decimals_to_float(underlying_data)
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


