#!/usr/bin/env python3
"""
Optimize strategy parameters using grid search and walk-forward analysis.

This script:
1. Loads historical data for backtesting
2. Runs grid search to find optimal parameters
3. Performs walk-forward analysis to validate robustness
4. Saves results and generates recommendations

Usage:
    python scripts/optimize_strategy.py --strategy bullish_vertical_put
    python scripts/optimize_strategy.py --strategy bullish_vertical_call
    python scripts/optimize_strategy.py --strategy bullish_vertical_put --walk-forward
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
from datetime import datetime
import pandas as pd
import json
from pathlib import Path

from quant_vibe.optimization import ParameterOptimizer, WalkForwardAnalysis
from quant_vibe.strategies.registry import StrategyRegistry
from quant_vibe.utils import load_options_backtest_data
from quant_vibe.config.logging_config import setup_normalized_logging
from quant_vibe.utils import now_utc

# Setup logging
logger = setup_normalized_logging("optimize_strategy", "INFO", "logs/optimization")

# Global variable for status file path (set in main)
STATUS_FILE_PATH = None


def update_status(current: int, total: int, params: dict, metrics: dict, status_type: str = "progress"):
    """
    Update status file with current progress.

    Args:
        current: Current combination number
        total: Total combinations
        params: Current parameter combination
        metrics: Current metrics
        status_type: Type of status update ("progress", "complete", "log")
    """
    if STATUS_FILE_PATH is None:
        return

    try:
        status_data = {
            "timestamp": now_utc().isoformat(),
            "type": status_type,
            "current_combination": current,
            "total_combinations": total,
            "progress_pct": (current / total * 100) if total > 0 else 0,
            "current_params": params,
            "current_metrics": metrics,
        }

        # Append to status file as newline-delimited JSON
        with open(STATUS_FILE_PATH, "a") as f:
            f.write(json.dumps(status_data) + "\n")
    except Exception as e:
        logger.warning(f"Failed to update status file: {e}")


def log_message(message: str, level: str = "INFO"):
    """
    Log a message and write to status file.

    Args:
        message: Log message
        level: Log level (INFO, WARNING, ERROR)
    """
    # Log normally
    if level == "INFO":
        logger.info(message)
    elif level == "WARNING":
        logger.warning(message)
    elif level == "ERROR":
        logger.error(message)

    # Also write to status file for UI consumption
    if STATUS_FILE_PATH:
        try:
            log_data = {
                "timestamp": now_utc().isoformat(),
                "type": "log",
                "level": level,
                "message": message,
            }
            with open(STATUS_FILE_PATH, "a") as f:
                f.write(json.dumps(log_data) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write log to status file: {e}")


# Strategy mapping (use central registry)
STRATEGY_MAP = {
    name: StrategyRegistry.get_strategy_class(name)
    for name in StrategyRegistry.list_strategies()
}

# Default parameter grids for each strategy
# These are custom ranges - the registry can auto-generate grids if not specified
PARAM_GRIDS = {
    "bullish_vertical_put": {
        "spread_width": [10.0, 15.0, 20.0, 25.0, 30.0],
        "profit_target_min": [0.30, 0.40, 0.50, 0.60, 0.70],
        "trailing_stop_pct": [0.03, 0.05, 0.07, 0.10],
    },
    "bullish_vertical_call": {
        "spread_width": [10.0, 15.0, 20.0, 25.0],
        "profit_target_min": [0.30, 0.40, 0.50, 0.60],
        "pullback_amount": [10.0, 20.0, 30.0],
        "trailing_stop_pct": [0.03, 0.05, 0.07],
    },
    "coin_toss": {
        # Auto-generate from registry with custom ranges
        "target_price": [1.5, 2.0, 2.5],
        "price_tolerance": [0.25, 0.50, 0.75],
        "profit_target_pct": [0.50, 0.75, 1.0],
        "stop_loss_pct": [0.20, 0.30, 0.40],
    },
    "bollinger_band_limit": {
        # Optimize only the most important parameters (5 params × 3-4 values = 324 combos)
        # Key strategy parameters:
        "bb_period": [15, 20, 25],  # Bollinger Band lookback period
        "bb_std": [1.5, 2.0, 2.5],  # Standard deviation multiplier
        "bb_threshold": [0.02, 0.03, 0.04],  # Entry threshold (distance from band)
        "target_contract_price": [0.8, 1.0, 1.2],  # Limit order entry price
        "profit_target_price": [1.6, 2.0, 2.4],  # Limit order exit price
        # Fixed parameters set in FIXED_PARAMS:
        # - min_dte, max_dte (strategy concept)
        # - observation_period (strategy concept)
        # - num_spreads (position sizing)
        # - max_trades_daily (risk management)
        # - profit_target_pct (redundant with profit_target_price)
        # - stop_loss_pct (stop loss strategy)
        # - trailing_stop_pct, trailing_stop_threshold (trailing stop)
    },
}

# Fixed parameters for each strategy
FIXED_PARAMS = {
    "bullish_vertical_put": {
        "min_dte": 7,
        "max_dte": 45,
        "observation_period": 30,
        "pullback_amount": 50.0,
        "profit_target_max": 1.0,
        "num_spreads": 10,
        "min_volume": 50,
        "min_bid_ask_spread_pct": 10.0,
        "max_trades_daily": 1,
    },
    "bullish_vertical_call": {
        "min_dte": 0,
        "max_dte": 45,
        "observation_period": 15,  # Faster than 30 minutes
        "profit_target_max": 1.0,
        "num_spreads": 10,
        "max_trades_daily": 1,
    },
    "coin_toss": {
        "min_dte": 0,
        "max_dte": 0,
        "observation_period": 15,  # Faster than 30 minutes
        "profit_target_max": 1.0,
        "num_spreads": 10,
        "max_trades_daily": 5,
    },
    "bollinger_band_limit": {
        # Strategy concept parameters
        "min_dte": 0,
        "max_dte": 0,  # 0 DTE strategy
        # Position sizing
        "quantity": 10,
        # Price tolerance
        "price_tolerance": 1.0,
        "limit_buy_price": 1.0,  # Fixed at $1 limit entry
        # OTM range
        "otm_percent_min": 0.10,  # 10% OTM minimum
        "otm_percent_max": 0.15,  # 15% OTM maximum
        # Risk management
        "stop_loss_pct": 0.50,  # 50% stop loss
        "order_expiry_minutes": 60,  # 1 hour limit order expiry
        "max_trades_daily": 5,
    },
}


def run_grid_search(
    strategy_name: str,
    underlying_data: pd.DataFrame,
    options_data: pd.DataFrame,
    param_grid: dict,
    fixed_params: dict,
    initial_capital: float = 100000.0,
):
    """
    Run grid search optimization.

    Args:
        strategy_name: Name of strategy
        underlying_data: Underlying price data
        options_data: Options bars data
        param_grid: Parameter grid to search
        fixed_params: Fixed parameters
        initial_capital: Initial capital for backtests

    Returns:
        ParameterOptimizer instance with results
    """
    log_message(f"\n{'='*70}")
    log_message(f"GRID SEARCH OPTIMIZATION: {strategy_name}")
    log_message(f"{'='*70}")

    # Validate param_grid and fixed_params before optimization
    log_message("Validating parameter specifications...")
    try:
        # Combine param_grid and fixed_params for validation
        sample_params = {**fixed_params}
        for key, values in param_grid.items():
            sample_params[key] = values[0] if values else None

        # Validate using registry
        StrategyRegistry.validate_params(strategy_name, sample_params)
        log_message("✓ Parameter validation passed")
    except ValueError as e:
        log_message(f"❌ Parameter validation failed: {e}", level="ERROR")
        log_message("Please check your PARAM_GRIDS and FIXED_PARAMS configurations", level="ERROR")
        raise

    strategy_class = STRATEGY_MAP[strategy_name]

    optimizer = ParameterOptimizer(
        strategy_class=strategy_class,
        underlying_data=underlying_data,
        options_data=options_data,
        initial_capital=initial_capital,
    )

    # Define progress callback
    def progress_callback(current: int, total: int, params: dict, metrics: dict):
        update_status(current, total, params, metrics, status_type="progress")

    # Run grid search
    log_message(f"Starting grid search with parameter combinations...")
    results = optimizer.grid_search(
        param_grid=param_grid,
        fixed_params=fixed_params,
        verbose=True,
        progress_callback=progress_callback,
    )

    # Show top 10 results
    logger.info(f"\n{'='*70}")
    logger.info("TOP 10 PARAMETER COMBINATIONS (by Sharpe Ratio)")
    logger.info(f"{'='*70}")

    top_10 = optimizer.get_top_n(n=10, metric="sharpe_ratio", min_trades=10)

    for idx, row in top_10.iterrows():
        logger.info(f"\n{'-'*70}")
        logger.info(f"Rank #{top_10.index.get_loc(idx) + 1}")
        logger.info(f"Parameters: {row['params']}")
        logger.info(f"  Sharpe Ratio: {row['sharpe_ratio']:.2f}")
        logger.info(f"  Total Return: {row['total_return']:.2f}%")
        logger.info(f"  Win Rate: {row['win_rate']:.2f}%")
        logger.info(f"  Max Drawdown: {row['max_drawdown']:.2f}%")
        logger.info(f"  Num Trades: {row['num_trades']}")
        logger.info(f"  Profit Factor: {row['profit_factor']:.2f}")

    # Find optimal by different metrics
    logger.info(f"\n{'='*70}")
    logger.info("OPTIMAL PARAMETERS BY DIFFERENT METRICS")
    logger.info(f"{'='*70}")

    for metric in ["sharpe_ratio", "total_return", "win_rate"]:
        optimal = optimizer.find_optimal(metric=metric, min_trades=10)
        logger.info(f"\nBy {metric}:")
        logger.info(f"  Parameters: {optimal['params']}")
        logger.info(f"  Sharpe: {optimal['sharpe_ratio']:.2f}")
        logger.info(f"  Return: {optimal['total_return']:.2f}%")
        logger.info(f"  Win Rate: {optimal['win_rate']:.2f}%")

    return optimizer


def run_walk_forward(
    strategy_name: str,
    underlying_data: pd.DataFrame,
    options_data: pd.DataFrame,
    param_grid: dict,
    fixed_params: dict,
    train_window_days: int = 60,
    test_window_days: int = 30,
    initial_capital: float = 100000.0,
):
    """
    Run walk-forward analysis.

    Args:
        strategy_name: Name of strategy
        underlying_data: Underlying price data
        options_data: Options bars data
        param_grid: Parameter grid to search
        fixed_params: Fixed parameters
        train_window_days: Training window size
        test_window_days: Test window size
        initial_capital: Initial capital for backtests

    Returns:
        WalkForwardAnalysis instance with results
    """
    logger.info(f"\n{'='*70}")
    logger.info(f"WALK-FORWARD ANALYSIS: {strategy_name}")
    logger.info(f"{'='*70}")
    logger.info(f"Train window: {train_window_days} days")
    logger.info(f"Test window: {test_window_days} days")

    strategy_class = STRATEGY_MAP[strategy_name]

    wf = WalkForwardAnalysis(
        strategy_class=strategy_class,
        train_window_days=train_window_days,
        test_window_days=test_window_days,
        initial_capital=initial_capital,
    )

    # Run walk-forward
    results = wf.run(
        underlying_data=underlying_data,
        options_data=options_data,
        param_grid=param_grid,
        fixed_params=fixed_params,
        optimization_metric="sharpe_ratio",
        min_train_trades=5,
        verbose=True,
    )

    # Show period-by-period results
    logger.info(f"\n{'='*70}")
    logger.info("PERIOD-BY-PERIOD RESULTS")
    logger.info(f"{'='*70}")

    for idx, row in results.iterrows():
        logger.info(f"\nPeriod {row['period']}:")
        logger.info(f"  Train: {row['train_start'].date()} to {row['train_end'].date()}")
        logger.info(f"  Test:  {row['test_start'].date()} to {row['test_end'].date()}")
        logger.info(f"  Optimal params: {row['optimal_params']}")
        logger.info(f"  In-sample Sharpe:  {row['in_sample_sharpe']:.2f}")
        logger.info(f"  Out-of-sample Sharpe: {row['out_of_sample_sharpe']:.2f}")
        logger.info(f"  Sharpe degradation: {row['sharpe_degradation']:.1f}%")
        logger.info(f"  In-sample return:  {row['in_sample_return']:.2f}%")
        logger.info(f"  Out-of-sample return: {row['out_of_sample_return']:.2f}%")
        logger.info(f"  Return degradation: {row['return_degradation']:.1f}%")

    # Check robustness
    logger.info(f"\n{'='*70}")
    logger.info("ROBUSTNESS CHECK")
    logger.info(f"{'='*70}")

    robustness = wf.check_robustness(
        max_sharpe_degradation=50.0,
        max_return_degradation=50.0,
        min_out_of_sample_sharpe=1.0,
        min_out_of_sample_win_rate=55.0,
    )

    logger.info(f"\nPassed: {robustness['passed']}")
    logger.info(f"Avg Sharpe degradation: {robustness['avg_sharpe_degradation']:.1f}%")
    logger.info(f"Avg return degradation: {robustness['avg_return_degradation']:.1f}%")
    logger.info(f"Avg out-of-sample Sharpe: {robustness['avg_out_of_sample_sharpe']:.2f}")
    logger.info(f"Avg out-of-sample win rate: {robustness['avg_out_of_sample_win_rate']:.1f}%")

    if robustness["failures"]:
        logger.warning("\nFailures:")
        for failure in robustness["failures"]:
            logger.warning(f"  ❌ {failure}")

    if robustness["warnings"]:
        logger.warning("\nWarnings:")
        for warning in robustness["warnings"]:
            logger.warning(f"  ⚠️  {warning}")

    if robustness["passed"]:
        logger.info("\n✅ Strategy passes robustness checks!")
    else:
        logger.warning("\n❌ Strategy FAILS robustness checks - risk of overfitting!")

    return wf


def main():
    global STATUS_FILE_PATH

    parser = argparse.ArgumentParser(description="Optimize strategy parameters")
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        choices=list(STRATEGY_MAP.keys()),
        help="Strategy name to optimize",
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward analysis (in addition to grid search)",
    )
    parser.add_argument(
        "--train-start",
        type=str,
        default="2025-09-01",
        help="Training data start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--train-end",
        type=str,
        default="2025-11-30",
        help="Training data end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--test-start",
        type=str,
        default="2025-12-01",
        help="Test data start date (YYYY-MM-DD, for validation)",
    )
    parser.add_argument(
        "--test-end",
        type=str,
        default="2025-12-31",
        help="Test data end date (YYYY-MM-DD, for validation)",
    )
    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100000.0,
        help="Initial capital for backtests",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results/optimization",
        help="Output directory for results",
    )
    parser.add_argument(
        "--status-file",
        type=str,
        default=None,
        help="Path to write status updates for UI consumption (optional)",
    )

    args = parser.parse_args()

    # Set status file path if provided
    if args.status_file:
        STATUS_FILE_PATH = Path(args.status_file)
        # Clear/create status file
        STATUS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATUS_FILE_PATH.write_text("")  # Clear file
        log_message(f"Status file: {STATUS_FILE_PATH}")

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse dates and make timezone-aware (UTC)
    from datetime import timezone
    train_start = datetime.strptime(args.train_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    train_end = datetime.strptime(args.train_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    test_start = datetime.strptime(args.test_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    test_end = datetime.strptime(args.test_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Load data
    log_message(f"\n{'='*70}")
    log_message("LOADING DATA")
    log_message(f"{'='*70}")
    log_message(f"Training period: {args.train_start} to {args.train_end}")
    log_message(f"Test period: {args.test_start} to {args.test_end}")

    # Load full date range for walk-forward (if requested)
    if args.walk_forward:
        data_start = train_start
        data_end = test_end
    else:
        # For grid search only, use training + test data
        data_start = train_start
        data_end = test_end

    # Use 5-minute timeframe for optimizations to reduce memory usage by 95%
    # This allows longer date ranges without running out of memory
    options_data, underlying_data = load_options_backtest_data(
        underlying_ticker="SPX",
        start_date=data_start,
        end_date=data_end,
        min_dte=0,
        max_dte=45,
        verbose=True,
        timeframe="5min",  # 95% less memory than 1min data
    )

    log_message(f"\nLoaded {len(underlying_data)} underlying bars")
    log_message(f"Loaded {len(options_data)} options bars")

    # Get parameter grid and fixed params for strategy
    # Use predefined grids if available, otherwise auto-generate from registry
    if args.strategy in PARAM_GRIDS:
        param_grid = PARAM_GRIDS[args.strategy]
        log_message(f"Using predefined parameter grid for {args.strategy}")
    else:
        # Auto-generate from registry
        log_message(f"No predefined parameter grid found for {args.strategy}, auto-generating...")
        try:
            # Use registry's optimization grid generator
            param_grid = StrategyRegistry.generate_optimization_grid(args.strategy)
            log_message(f"Auto-generated parameter grid with {sum(len(v) for v in param_grid.values())} total parameter values")
        except Exception as e:
            log_message(f"Failed to auto-generate parameter grid: {e}", level="ERROR")
            log_message(f"Strategy '{args.strategy}' needs a predefined parameter grid in PARAM_GRIDS", level="ERROR")
            raise ValueError(f"No parameter grid defined for strategy '{args.strategy}' and auto-generation failed: {e}")

    if args.strategy in FIXED_PARAMS:
        fixed_params = FIXED_PARAMS[args.strategy]
        log_message(f"Using predefined fixed parameters for {args.strategy}")
    else:
        # Use default params from registry as fixed params
        try:
            default_params = StrategyRegistry.get_default_params(args.strategy)
            # Remove any params that are in the grid (those will be optimized)
            fixed_params = {k: v for k, v in default_params.items() if k not in param_grid}
            log_message(f"Using {len(fixed_params)} default parameters as fixed params")
        except Exception as e:
            log_message(f"Warning: Could not get default params: {e}", level="WARNING")
            fixed_params = {}

    # Run grid search (on training data only)
    # Note: underlying_data has timestamp as index, options_data has it as column
    train_underlying = underlying_data[
        (underlying_data.index >= train_start) & (underlying_data.index <= train_end)
    ]
    train_options = options_data[
        (options_data["timestamp"] >= train_start) & (options_data["timestamp"] <= train_end)
    ]

    # Calculate and log total combinations
    import math
    total_combinations = math.prod(len(values) for values in param_grid.values())
    log_message(f"\nParameter grid details:")
    for param_name, values in param_grid.items():
        log_message(f"  {param_name}: {len(values)} values {values}")
    log_message(f"\n⚠️  TOTAL COMBINATIONS: {total_combinations:,}")

    # Estimate memory and time
    rows_per_backtest = len(train_options)
    memory_per_backtest_gb = rows_per_backtest * 0.000002  # ~2KB per row
    total_memory_gb = total_combinations * memory_per_backtest_gb
    time_estimate_hours = total_combinations / 60  # ~1 min per backtest

    log_message(f"  Training data rows: {rows_per_backtest:,}")
    log_message(f"  Estimated memory: {total_memory_gb:.1f} GB")
    log_message(f"  Estimated time: {time_estimate_hours:.1f} hours ({time_estimate_hours/24:.1f} days)")

    # Warn if too large
    if total_combinations > 1000:
        log_message(f"\n⚠️  WARNING: {total_combinations:,} combinations is very large!", level="WARNING")
        log_message(f"  Consider reducing parameter grid size or using optimize_only parameter", level="WARNING")
        if total_combinations > 10000:
            log_message(f"\n❌ ERROR: {total_combinations:,} combinations is too large to optimize efficiently!", level="ERROR")
            log_message(f"  Maximum recommended: 1000 combinations", level="ERROR")
            log_message(f"  Please define a manual PARAM_GRIDS entry with fewer parameters/values", level="ERROR")
            raise ValueError(f"Parameter grid too large: {total_combinations:,} combinations")

    optimizer = run_grid_search(
        strategy_name=args.strategy,
        underlying_data=train_underlying,
        options_data=train_options,
        param_grid=param_grid,
        fixed_params=fixed_params,
        initial_capital=args.initial_capital,
    )

    # Save grid search results
    timestamp = now_utc().strftime("%Y%m%d_%H%M%S")
    grid_results_file = output_dir / f"{args.strategy}_grid_search_{timestamp}.csv"
    optimizer.save_results(str(grid_results_file))
    log_message(f"\nGrid search results saved to: {grid_results_file}")

    # Run walk-forward analysis if requested
    if args.walk_forward:
        wf = run_walk_forward(
            strategy_name=args.strategy,
            underlying_data=underlying_data,
            options_data=options_data,
            param_grid=param_grid,
            fixed_params=fixed_params,
            train_window_days=60,
            test_window_days=30,
            initial_capital=args.initial_capital,
        )

        # Save walk-forward results
        wf_results_file = output_dir / f"{args.strategy}_walk_forward_{timestamp}.csv"
        wf.save_results(str(wf_results_file))
        log_message(f"\nWalk-forward results saved to: {wf_results_file}")

    log_message(f"\n{'='*70}")
    log_message("OPTIMIZATION COMPLETE")
    log_message(f"{'='*70}")
    log_message(f"\nNext steps:")
    log_message(f"1. Review results in: {output_dir}")
    log_message(f"2. Update config/backtest.yaml with optimal parameters")
    log_message(f"3. Run out-of-sample backtest on {args.test_start} to {args.test_end}")
    log_message(f"4. If results look good, update config/live_trading.yaml")


if __name__ == "__main__":
    main()
