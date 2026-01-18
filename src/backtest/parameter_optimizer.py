"""Parameter optimization framework for trading strategies."""

import itertools
import pandas as pd
from typing import Any, Dict, List, Optional, Type, Callable
from datetime import datetime

from .options_engine import OptionsBacktestEngine
from quant_vibe.strategies.options_base import OptionsStrategy
from quant_vibe.logging import setup_normalized_logging
from quant_vibe.utils.timestamp_utils import now_utc

logger = setup_normalized_logging(app_name="optimization", log_dir="logs/optimization")


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
        """Initialize parameter optimizer."""
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
        """Run grid search over parameter combinations."""
        fixed_params = fixed_params or {}

        # Generate all parameter combinations
        combinations = self._generate_combinations(param_grid)
        total_combinations = len(combinations)

        logger.info(
            f"Starting grid search with {total_combinations} parameter combinations",
            extra={"num_combinations": total_combinations},
        )

        results = []
        for idx, params in enumerate(combinations, 1):
            # Add fixed parameters
            params.update(fixed_params)

            if verbose:
                self._log_progress(idx, total_combinations, params)

            # Run backtest and collect results
            result = self._evaluate_parameters(params, idx, total_combinations, verbose)
            if result:
                results.append(result)

                if progress_callback:
                    progress_callback(idx, total_combinations, params, result)

        # Convert to DataFrame and sort by Sharpe ratio
        self.results = pd.DataFrame(results)
        if not self.results.empty:
            self.results = self.results.sort_values("sharpe_ratio", ascending=False)

        return self.results

    def _generate_combinations(self, param_grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        """Generate all parameter combinations from grid."""
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(itertools.product(*param_values))
        return [dict(zip(param_names, combo)) for combo in combinations]

    def _log_progress(self, current: int, total: int, params: Dict[str, Any]) -> None:
        """Log current optimization progress."""
        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
        logger.info(
            f"[{current}/{total}] Testing: {params_str}",
            extra={"combination": current, "total": total},
        )

    def _evaluate_parameters(
        self, params: Dict[str, Any], current: int, total: int, verbose: bool
    ) -> Optional[Dict[str, Any]]:
        """Evaluate a single parameter combination."""
        try:
            start_time = now_utc()
            metrics = self._run_single_backtest(params)
            elapsed_time = (now_utc() - start_time).total_seconds()

            # Build result dictionary
            result = self._build_result_dict(params, metrics)

            if verbose:
                self._log_results(metrics, elapsed_time)

            return result

        except Exception as e:
            logger.error(
                f"Error testing parameters: {e}",
                extra={"params": params, "error": str(e)},
            )
            return None

    def _build_result_dict(
        self, params: Dict[str, Any], metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build result dictionary from parameters and metrics."""
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

        return result

    def _log_results(self, metrics: Dict[str, Any], elapsed_time: float) -> None:
        """Log backtest results."""
        logger.info(
            f"  → Sharpe: {metrics['sharpe_ratio']:.2f}, "
            f"Return: {metrics['total_return']:.2f}%, "
            f"Win Rate: {metrics['win_rate']:.2f}%, "
            f"Trades: {metrics['num_trades']}, "
            f"Time: {elapsed_time:.1f}s",
            extra=metrics,
        )

    def _run_single_backtest(self, params: Dict[str, Any]) -> Dict[str, float]:
        """Run a single backtest with given parameters."""
        # Create strategy instance with parameters
        strategy = self.strategy_class(**params)

        # Run backtest
        engine = OptionsBacktestEngine(
            initial_capital=self.initial_capital,
            log_trades=False,  # Disable logging for optimization
        )

        results = engine.run(
            strategy=strategy,
            underlying_data=self.underlying_data,
            options_data=self.options_data,
            start_date=self.start_date,
            end_date=self.end_date,
        )

        # Calculate additional metrics
        return self._calculate_metrics(results)

    def _calculate_metrics(self, results: Dict[str, Any]) -> Dict[str, float]:
        """Calculate metrics from backtest results."""
        trades_df = results.get("trades", pd.DataFrame())

        if trades_df.empty:
            return self._empty_metrics()

        total_pnl = trades_df["pnl"].sum()
        num_trades = len(trades_df)
        winning_trades = trades_df[trades_df["pnl"] > 0]
        losing_trades = trades_df[trades_df["pnl"] < 0]

        return {
            "total_return": results.get("total_return_pct", 0),
            "sharpe_ratio": results.get("sharpe_ratio", 0),
            "max_drawdown": results.get("max_drawdown", 0),
            "win_rate": results.get("win_rate", 0),
            "num_trades": num_trades,
            "profit_factor": results.get("profit_factor", 0),
            "avg_trade_pnl": total_pnl / num_trades if num_trades > 0 else 0,
            "total_pnl": total_pnl,
            "avg_win": winning_trades["pnl"].mean() if not winning_trades.empty else 0,
            "avg_loss": losing_trades["pnl"].mean() if not losing_trades.empty else 0,
        }

    def _empty_metrics(self) -> Dict[str, float]:
        """Return empty metrics when no trades were executed."""
        return {
            "total_return": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0,
            "win_rate": 0,
            "num_trades": 0,
            "profit_factor": 0,
            "avg_trade_pnl": 0,
            "total_pnl": 0,
            "avg_win": 0,
            "avg_loss": 0,
        }

    def get_best_params(self, metric: str = "sharpe_ratio", top_n: int = 5) -> pd.DataFrame:
        """Get the best parameter combinations based on a metric."""
        if self.results is None or self.results.empty:
            return pd.DataFrame()

        return self.results.nlargest(top_n, metric)

    def plot_optimization_surface(
        self,
        param_x: str,
        param_y: str,
        metric: str = "sharpe_ratio",
        save_path: Optional[str] = None,
    ) -> None:
        """Plot 3D surface of optimization results."""
        if self.results is None or self.results.empty:
            logger.warning("No results to plot")
            return

        try:
            import matplotlib.pyplot as plt
            from mpl_toolkits.mplot3d import Axes3D
            import numpy as np
        except ImportError:
            logger.error("Matplotlib required for plotting. Install with: pip install matplotlib")
            return

        # Extract data
        x_col = f"param_{param_x}"
        y_col = f"param_{param_y}"

        if x_col not in self.results.columns or y_col not in self.results.columns:
            logger.error(f"Parameters {param_x} or {param_y} not found in results")
            return

        # Create pivot table
        pivot = self.results.pivot_table(
            values=metric,
            index=y_col,
            columns=x_col,
            aggfunc="mean",
        )

        # Create 3D plot
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111, projection="3d")

        # Create mesh grid
        X, Y = np.meshgrid(pivot.columns, pivot.index)
        Z = pivot.values

        # Plot surface
        surf = ax.plot_surface(X, Y, Z, cmap="viridis", alpha=0.8)

        # Labels and title
        ax.set_xlabel(param_x)
        ax.set_ylabel(param_y)
        ax.set_zlabel(metric)
        ax.set_title(f"Optimization Surface: {metric}")

        # Add color bar
        fig.colorbar(surf, shrink=0.5, aspect=5)

        if save_path:
            plt.savefig(save_path, dpi=100, bbox_inches="tight")
            logger.info(f"Plot saved to {save_path}")
        else:
            plt.show()

    def summary_report(self) -> None:
        """Print a summary report of optimization results."""
        if self.results is None or self.results.empty:
            print("No optimization results available")
            return

        print("\n" + "=" * 70)
        print("PARAMETER OPTIMIZATION SUMMARY")
        print("=" * 70)

        # Best parameters
        best = self.results.iloc[0]
        print("\nBEST PARAMETERS:")
        for key, value in best["params"].items():
            print(f"  {key}: {value}")

        print(f"\nBEST METRICS:")
        print(f"  Sharpe Ratio: {best['sharpe_ratio']:.2f}")
        print(f"  Total Return: {best['total_return']:.2f}%")
        print(f"  Win Rate: {best['win_rate']:.2f}%")
        print(f"  Max Drawdown: {best['max_drawdown']:.2f}%")
        print(f"  Num Trades: {best['num_trades']}")
        print(f"  Profit Factor: {best['profit_factor']:.2f}")

        # Parameter sensitivity
        print("\nPARAMETER SENSITIVITY (correlation with Sharpe ratio):")
        param_cols = [col for col in self.results.columns if col.startswith("param_")]
        for col in param_cols:
            param_name = col.replace("param_", "")
            if self.results[col].dtype in ["int64", "float64"]:
                correlation = self.results[col].corr(self.results["sharpe_ratio"])
                print(f"  {param_name}: {correlation:+.3f}")

        # Distribution of results
        print("\nRESULTS DISTRIBUTION:")
        print(f"  Total combinations tested: {len(self.results)}")
        print(f"  Profitable combinations: {(self.results['total_return'] > 0).sum()}")
        print(f"  Sharpe > 1.0: {(self.results['sharpe_ratio'] > 1.0).sum()}")
        print(f"  Sharpe > 1.5: {(self.results['sharpe_ratio'] > 1.5).sum()}")
        print(f"  Sharpe > 2.0: {(self.results['sharpe_ratio'] > 2.0).sum()}")

        print("=" * 70)