import os
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
from typing import Any, Dict
import pandas as pd

from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.logging.unified_logging import get_logger
from quant_vibe.utils.output import TeeOutput
from quant_vibe.utils.timestamp_utils import market_hours, now_utc

logger = get_logger(__name__)

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


