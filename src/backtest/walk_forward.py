"""Walk-forward analysis for strategy validation and robustness testing.

This module provides tools to:
1. Perform rolling window optimization and out-of-sample testing
2. Detect overfitting through performance degradation analysis
3. Validate parameter stability across different market conditions
4. Generate reports on out-of-sample performance
"""

import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional, Type
from datetime import datetime, timedelta
import logging

from .options_engine import OptionsBacktestEngine
from quant_vibe.strategies.options_base import OptionsStrategy
from .parameter_optimizer import ParameterOptimizer
from quant_vibe.config.logging_config import setup_normalized_logging

logger = setup_normalized_logging("walk_forward", "INFO", "logs/optimization")


class WalkForwardAnalysis:
    """Perform walk-forward analysis on trading strategies."""

    def __init__(
        self,
        strategy_class: Type[OptionsStrategy],
        train_window_days: int = 60,
        test_window_days: int = 30,
        initial_capital: float = 100000.0,
    ):
        """
        Initialize walk-forward analyzer.

        Args:
            strategy_class: Strategy class to test
            train_window_days: Number of days to use for training/optimization
            test_window_days: Number of days to use for out-of-sample testing
            initial_capital: Initial capital for backtests
        """
        self.strategy_class = strategy_class
        self.train_window_days = train_window_days
        self.test_window_days = test_window_days
        self.initial_capital = initial_capital
        self.results: Optional[pd.DataFrame] = None

    def run(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        fixed_params: Optional[Dict[str, Any]] = None,
        optimization_metric: str = "sharpe_ratio",
        min_train_trades: int = 5,
        verbose: bool = True,
    ) -> pd.DataFrame:
        """
        Run walk-forward optimization.

        Process:
        1. Split data into overlapping train/test windows
        2. For each window:
           a. Optimize parameters on training data
           b. Test optimal parameters on out-of-sample test data
        3. Compare in-sample vs out-of-sample performance

        Args:
            underlying_data: DataFrame with underlying price data
            options_data: DataFrame with options bars data
            param_grid: Dict of parameters to optimize
            fixed_params: Dict of fixed parameters
            optimization_metric: Metric to optimize ('sharpe_ratio', 'total_return', etc.)
            min_train_trades: Minimum trades required in training period
            verbose: Whether to print progress

        Returns:
            DataFrame with results by test period:
            - period: int (test period number)
            - train_start, train_end: dates for training window
            - test_start, test_end: dates for test window
            - optimal_params: dict of optimal parameters from training
            - in_sample_*: metrics from training period
            - out_of_sample_*: metrics from test period
            - degradation_*: percentage drop from in-sample to out-of-sample
        """
        fixed_params = fixed_params or {}

        # Get date range
        # Handle both timestamp as column or as index
        if "timestamp" in underlying_data.columns:
            underlying_data = underlying_data.sort_values("timestamp")
            min_date = underlying_data["timestamp"].min()
            max_date = underlying_data["timestamp"].max()
        else:
            # Timestamp is the index
            underlying_data = underlying_data.sort_index()
            min_date = underlying_data.index.min()
            max_date = underlying_data.index.max()

        logger.info(
            f"Starting walk-forward analysis from {min_date} to {max_date}",
            extra={
                "min_date": str(min_date),
                "max_date": str(max_date),
                "train_days": self.train_window_days,
                "test_days": self.test_window_days,
            },
        )

        # Generate train/test periods
        periods = self._generate_periods(min_date, max_date)

        if len(periods) == 0:
            raise ValueError(
                f"Not enough data for walk-forward analysis. "
                f"Need at least {self.train_window_days + self.test_window_days} days."
            )

        logger.info(
            f"Generated {len(periods)} walk-forward periods",
            extra={"num_periods": len(periods)},
        )

        results = []

        for idx, period in enumerate(periods, 1):
            if verbose:
                logger.info(
                    f"\n[Period {idx}/{len(periods)}] "
                    f"Train: {period['train_start'].date()} to {period['train_end'].date()}, "
                    f"Test: {period['test_start'].date()} to {period['test_end'].date()}",
                    extra={
                        "period": idx,
                        "total_periods": len(periods),
                        "train_start": str(period["train_start"].date()),
                        "train_end": str(period["train_end"].date()),
                        "test_start": str(period["test_start"].date()),
                        "test_end": str(period["test_end"].date()),
                    },
                )

            try:
                # Split data into train/test
                train_underlying, train_options = self._filter_data(
                    underlying_data,
                    options_data,
                    period["train_start"],
                    period["train_end"],
                )

                test_underlying, test_options = self._filter_data(
                    underlying_data,
                    options_data,
                    period["test_start"],
                    period["test_end"],
                )

                # Optimize on training data
                if verbose:
                    logger.info("  Optimizing parameters on training data...")

                optimizer = ParameterOptimizer(
                    strategy_class=self.strategy_class,
                    underlying_data=train_underlying,
                    options_data=train_options,
                    initial_capital=self.initial_capital,
                    start_date=period["train_start"],
                    end_date=period["train_end"],
                )

                optimizer.grid_search(
                    param_grid=param_grid,
                    fixed_params=fixed_params,
                    verbose=False,  # Suppress grid search output
                )

                # Find optimal parameters
                optimal_result = optimizer.find_optimal(
                    metric=optimization_metric,
                    min_trades=min_train_trades,
                )

                optimal_params = optimal_result["params"]

                if verbose:
                    logger.info(
                        f"  Optimal params: {optimal_params}",
                        extra={"optimal_params": optimal_params},
                    )
                    logger.info(
                        f"  In-sample {optimization_metric}: {optimal_result[optimization_metric]:.2f}",
                        extra={
                            "in_sample_metric": optimization_metric,
                            "value": optimal_result[optimization_metric],
                        },
                    )

                # Test on out-of-sample data
                if verbose:
                    logger.info("  Testing on out-of-sample data...")

                out_of_sample_metrics = self._run_backtest(
                    optimal_params,
                    test_underlying,
                    test_options,
                    period["test_start"],
                    period["test_end"],
                )

                if verbose:
                    logger.info(
                        f"  Out-of-sample {optimization_metric}: "
                        f"{out_of_sample_metrics[optimization_metric]:.2f}",
                        extra={
                            "out_of_sample_metric": optimization_metric,
                            "value": out_of_sample_metrics[optimization_metric],
                        },
                    )

                # Calculate degradation
                degradation = self._calculate_degradation(optimal_result, out_of_sample_metrics)

                if verbose:
                    logger.info(
                        f"  Sharpe degradation: {degradation['sharpe_ratio_degradation']:.1f}%, "
                        f"Return degradation: {degradation['total_return_degradation']:.1f}%",
                        extra={
                            "sharpe_degradation": degradation["sharpe_ratio_degradation"],
                            "return_degradation": degradation["total_return_degradation"],
                        },
                    )

                # Store results
                result = {
                    "period": idx,
                    "train_start": period["train_start"],
                    "train_end": period["train_end"],
                    "test_start": period["test_start"],
                    "test_end": period["test_end"],
                    "optimal_params": optimal_params,
                    # In-sample metrics
                    "in_sample_sharpe": optimal_result["sharpe_ratio"],
                    "in_sample_return": optimal_result["total_return"],
                    "in_sample_win_rate": optimal_result["win_rate"],
                    "in_sample_max_drawdown": optimal_result["max_drawdown"],
                    "in_sample_num_trades": optimal_result["num_trades"],
                    # Out-of-sample metrics
                    "out_of_sample_sharpe": out_of_sample_metrics["sharpe_ratio"],
                    "out_of_sample_return": out_of_sample_metrics["total_return"],
                    "out_of_sample_win_rate": out_of_sample_metrics["win_rate"],
                    "out_of_sample_max_drawdown": out_of_sample_metrics["max_drawdown"],
                    "out_of_sample_num_trades": out_of_sample_metrics["num_trades"],
                    # Degradation
                    "sharpe_degradation": degradation["sharpe_ratio_degradation"],
                    "return_degradation": degradation["total_return_degradation"],
                    "win_rate_degradation": degradation["win_rate_degradation"],
                }

                results.append(result)

            except Exception as e:
                logger.error(
                    f"Error in period {idx}: {e}",
                    exc_info=True,
                    extra={"period": idx},
                )

        # Convert to DataFrame
        self.results = pd.DataFrame(results)

        # Summary statistics
        if len(self.results) > 0:
            logger.info("\n" + "=" * 70)
            logger.info("WALK-FORWARD ANALYSIS SUMMARY")
            logger.info("=" * 70)
            logger.info(
                f"Average out-of-sample Sharpe: {self.results['out_of_sample_sharpe'].mean():.2f}"
            )
            logger.info(
                f"Average out-of-sample return: {self.results['out_of_sample_return'].mean():.2f}%"
            )
            logger.info(
                f"Average Sharpe degradation: {self.results['sharpe_degradation'].mean():.1f}%"
            )
            logger.info(
                f"Average return degradation: {self.results['return_degradation'].mean():.1f}%"
            )
            logger.info("=" * 70)

        return self.results

    def _generate_periods(
        self,
        min_date: datetime,
        max_date: datetime,
    ) -> List[Dict[str, datetime]]:
        """
        Generate train/test period splits.

        Uses rolling window approach:
        - Period 1: Train[0:60], Test[60:90]
        - Period 2: Train[30:90], Test[90:120]
        - etc.

        Args:
            min_date: Earliest date in dataset
            max_date: Latest date in dataset

        Returns:
            List of dicts with train_start, train_end, test_start, test_end
        """
        periods = []

        # Start with first training window
        current_train_start = min_date

        while True:
            # Calculate period dates
            train_end = current_train_start + timedelta(days=self.train_window_days)
            test_start = train_end
            test_end = test_start + timedelta(days=self.test_window_days)

            # Stop if we've run out of data
            if test_end > max_date:
                break

            periods.append(
                {
                    "train_start": current_train_start,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                }
            )

            # Move forward by test window size (non-overlapping test periods)
            current_train_start = test_end

        return periods

    def _filter_data(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Filter data to date range.

        Args:
            underlying_data: Full underlying dataset
            options_data: Full options dataset
            start_date: Start date
            end_date: End date

        Returns:
            Tuple of (filtered_underlying, filtered_options)
        """
        # Handle both timestamp as column or as index for underlying_data
        if "timestamp" in underlying_data.columns:
            underlying_filtered = underlying_data[
                (underlying_data["timestamp"] >= start_date)
                & (underlying_data["timestamp"] < end_date)
            ].copy()
        else:
            # Timestamp is the index
            underlying_filtered = underlying_data[
                (underlying_data.index >= start_date) & (underlying_data.index < end_date)
            ].copy()

        options_filtered = options_data[
            (options_data["timestamp"] >= start_date) & (options_data["timestamp"] < end_date)
        ].copy()

        return underlying_filtered, options_filtered

    def _run_backtest(
        self,
        params: Dict[str, Any],
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, float]:
        """
        Run single backtest with given parameters.

        Args:
            params: Strategy parameters
            underlying_data: Underlying price data
            options_data: Options bars data
            start_date: Backtest start
            end_date: Backtest end

        Returns:
            Dict with performance metrics
        """
        # Create strategy instance
        strategy = self.strategy_class(**params)

        # Create backtest engine
        engine = OptionsBacktestEngine(initial_capital=self.initial_capital)

        # Run backtest
        results = engine.run(
            strategy=strategy,
            underlying_data=underlying_data,
            options_data=options_data,
            start_date=start_date,
            end_date=end_date,
        )

        trades = results["trades"]
        equity_curve = results["equity_curve"]

        # Calculate metrics
        if len(trades) == 0:
            return {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "num_trades": 0,
            }

        # Total return
        total_pnl = trades["pnl"].sum()
        total_return = (total_pnl / self.initial_capital) * 100

        # Win rate
        winning_trades = trades[trades["pnl"] > 0]
        win_rate = (len(winning_trades) / len(trades)) * 100 if len(trades) > 0 else 0.0

        # Sharpe ratio
        # Use portfolio_value column (not total_value)
        daily_returns = equity_curve["portfolio_value"].pct_change().dropna()
        if len(daily_returns) > 1:
            sharpe_ratio = (
                (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
                if daily_returns.std() > 0
                else 0.0
            )
        else:
            sharpe_ratio = 0.0

        # Max drawdown
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = abs(drawdown.min()) * 100

        return {
            "total_return": total_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "num_trades": len(trades),
        }

    def _calculate_degradation(
        self,
        in_sample: Dict[str, float],
        out_of_sample: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Calculate performance degradation from in-sample to out-of-sample.

        Args:
            in_sample: In-sample metrics
            out_of_sample: Out-of-sample metrics

        Returns:
            Dict with degradation percentages (positive = worse out-of-sample)
        """

        def calc_degradation(in_val: float, out_val: float) -> float:
            """Calculate percentage degradation."""
            if in_val == 0:
                return 0.0
            return ((in_val - out_val) / abs(in_val)) * 100

        return {
            "sharpe_ratio_degradation": calc_degradation(
                in_sample["sharpe_ratio"],
                out_of_sample["sharpe_ratio"],
            ),
            "total_return_degradation": calc_degradation(
                in_sample["total_return"],
                out_of_sample["total_return"],
            ),
            "win_rate_degradation": calc_degradation(
                in_sample["win_rate"],
                out_of_sample["win_rate"],
            ),
        }

    def check_robustness(
        self,
        max_sharpe_degradation: float = 50.0,
        max_return_degradation: float = 50.0,
        min_out_of_sample_sharpe: float = 1.0,
        min_out_of_sample_win_rate: float = 55.0,
    ) -> Dict[str, Any]:
        """
        Check if strategy passes robustness tests.

        Args:
            max_sharpe_degradation: Max acceptable Sharpe degradation (%)
            max_return_degradation: Max acceptable return degradation (%)
            min_out_of_sample_sharpe: Minimum acceptable out-of-sample Sharpe
            min_out_of_sample_win_rate: Minimum acceptable out-of-sample win rate (%)

        Returns:
            Dict with:
            - passed: bool
            - failures: list of failed checks
            - warnings: list of warnings
        """
        if self.results is None:
            raise ValueError("Must run walk-forward analysis first")

        failures = []
        warnings = []

        # Check average degradation
        avg_sharpe_deg = self.results["sharpe_degradation"].mean()
        avg_return_deg = self.results["return_degradation"].mean()

        if avg_sharpe_deg > max_sharpe_degradation:
            failures.append(
                f"Sharpe degradation {avg_sharpe_deg:.1f}% exceeds limit {max_sharpe_degradation}%"
            )

        if avg_return_deg > max_return_degradation:
            failures.append(
                f"Return degradation {avg_return_deg:.1f}% exceeds limit {max_return_degradation}%"
            )

        # Check out-of-sample performance
        avg_oos_sharpe = self.results["out_of_sample_sharpe"].mean()
        avg_oos_win_rate = self.results["out_of_sample_win_rate"].mean()

        if avg_oos_sharpe < min_out_of_sample_sharpe:
            failures.append(
                f"Out-of-sample Sharpe {avg_oos_sharpe:.2f} below minimum {min_out_of_sample_sharpe}"
            )

        if avg_oos_win_rate < min_out_of_sample_win_rate:
            failures.append(
                f"Out-of-sample win rate {avg_oos_win_rate:.1f}% below minimum {min_out_of_sample_win_rate}%"
            )

        # Check for any period with negative returns
        negative_periods = self.results[self.results["out_of_sample_return"] < 0]
        if len(negative_periods) > 0:
            warnings.append(
                f"{len(negative_periods)} out of {len(self.results)} periods had negative returns"
            )

        # Check parameter stability
        if len(self.results) > 1:
            # Check if optimal parameters change drastically between periods
            # (This is simplified - could be more sophisticated)
            param_changes = []
            for i in range(1, len(self.results)):
                prev_params = self.results.iloc[i - 1]["optimal_params"]
                curr_params = self.results.iloc[i]["optimal_params"]
                if prev_params != curr_params:
                    param_changes.append(i)

            if len(param_changes) == len(self.results) - 1:
                warnings.append("Parameters changed in every period - may indicate instability")

        passed = len(failures) == 0

        return {
            "passed": passed,
            "failures": failures,
            "warnings": warnings,
            "avg_sharpe_degradation": avg_sharpe_deg,
            "avg_return_degradation": avg_return_deg,
            "avg_out_of_sample_sharpe": avg_oos_sharpe,
            "avg_out_of_sample_win_rate": avg_oos_win_rate,
        }

    def save_results(self, filepath: str):
        """
        Save walk-forward results to CSV.

        Args:
            filepath: Path to save CSV file
        """
        if self.results is None:
            raise ValueError("Must run analysis first")

        # Convert optimal_params dict to string
        results_copy = self.results.copy()
        results_copy["optimal_params"] = results_copy["optimal_params"].apply(str)

        results_copy.to_csv(filepath, index=False)
        logger.info(f"Results saved to {filepath}", extra={"filepath": filepath})
