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

from quant_vibe.optimization import ParameterOptimizer, WalkForwardAnalysis
from quant_vibe.strategies.registry import StrategyRegistry
from quant_vibe.utils import load_options_backtest_data
from quant_vibe.config.logging_config import setup_normalized_logging

# Setup logging
logger = setup_normalized_logging("optimize_strategy", "INFO", "logs/optimization")

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
    logger.info(f"\n{'='*70}")
    logger.info(f"GRID SEARCH OPTIMIZATION: {strategy_name}")
    logger.info(f"{'='*70}")

    # Validate param_grid and fixed_params before optimization
    logger.info("Validating parameter specifications...")
    try:
        # Combine param_grid and fixed_params for validation
        sample_params = {**fixed_params}
        for key, values in param_grid.items():
            sample_params[key] = values[0] if values else None

        # Validate using registry
        StrategyRegistry.validate_params(strategy_name, sample_params)
        logger.info("✓ Parameter validation passed")
    except ValueError as e:
        logger.error(f"❌ Parameter validation failed: {e}")
        logger.error("Please check your PARAM_GRIDS and FIXED_PARAMS configurations")
        raise

    strategy_class = STRATEGY_MAP[strategy_name]

    optimizer = ParameterOptimizer(
        strategy_class=strategy_class,
        underlying_data=underlying_data,
        options_data=options_data,
        initial_capital=initial_capital,
    )

    # Run grid search
    results = optimizer.grid_search(
        param_grid=param_grid,
        fixed_params=fixed_params,
        verbose=True,
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

    args = parser.parse_args()

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
    logger.info(f"\n{'='*70}")
    logger.info("LOADING DATA")
    logger.info(f"{'='*70}")
    logger.info(f"Training period: {args.train_start} to {args.train_end}")
    logger.info(f"Test period: {args.test_start} to {args.test_end}")

    # Load full date range for walk-forward (if requested)
    if args.walk_forward:
        data_start = train_start
        data_end = test_end
    else:
        # For grid search only, use training + test data
        data_start = train_start
        data_end = test_end

    options_data, underlying_data = load_options_backtest_data(
        underlying_ticker="SPX",
        start_date=data_start,
        end_date=data_end,
        min_dte=0,
        max_dte=45,
        verbose=True,
    )

    logger.info(f"\nLoaded {len(underlying_data)} underlying bars")
    logger.info(f"Loaded {len(options_data)} options bars")

    # Get parameter grid and fixed params for strategy
    param_grid = PARAM_GRIDS[args.strategy]
    fixed_params = FIXED_PARAMS[args.strategy]

    # Run grid search (on training data only)
    # Note: underlying_data has timestamp as index, options_data has it as column
    train_underlying = underlying_data[
        (underlying_data.index >= train_start) & (underlying_data.index <= train_end)
    ]
    train_options = options_data[
        (options_data["timestamp"] >= train_start) & (options_data["timestamp"] <= train_end)
    ]

    optimizer = run_grid_search(
        strategy_name=args.strategy,
        underlying_data=train_underlying,
        options_data=train_options,
        param_grid=param_grid,
        fixed_params=fixed_params,
        initial_capital=args.initial_capital,
    )

    # Save grid search results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    grid_results_file = output_dir / f"{args.strategy}_grid_search_{timestamp}.csv"
    optimizer.save_results(str(grid_results_file))
    logger.info(f"\nGrid search results saved to: {grid_results_file}")

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
        logger.info(f"\nWalk-forward results saved to: {wf_results_file}")

    logger.info(f"\n{'='*70}")
    logger.info("OPTIMIZATION COMPLETE")
    logger.info(f"{'='*70}")
    logger.info(f"\nNext steps:")
    logger.info(f"1. Review results in: {output_dir}")
    logger.info(f"2. Update config/backtest.yaml with optimal parameters")
    logger.info(f"3. Run out-of-sample backtest on {args.test_start} to {args.test_end}")
    logger.info(f"4. If results look good, update config/live_trading.yaml")


if __name__ == "__main__":
    main()
