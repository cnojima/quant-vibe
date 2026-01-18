"""Walk-forward analysis for strategy validation and robustness testing."""

import pandas as pd
from typing import Any, Dict, List, Optional, Type
from datetime import datetime, timedelta

from .options_engine import OptionsBacktestEngine
from .parameter_optimizer import ParameterOptimizer
from quant_vibe.strategies.options_base import OptionsStrategy
from quant_vibe.logging import setup_normalized_logging

logger = setup_normalized_logging(app_name="walk_forward", log_dir="logs/optimization")


class WalkForwardAnalysis:
    """Perform walk-forward analysis on trading strategies."""

    def __init__(
        self,
        strategy_class: Type[OptionsStrategy],
        train_window_days: int = 60,
        test_window_days: int = 30,
        initial_capital: float = 100000.0,
    ):
        """Initialize walk-forward analyzer."""
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
        """Run walk-forward optimization."""
        fixed_params = fixed_params or {}

        # Get date range from data
        min_date, max_date = self._extract_date_range(underlying_data)

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
        self._validate_periods(periods)

        logger.info(
            f"Generated {len(periods)} walk-forward periods",
            extra={"num_periods": len(periods)},
        )

        # Run analysis for each period
        results = []
        for idx, period in enumerate(periods, 1):
            if verbose:
                self._log_period(idx, len(periods), period)

            result = self._analyze_period(
                period,
                underlying_data,
                options_data,
                param_grid,
                fixed_params,
                optimization_metric,
                min_train_trades,
                verbose,
            )

            if result:
                results.append(result)

        # Create results DataFrame
        self.results = pd.DataFrame(results)
        return self.results

    def _extract_date_range(self, data: pd.DataFrame) -> tuple[datetime, datetime]:
        """Extract min and max dates from data."""
        if "timestamp" in data.columns:
            data = data.sort_values("timestamp")
            return data["timestamp"].min(), data["timestamp"].max()

        # Timestamp is the index
        data = data.sort_index()
        return data.index.min(), data.index.max()

    def _validate_periods(self, periods: List[Dict[str, datetime]]) -> None:
        """Validate that we have enough periods for analysis."""
        if len(periods) == 0:
            raise ValueError(
                f"Not enough data for walk-forward analysis. "
                f"Need at least {self.train_window_days + self.test_window_days} days."
            )

    def _log_period(self, current: int, total: int, period: Dict[str, datetime]) -> None:
        """Log current period being analyzed."""
        logger.info(
            f"\n[Period {current}/{total}] "
            f"Train: {period['train_start'].date()} to {period['train_end'].date()}, "
            f"Test: {period['test_start'].date()} to {period['test_end'].date()}",
            extra={
                "period": current,
                "total_periods": total,
                "train_start": str(period["train_start"].date()),
                "train_end": str(period["train_end"].date()),
                "test_start": str(period["test_start"].date()),
                "test_end": str(period["test_end"].date()),
            },
        )

    def _analyze_period(
        self,
        period: Dict[str, datetime],
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        fixed_params: Dict[str, Any],
        optimization_metric: str,
        min_train_trades: int,
        verbose: bool,
    ) -> Optional[Dict[str, Any]]:
        """Analyze a single walk-forward period."""
        try:
            # Split data
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
            optimal_params, train_metrics = self._optimize_on_training(
                train_underlying,
                train_options,
                param_grid,
                fixed_params,
                optimization_metric,
                period["train_start"],
                period["train_end"],
                verbose,
            )

            # Skip if insufficient training trades
            if train_metrics.get("total_trades", 0) < min_train_trades:
                logger.warning(
                    f"Skipping period - only {train_metrics.get('total_trades', 0)} trades in training",
                    extra={"period": period, "min_trades": min_train_trades},
                )
                return None

            # Test on out-of-sample data
            test_metrics = self._test_on_out_of_sample(
                test_underlying,
                test_options,
                optimal_params,
                period["test_start"],
                period["test_end"],
                verbose,
            )

            # Calculate degradation
            degradation = self._calculate_degradation(train_metrics, test_metrics)

            # Build result
            return {
                "period": len(self.results) + 1 if self.results is not None else 1,
                "train_start": period["train_start"],
                "train_end": period["train_end"],
                "test_start": period["test_start"],
                "test_end": period["test_end"],
                "optimal_params": optimal_params,
                **{f"in_sample_{k}": v for k, v in train_metrics.items()},
                **{f"out_of_sample_{k}": v for k, v in test_metrics.items()},
                **{f"degradation_{k}": v for k, v in degradation.items()},
            }

        except Exception as e:
            logger.error(f"Error analyzing period: {e}", extra={"period": period, "error": str(e)})
            return None

    def _filter_data(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Filter data to specific date range."""
        # Filter underlying data
        if "timestamp" in underlying_data.columns:
            mask = (underlying_data["timestamp"] >= start_date) & (underlying_data["timestamp"] <= end_date)
            filtered_underlying = underlying_data[mask].copy()
        else:
            filtered_underlying = underlying_data[start_date:end_date].copy()

        # Filter options data
        mask = (options_data["timestamp"] >= start_date) & (options_data["timestamp"] <= end_date)
        filtered_options = options_data[mask].copy()

        return filtered_underlying, filtered_options

    def _optimize_on_training(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        param_grid: Dict[str, List[Any]],
        fixed_params: Dict[str, Any],
        optimization_metric: str,
        start_date: datetime,
        end_date: datetime,
        verbose: bool,
    ) -> tuple[Dict[str, Any], Dict[str, float]]:
        """Optimize parameters on training data."""
        optimizer = ParameterOptimizer(
            strategy_class=self.strategy_class,
            underlying_data=underlying_data,
            options_data=options_data,
            initial_capital=self.initial_capital,
            start_date=start_date,
            end_date=end_date,
        )

        # Run grid search
        results = optimizer.grid_search(
            param_grid=param_grid,
            fixed_params=fixed_params,
            verbose=False,  # Suppress individual backtest logging
        )

        if results.empty:
            return {}, {}

        # Get best parameters
        best = results.nlargest(1, optimization_metric).iloc[0]
        optimal_params = best["params"]

        # Extract metrics
        metrics = {
            "sharpe_ratio": best["sharpe_ratio"],
            "total_return": best["total_return"],
            "win_rate": best["win_rate"],
            "max_drawdown": best["max_drawdown"],
            "total_trades": best["total_trades"],
            "profit_factor": best["profit_factor"],
        }

        if verbose:
            logger.info(
                f"  Training: Sharpe={metrics['sharpe_ratio']:.2f}, "
                f"Return={metrics['total_return']:.2f}%, "
                f"Trades={metrics['total_trades']}",
                extra={"phase": "training", **metrics},
            )

        return optimal_params, metrics

    def _test_on_out_of_sample(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        params: Dict[str, Any],
        start_date: datetime,
        end_date: datetime,
        verbose: bool,
    ) -> Dict[str, float]:
        """Test parameters on out-of-sample data."""
        # Create strategy with optimal parameters
        strategy = self.strategy_class(**params)

        # Run backtest
        engine = OptionsBacktestEngine(
            initial_capital=self.initial_capital,
            log_trades=False,
        )

        results = engine.run(
            strategy=strategy,
            underlying_data=underlying_data,
            options_data=options_data,
            start_date=start_date,
            end_date=end_date,
        )

        # Extract metrics
        metrics = {
            "sharpe_ratio": results.get("sharpe_ratio", 0),
            "total_return": results.get("total_return_pct", 0),
            "win_rate": results.get("win_rate", 0),
            "max_drawdown": results.get("max_drawdown", 0),
            "total_trades": results.get("total_trades", 0),
            "profit_factor": results.get("profit_factor", 0),
        }

        if verbose:
            logger.info(
                f"  Testing:  Sharpe={metrics['sharpe_ratio']:.2f}, "
                f"Return={metrics['total_return']:.2f}%, "
                f"Trades={metrics['total_trades']}",
                extra={"phase": "testing", **metrics},
            )

        return metrics

    def _calculate_degradation(
        self, train_metrics: Dict[str, float], test_metrics: Dict[str, float]
    ) -> Dict[str, float]:
        """Calculate performance degradation from in-sample to out-of-sample."""
        degradation = {}

        for metric in ["sharpe_ratio", "total_return", "win_rate"]:
            train_val = train_metrics.get(metric, 0)
            test_val = test_metrics.get(metric, 0)

            if train_val != 0:
                degradation[metric] = ((test_val - train_val) / abs(train_val)) * 100
            else:
                degradation[metric] = 0 if test_val == 0 else -100 if test_val < 0 else 100

        return degradation

    def _generate_periods(self, min_date: datetime, max_date: datetime) -> List[Dict[str, datetime]]:
        """Generate train/test period splits."""
        periods = []
        current_date = min_date

        while current_date + timedelta(days=self.train_window_days + self.test_window_days) <= max_date:
            period = {
                "train_start": current_date,
                "train_end": current_date + timedelta(days=self.train_window_days - 1),
                "test_start": current_date + timedelta(days=self.train_window_days),
                "test_end": current_date + timedelta(days=self.train_window_days + self.test_window_days - 1),
            }
            periods.append(period)

            # Move forward by test window size
            current_date += timedelta(days=self.test_window_days)

        return periods

    def summary_report(self) -> None:
        """Print summary report of walk-forward results."""
        if self.results is None or self.results.empty:
            print("No walk-forward results available")
            return

        print("\n" + "=" * 70)
        print("WALK-FORWARD ANALYSIS SUMMARY")
        print("=" * 70)

        # Overall statistics
        print(f"\nPERIODS ANALYZED: {len(self.results)}")
        print(f"Train Window: {self.train_window_days} days")
        print(f"Test Window: {self.test_window_days} days")

        # Average performance
        print("\nAVERAGE PERFORMANCE:")
        metrics = ["sharpe_ratio", "total_return", "win_rate", "total_trades"]

        for metric in metrics:
            in_sample = self.results[f"in_sample_{metric}"].mean()
            out_sample = self.results[f"out_of_sample_{metric}"].mean()
            degradation = self.results[f"degradation_{metric}"].mean()

            print(f"\n{metric.replace('_', ' ').title()}:")
            print(f"  In-Sample:     {in_sample:.2f}")
            print(f"  Out-of-Sample: {out_sample:.2f}")
            print(f"  Degradation:   {degradation:+.2f}%")

        # Consistency analysis
        print("\nCONSISTENCY ANALYSIS:")
        profitable_periods = (self.results["out_of_sample_total_return"] > 0).sum()
        consistent_periods = (
            (self.results["in_sample_total_return"] > 0) &
            (self.results["out_of_sample_total_return"] > 0)
        ).sum()

        print(f"  Profitable out-of-sample periods: {profitable_periods}/{len(self.results)}")
        print(f"  Consistently profitable periods:  {consistent_periods}/{len(self.results)}")

        # Overfitting detection
        avg_degradation = self.results["degradation_sharpe_ratio"].mean()
        if avg_degradation < -50:
            print("\n⚠️  WARNING: Significant overfitting detected (>50% Sharpe degradation)")
        elif avg_degradation < -30:
            print("\n⚠️  CAUTION: Moderate overfitting detected (>30% Sharpe degradation)")
        else:
            print("\n✅ Strategy shows reasonable out-of-sample performance")

        print("=" * 70)