"""Helper functions for backtest scripts."""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
from dotenv import load_dotenv

from .output import TeeOutput
from ..data.timescale_store import TimescaleStore

# Load environment variables
load_dotenv()


def setup_backtest_output(
    strategy_name: str,
    base_dir: Path | None = None,
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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

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
    db_profile: str | None = None,
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

    Returns:
        Tuple of (options_data, underlying_data) DataFrames

    Raises:
        ValueError: If no data is found or data is invalid

    Example:
        ```python
        # Load from local database (default)
        options_data, underlying_data = load_options_backtest_data(
            'SPX',
            start_date=datetime(2025, 12, 1),
            end_date=datetime(2025, 12, 15),
            min_dte=0,
            max_dte=0,
        )

        # Load from remote database
        options_data, underlying_data = load_options_backtest_data(
            'SPX',
            start_date=datetime(2025, 12, 1),
            end_date=datetime(2025, 12, 15),
            min_dte=0,
            max_dte=0,
            db_profile="remote",
        )
        ```
    """
    # Determine database profile from environment variable if not explicitly provided
    if db_profile is None:
        use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"
        db_profile = "remote" if use_remote else "local"

    if verbose:
        print("=" * 70)
        print("LOADING DATA")
        print("=" * 70)

    # Load data from TimescaleDB
    if verbose:
        db_location = "remote" if db_profile == "remote" else "local"
        print(f"\n1. Loading {underlying_ticker} options data from TimescaleDB ({db_location})...")

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
        # Load options data
        options_data = ts_store.get_options_for_backtest(
            underlying_ticker=underlying_ticker,
            start_time=start_date,
            end_time=end_date,
            min_dte=min_dte,
            max_dte=max_dte,
        )

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
            print(f"✅ Loaded {len(options_data):,} options bars")
            print(f"   Unique timestamps: {options_data['timestamp'].nunique():,}")
            print(f"   Unique contracts: {options_data['contract_symbol'].nunique():,}")
            print(
                f"   Date range: {options_data['timestamp'].min()} to "
                f"{options_data['timestamp'].max()}"
            )
            print(f"   Expirations: {sorted(options_data['expiration_date'].unique())}")

        # Load underlying price data
        # Try loading from underlying_bars table first (more accurate)
        if verbose:
            print(
                f"\n2. Loading {underlying_ticker} underlying price data from "
                f"underlying_bars table..."
            )

        underlying_data = ts_store.get_underlying_bars(
            ticker=underlying_ticker,
            start_time=start_date,
            end_time=end_date,
        )

        # Fall back to deriving from options if underlying_bars is empty
        if underlying_data.empty:
            if verbose:
                print(
                    f"⚠️  No data in underlying_bars table, falling back to deriving "
                    f"from options bid/ask..."
                )

            underlying_data = ts_store.get_underlying_price_from_options(
                underlying_ticker=underlying_ticker,
                start_time=start_date,
                end_time=end_date,
            )

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
            print(f"✅ Loaded {len(underlying_data):,} underlying price bars ({data_source})")
            print(f"   Date range: {underlying_data.index[0]} to {underlying_data.index[-1]}")
            print(
                f"   Price range: ${underlying_data['Low'].min():.2f} - "
                f"${underlying_data['High'].max():.2f}"
            )
            print(f"   Latest close: ${underlying_data['Close'].iloc[-1]:.2f}")
            print()

        return options_data, underlying_data

    except Exception as e:
        if verbose:
            print(f"❌ Error loading data: {e}")
            import traceback

            traceback.print_exc()
        raise

    finally:
        ts_store.close()


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
            print(f"\n✅ Trades saved to: {trades_file}")

    # Save equity curve
    if not results["equity_curve"].empty:
        equity_file = output_dir / f"{strategy_name}_equity_{timestamp}.csv"
        results["equity_curve"].to_csv(equity_file, index=False)
        saved_files["equity"] = equity_file

        if verbose:
            print(f"✅ Equity curve saved to: {equity_file}")

    return saved_files
