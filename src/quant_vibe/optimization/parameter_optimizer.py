"""Parameter optimization framework for trading strategies.

This module provides tools to:
1. Run grid search over parameter combinations
2. Evaluate performance metrics (Sharpe ratio, win rate, max drawdown, etc.)
3. Find optimal parameters based on specified metrics
4. Avoid overfitting through out-of-sample validation
"""

import itertools
import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional, Type, Callable
from datetime import datetime
import logging

from quant_vibe.backtesting.options_engine import OptionsBacktestEngine
from quant_vibe.strategies.options_base import OptionsStrategy
from quant_vibe.config.logging_config import setup_normalized_logging
from quant_vibe.utils.timestamp_utils import now_utc

logger = setup_normalized_logging("optimization", "INFO", "logs/optimization")


class ParameterOptimizer:
    """Optimize strategy parameters using grid search."""

    def __init__(
        self,
        strategy_class: Type[OptionsStrategy],
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        initial_capital: float = 100000.0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ):
        """
        Initialize parameter optimizer.

        Args:
            strategy_class: Strategy class to optimize (not instance)
            underlying_data: DataFrame with underlying price data
            options_data: DataFrame with options bars data
            initial_capital: Initial capital for backtests
            start_date: Backtest start date
            end_date: Backtest end date
        """
        self.strategy_class = strategy_class
        self.underlying_data = underlying_data
        self.options_data = options_data
        self.initial_capital = initial_capital
        self.start_date = start_date
        self.end_date = end_date
        self.results: Optional[pd.DataFrame] = None

    def grid_search(
        self,
        param_grid: Dict[str, List[Any]],
        fixed_params: Optional[Dict[str, Any]] = None,
        verbose: bool = True,
        progress_callback: Optional[Callable[[int, int, Dict[str, Any], Dict[str, float]], None]] = None,
    ) -> pd.DataFrame:
        """
        Run grid search over parameter combinations.

        Args:
            param_grid: Dict of parameter names to lists of values to try.
                       Example: {
                           'spread_width': [5, 10, 15, 20],
                           'profit_target_min': [0.30, 0.40, 0.50, 0.60],
                           'stop_loss_pct': [0.50, 0.75, 1.00]
                       }
            fixed_params: Dict of fixed parameters to pass to every strategy instance
            verbose: Whether to print progress
            progress_callback: Optional callback function called after each combination.
                             Signature: callback(current: int, total: int, params: dict, metrics: dict)

        Returns:
            DataFrame with columns:
            - params: dict of parameter combination
            - total_return: float (%)
            - sharpe_ratio: float
            - max_drawdown: float (%)
            - win_rate: float (%)
            - num_trades: int
            - profit_factor: float
            - avg_trade_pnl: float
            - total_pnl: float
        """
        fixed_params = fixed_params or {}

        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))

        total_combinations = len(combinations)
        logger.info(
            f"Starting grid search with {total_combinations} parameter combinations",
            extra={"num_combinations": total_combinations},
        )

        results = []

        for idx, combo in enumerate(combinations, 1):
            # Create parameter dict for this combination
            params = dict(zip(param_names, combo))
            params.update(fixed_params)

            if verbose:
                params_str = ", ".join(f"{k}={v}" for k, v in params.items())
                logger.info(
                    f"[{idx}/{total_combinations}] Testing: {params_str}",
                    extra={"combination": idx, "total": total_combinations},
                )

            try:
                # Run backtest with this parameter set
                start_time = now_utc()
                metrics = self._run_single_backtest(params)
                elapsed_time = (now_utc() - start_time).total_seconds()

                # Store results
                result = {
                    "params": params.copy(),
                    "total_return": metrics["total_return"],
                    "sharpe_ratio": metrics["sharpe_ratio"],
                    "max_drawdown": metrics["max_drawdown"],
                    "win_rate": metrics["win_rate"],
                    "num_trades": metrics["num_trades"],
                    "profit_factor": metrics["profit_factor"],
                    "avg_trade_pnl": metrics["avg_trade_pnl"],
                    "total_pnl": metrics["total_pnl"],
                }

                # Add individual param columns for easier filtering
                for param_name, param_value in params.items():
                    result[f"param_{param_name}"] = param_value

                results.append(result)

                if verbose:
                    logger.info(
                        f"  → Sharpe: {metrics['sharpe_ratio']:.2f}, "
                        f"Return: {metrics['total_return']:.2f}%, "
                        f"Win Rate: {metrics['win_rate']:.2f}%, "
                        f"Trades: {metrics['num_trades']}, "
                        f"Time: {elapsed_time:.1f}s",
                        extra={
                            "sharpe": metrics["sharpe_ratio"],
                            "return": metrics["total_return"],
                            "win_rate": metrics["win_rate"],
                            "trades": metrics["num_trades"],
                            "elapsed_time": elapsed_time,
                        },
                    )

                # Call progress callback if provided
                if progress_callback:
                    try:
                        progress_callback(idx, total_combinations, params, metrics)
                    except Exception as cb_error:
                        logger.warning(f"Progress callback error: {cb_error}")

            except Exception as e:
                logger.error(
                    f"Error testing parameters {params}: {e}",
                    exc_info=True,
                    extra={"params": params},
                )
                # Store failed result with NaN metrics
                result = {
                    "params": params.copy(),
                    "total_return": np.nan,
                    "sharpe_ratio": np.nan,
                    "max_drawdown": np.nan,
                    "win_rate": np.nan,
                    "num_trades": 0,
                    "profit_factor": np.nan,
                    "avg_trade_pnl": np.nan,
                    "total_pnl": np.nan,
                }
                for param_name, param_value in params.items():
                    result[f"param_{param_name}"] = param_value
                results.append(result)

                # Call progress callback even for failures
                if progress_callback:
                    try:
                        progress_callback(idx, total_combinations, params, {
                            "sharpe_ratio": 0.0,
                            "total_return": 0.0,
                            "win_rate": 0.0,
                            "num_trades": 0,
                            "error": str(e),
                        })
                    except Exception as cb_error:
                        logger.warning(f"Progress callback error: {cb_error}")

        # Convert to DataFrame
        self.results = pd.DataFrame(results)

        # Sort by Sharpe ratio (descending)
        self.results = self.results.sort_values("sharpe_ratio", ascending=False)

        logger.info(
            f"Grid search complete. Best Sharpe ratio: {self.results.iloc[0]['sharpe_ratio']:.2f}",
            extra={"best_sharpe": float(self.results.iloc[0]["sharpe_ratio"])},
        )

        return self.results

    def _run_single_backtest(self, params: Dict[str, Any]) -> Dict[str, float]:
        """
        Run a single backtest with given parameters.

        Args:
            params: Dictionary of strategy parameters

        Returns:
            Dict with performance metrics
        """
        # Create strategy instance with parameters
        strategy = self.strategy_class(**params)

        # Create backtest engine
        engine = OptionsBacktestEngine(initial_capital=self.initial_capital)

        # Run backtest
        results = engine.run(
            strategy=strategy,
            underlying_data=self.underlying_data,
            options_data=self.options_data,
            start_date=self.start_date,
            end_date=self.end_date,
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
                "profit_factor": 0.0,
                "avg_trade_pnl": 0.0,
                "total_pnl": 0.0,
            }

        # Total P&L and return
        total_pnl = trades["pnl"].sum()
        total_return = (total_pnl / self.initial_capital) * 100

        # Win rate
        winning_trades = trades[trades["pnl"] > 0]
        win_rate = (len(winning_trades) / len(trades)) * 100 if len(trades) > 0 else 0.0

        # Profit factor
        gross_profit = winning_trades["pnl"].sum() if len(winning_trades) > 0 else 0.0
        losing_trades = trades[trades["pnl"] <= 0]
        gross_loss = abs(losing_trades["pnl"].sum()) if len(losing_trades) > 0 else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf

        # Sharpe ratio (annualized)
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

        # Average trade P&L
        avg_trade_pnl = trades["pnl"].mean()

        return {
            "total_return": total_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "num_trades": len(trades),
            "profit_factor": profit_factor if not np.isinf(profit_factor) else 999.0,
            "avg_trade_pnl": avg_trade_pnl,
            "total_pnl": total_pnl,
        }

    def find_optimal(
        self,
        metric: str = "sharpe_ratio",
        min_trades: int = 10,
    ) -> Dict[str, Any]:
        """
        Return best parameter set by specified metric.

        Args:
            metric: Metric to optimize ('sharpe_ratio', 'total_return', 'win_rate', etc.)
            min_trades: Minimum number of trades required for valid result

        Returns:
            Dict with 'params' and metric values
        """
        if self.results is None:
            raise ValueError("Must run grid_search() first")

        # Filter by minimum trades
        valid_results = self.results[self.results["num_trades"] >= min_trades]

        if len(valid_results) == 0:
            logger.warning(
                f"No parameter combinations with >= {min_trades} trades",
                extra={"min_trades": min_trades},
            )
            # Fall back to all results
            valid_results = self.results

        # Sort by metric (descending for most metrics)
        ascending = metric == "max_drawdown"  # Lower is better for drawdown
        best_row = valid_results.sort_values(metric, ascending=ascending).iloc[0]

        result = {
            "params": best_row["params"],
            metric: best_row[metric],
            "total_return": best_row["total_return"],
            "sharpe_ratio": best_row["sharpe_ratio"],
            "max_drawdown": best_row["max_drawdown"],
            "win_rate": best_row["win_rate"],
            "num_trades": best_row["num_trades"],
        }

        logger.info(
            f"Optimal parameters (by {metric}): {best_row['params']}",
            extra={"metric": metric, "params": best_row["params"]},
        )

        return result

    def get_top_n(
        self,
        n: int = 10,
        metric: str = "sharpe_ratio",
        min_trades: int = 10,
    ) -> pd.DataFrame:
        """
        Get top N parameter combinations by specified metric.

        Args:
            n: Number of top results to return
            metric: Metric to sort by
            min_trades: Minimum number of trades required

        Returns:
            DataFrame with top N results
        """
        if self.results is None:
            raise ValueError("Must run grid_search() first")

        # Filter by minimum trades
        valid_results = self.results[self.results["num_trades"] >= min_trades]

        # Sort by metric
        ascending = metric == "max_drawdown"
        top_n = valid_results.sort_values(metric, ascending=ascending).head(n)

        return top_n

    def save_results(self, filepath: str):
        """
        Save optimization results to CSV.

        Args:
            filepath: Path to save CSV file
        """
        if self.results is None:
            raise ValueError("Must run grid_search() first")

        # Convert params dict to string for CSV
        results_copy = self.results.copy()
        results_copy["params"] = results_copy["params"].apply(str)

        results_copy.to_csv(filepath, index=False)
        logger.info(f"Results saved to {filepath}", extra={"filepath": filepath})

    def create_heatmap_data(
        self,
        param_x: str,
        param_y: str,
        metric: str = "sharpe_ratio",
    ) -> pd.DataFrame:
        """
        Create pivot table for heatmap visualization.

        Args:
            param_x: Parameter name for x-axis
            param_y: Parameter name for y-axis
            metric: Metric to display in heatmap

        Returns:
            Pivot table with param_x as columns, param_y as index
        """
        if self.results is None:
            raise ValueError("Must run grid_search() first")

        # Create pivot table
        pivot = self.results.pivot_table(
            index=f"param_{param_y}",
            columns=f"param_{param_x}",
            values=metric,
            aggfunc="mean",
        )

        return pivot
