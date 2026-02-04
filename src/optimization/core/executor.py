"""
Optimization execution engine.

Core logic for running parameter optimizations with backtesting.
"""

import gc
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from quant_vibe.logging import get_logger
from quant_vibe.utils import load_options_backtest_data, load_options_backtest_data_chunked, now_utc
from backtest import ParameterOptimizer

from .cache_manager import OptimizationCacheManager
from .parameter_grid import ParameterGridManager
from .progress_tracker import OptimizationProgressTracker
from .result_processor import OptimizationResultProcessor


logger = get_logger(__name__)


class OptimizationExecutor:
    """Executes optimization runs with parameter combinations."""

    def __init__(
        self,
        cache_manager: OptimizationCacheManager,
        param_grid_manager: ParameterGridManager,
        progress_tracker: OptimizationProgressTracker,
        result_processor: OptimizationResultProcessor,
        db_connection_string: str,
    ):
        """Initialize optimization executor.

        Args:
            cache_manager: Cache manager for data
            param_grid_manager: Parameter grid manager
            progress_tracker: Progress tracking
            result_processor: Result processing
            db_connection_string: Database connection for data loading
        """
        self.cache_manager = cache_manager
        self.param_grid_manager = param_grid_manager
        self.progress_tracker = progress_tracker
        self.result_processor = result_processor
        self.db_connection_string = db_connection_string

        # Track active optimizations
        self._active_optimizations = {}
        self._cancellation_flags = {}

    async def execute_optimization(
        self,
        optimization_id: str,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        train_start_date: datetime,
        train_end_date: datetime,
        test_start_date: Optional[datetime] = None,
        test_end_date: Optional[datetime] = None,
        initial_capital: float = 100000.0,
        fixed_params: Optional[Dict[str, Any]] = None,
        underlying_ticker: str = "SPX",
        timeframe: str = "5min",
        optimization_type: str = "grid_search",
        progress_callback: Optional[Callable] = None,
        result_callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Execute optimization with given parameters.

        Args:
            optimization_id: Unique optimization ID
            strategy_name: Strategy to optimize
            param_grid: Parameter grid
            train_start_date: Training period start
            train_end_date: Training period end
            test_start_date: Test period start (walk-forward)
            test_end_date: Test period end (walk-forward)
            initial_capital: Starting capital
            fixed_params: Fixed parameter overrides
            underlying_ticker: Underlying symbol
            timeframe: Data timeframe
            optimization_type: Type of optimization
            progress_callback: Async callback for progress updates
            result_callback: Async callback for each result

        Returns:
            Optimization results summary
        """
        logger.info(
            f"[Executor] Starting optimization {optimization_id}: "
            f"{strategy_name} with {self.param_grid_manager.count_permutations(param_grid)} combinations"
        )

        # Mark as active
        self._active_optimizations[optimization_id] = True
        self._cancellation_flags[optimization_id] = False

        try:
            # Extract min_dte and max_dte from fixed_params for data loading
            min_dte = fixed_params.get("min_dte", 0) if fixed_params else 0
            max_dte = fixed_params.get("max_dte", 60) if fixed_params else 60

            # Remove min_dte and max_dte from fixed_params to avoid conflict
            # These are only used for data filtering, not strategy parameters
            cleaned_fixed_params = fixed_params.copy() if fixed_params else {}
            cleaned_fixed_params.pop("min_dte", None)
            cleaned_fixed_params.pop("max_dte", None)

            # Load or cache data
            options_df, underlying_df = await self._load_data(
                underlying_ticker,
                train_start_date,
                train_end_date,
                min_dte,
                max_dte,
                timeframe,
            )

            if options_df.empty or underlying_df.empty:
                raise ValueError("No data available for the specified period")

            logger.info(
                f"[Executor] Loaded data: {len(options_df):,} options, "
                f"{len(underlying_df):,} underlying rows"
            )

            # Initialize progress tracking
            total_combinations = self.param_grid_manager.count_permutations(param_grid)
            await self.progress_tracker.initialize_progress(
                optimization_id,
                total_combinations,
                metadata={
                    "strategy_name": strategy_name,
                    "optimization_type": optimization_type,
                }
            )

            # Generate parameter combinations
            param_combinations = self.param_grid_manager.generate_combinations(param_grid)

            # Execute optimization based on type
            if optimization_type == "walk_forward" and test_start_date and test_end_date:
                results = await self._execute_walk_forward(
                    optimization_id,
                    strategy_name,
                    param_combinations,
                    options_df,
                    underlying_df,
                    train_start_date,
                    train_end_date,
                    test_start_date,
                    test_end_date,
                    initial_capital,
                    cleaned_fixed_params,
                    progress_callback,
                    result_callback,
                )
            else:
                results = await self._execute_grid_search(
                    optimization_id,
                    strategy_name,
                    param_combinations,
                    options_df,
                    underlying_df,
                    initial_capital,
                    cleaned_fixed_params,
                    progress_callback,
                    result_callback,
                )

            # Process and aggregate results
            sorted_results, summary_stats = self.result_processor.aggregate_results(
                results,
                sort_by="sharpe_ratio",
                limit=100,
            )

            # Complete progress tracking
            await self.progress_tracker.complete_progress(
                optimization_id,
                status="completed" if not self._cancellation_flags[optimization_id] else "cancelled"
            )

            logger.info(
                f"[Executor] Completed optimization {optimization_id}: "
                f"{len(results)} results"
            )

            return {
                "optimization_id": optimization_id,
                "status": "completed" if not self._cancellation_flags[optimization_id] else "cancelled",
                "total_results": len(results),
                "results": sorted_results,
                "summary": summary_stats,
            }

        except Exception as e:
            logger.error(f"[Executor] Optimization {optimization_id} failed: {e}")

            # Mark as failed
            await self.progress_tracker.complete_progress(
                optimization_id,
                status="failed",
                error_message=str(e),
            )

            raise

        finally:
            # Clean up
            self._active_optimizations.pop(optimization_id, None)
            self._cancellation_flags.pop(optimization_id, None)

    async def _load_data(
        self,
        underlying_ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int,
        max_dte: int,
        timeframe: str,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load or retrieve cached data.

        Args:
            underlying_ticker: Underlying symbol
            start_date: Start date
            end_date: End date
            min_dte: Minimum DTE
            max_dte: Maximum DTE
            timeframe: Data timeframe

        Returns:
            Tuple of (options_df, underlying_df)
        """
        # Try cache first
        cached_data = await self.cache_manager.get_cached_data(
            underlying_ticker,
            start_date,
            end_date,
            min_dte,
            max_dte,
            timeframe,
        )

        if cached_data:
            return cached_data

        # Load fresh data
        logger.info("[Executor] Loading fresh data from database...")
        logger.debug(f" underlying_ticker={underlying_ticker}, start_date={start_date}, end_date={end_date}, min_dte={min_dte}, max_dte={max_dte}, timeframe={timeframe}")

        # Validate date range - don't query future dates
        from datetime import datetime
        today = datetime.now().date()
        if end_date.date() > today:
            logger.warning(f"[Executor] End date {end_date.date()} is in the future, adjusting to today {today}")
            end_date = datetime.combine(today, datetime.min.time())

        # Ensure we have at least 1 day of data
        if start_date >= end_date:
            raise ValueError(f"Invalid date range: start_date {start_date} >= end_date {end_date}")

        # Note: load_options_backtest_data uses db_profile (not connection string)
        # It defaults to using environment variables for database connection
        try:
            import asyncio
            loop = asyncio.get_event_loop()

            # Calculate date range to decide on loading strategy
            date_range_days = (end_date - start_date).days

            # Always use chunked loading to avoid query timeouts and OOM
            # Recent expiration weeks can have 1M+ rows per day
            if date_range_days > 1:
                logger.info(f"[Executor] Using chunked loading for {date_range_days} day range...")
                options_df, underlying_df = await loop.run_in_executor(
                    None,
                    load_options_backtest_data_chunked,
                    underlying_ticker,
                    start_date,
                    end_date,
                    min_dte,
                    max_dte,
                    True,   # verbose
                    None,   # db_profile
                    timeframe,
                    1,      # chunk_days (1-day to avoid OOM on high-volume periods)
                )
            else:
                # Add timeout using asyncio (60 seconds for smaller ranges)
                options_df, underlying_df = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        load_options_backtest_data,
                        underlying_ticker,
                        start_date,
                        end_date,
                        min_dte,
                        max_dte,
                        False,  # verbose
                        None,   # db_profile
                        timeframe
                    ),
                    timeout=60.0  # 60 second timeout for smaller ranges
                )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Database query timed out. Try using a shorter date range or chunked loading.")
        except Exception as e:
            logger.error(f"[Executor] Error loading data: {e}")
            raise

        # Cache for next time
        cache_key = self.cache_manager.generate_cache_key(
            underlying_ticker,
            start_date,
            end_date,
            min_dte,
            max_dte,
            timeframe,
        )

        await self.cache_manager.store_cached_data(
            cache_key,
            options_df,
            underlying_df,
            metadata={
                "underlying_ticker": underlying_ticker,
                "start_date": start_date,
                "end_date": end_date,
                "timeframe": timeframe,
            }
        )

        return options_df, underlying_df

    async def _execute_grid_search(
        self,
        optimization_id: str,
        strategy_name: str,
        param_combinations: List[Dict[str, Any]],
        options_df: pd.DataFrame,
        underlying_df: pd.DataFrame,
        initial_capital: float,
        fixed_params: Optional[Dict[str, Any]],
        progress_callback: Optional[Callable],
        result_callback: Optional[Callable],
    ) -> List[Dict[str, Any]]:
        """Execute grid search optimization.

        Args:
            optimization_id: Optimization ID
            strategy_name: Strategy name
            param_combinations: List of parameter combinations
            options_df: Options data
            underlying_df: Underlying data
            initial_capital: Starting capital
            fixed_params: Fixed parameters
            progress_callback: Progress callback
            result_callback: Result callback

        Returns:
            List of optimization results
        """
        results = []

        # Create parameter optimizer
        optimizer = ParameterOptimizer(
            options_data=options_df,
            underlying_data=underlying_df,
            initial_capital=initial_capital,
        )

        # Create progress wrapper
        async def wrapped_progress_callback(current: int, total: int, params: Dict, metrics: Dict):
            # Update progress tracker
            await self.progress_tracker.update_progress(
                optimization_id,
                current,
                total,
                params,
                metrics,
            )

            # Call user callback if provided
            if progress_callback:
                await progress_callback(current, total, params, metrics)

        # Run optimization
        for i, params in enumerate(param_combinations, 1):
            # Check cancellation
            if self._cancellation_flags.get(optimization_id, False):
                logger.info(f"[Executor] Optimization {optimization_id} cancelled")
                break

            # Merge with fixed params
            complete_params = self.param_grid_manager.merge_with_fixed_params(
                strategy_name,
                params,
                fixed_params,
            )

            try:
                # Run backtest
                metrics = optimizer.run_single_backtest(
                    strategy_name,
                    complete_params,
                )

                # Process result
                result = self.result_processor.process_backtest_result(
                    params,
                    metrics,
                )

                results.append(result)

                # Update progress
                await wrapped_progress_callback(i, len(param_combinations), params, metrics)

                # Call result callback if provided
                if result_callback:
                    await result_callback(result)

            except Exception as e:
                logger.error(
                    f"[Executor] Error in combination {i}/{len(param_combinations)}: {e}"
                )
                # Continue with next combination

        return results

    async def _execute_walk_forward(
        self,
        optimization_id: str,
        strategy_name: str,
        param_combinations: List[Dict[str, Any]],
        options_df: pd.DataFrame,
        underlying_df: pd.DataFrame,
        train_start_date: datetime,
        train_end_date: datetime,
        test_start_date: datetime,
        test_end_date: datetime,
        initial_capital: float,
        fixed_params: Optional[Dict[str, Any]],
        progress_callback: Optional[Callable],
        result_callback: Optional[Callable],
    ) -> List[Dict[str, Any]]:
        """Execute walk-forward optimization.

        Args:
            optimization_id: Optimization ID
            strategy_name: Strategy name
            param_combinations: List of parameter combinations
            options_df: Options data
            underlying_df: Underlying data
            train_start_date: Training start
            train_end_date: Training end
            test_start_date: Test start
            test_end_date: Test end
            initial_capital: Starting capital
            fixed_params: Fixed parameters
            progress_callback: Progress callback
            result_callback: Result callback

        Returns:
            List of optimization results with test performance
        """
        results = []

        # Split data into train and test
        train_options = options_df[
            (options_df.index >= train_start_date) &
            (options_df.index <= train_end_date)
        ]
        train_underlying = underlying_df[
            (underlying_df.index >= train_start_date) &
            (underlying_df.index <= train_end_date)
        ]

        test_options = options_df[
            (options_df.index >= test_start_date) &
            (options_df.index <= test_end_date)
        ]
        test_underlying = underlying_df[
            (underlying_df.index >= test_start_date) &
            (underlying_df.index <= test_end_date)
        ]

        # Create optimizers for train and test
        train_optimizer = ParameterOptimizer(
            options_data=train_options,
            underlying_data=train_underlying,
            initial_capital=initial_capital,
        )

        test_optimizer = ParameterOptimizer(
            options_data=test_options,
            underlying_data=test_underlying,
            initial_capital=initial_capital,
        )

        # Run walk-forward
        for i, params in enumerate(param_combinations, 1):
            # Check cancellation
            if self._cancellation_flags.get(optimization_id, False):
                break

            # Merge with fixed params
            complete_params = self.param_grid_manager.merge_with_fixed_params(
                strategy_name,
                params,
                fixed_params,
            )

            try:
                # Run training backtest
                train_metrics = train_optimizer.run_single_backtest(
                    strategy_name,
                    complete_params,
                )

                # Run test backtest
                test_metrics = test_optimizer.run_single_backtest(
                    strategy_name,
                    complete_params,
                )

                # Combine results
                result = {
                    **params,
                    **{f"train_{k}": v for k, v in train_metrics.items()},
                    **{f"test_{k}": v for k, v in test_metrics.items()},
                    "timestamp": now_utc().isoformat(),
                }

                results.append(result)

                # Update progress
                await self.progress_tracker.update_progress(
                    optimization_id,
                    i,
                    len(param_combinations),
                    params,
                    {"train_sharpe": train_metrics.get("sharpe_ratio", 0),
                     "test_sharpe": test_metrics.get("sharpe_ratio", 0)},
                )

                # Call result callback
                if result_callback:
                    await result_callback(result)

            except Exception as e:
                logger.error(f"[Executor] Error in walk-forward combination {i}: {e}")

        return results

    def cancel_optimization(self, optimization_id: str) -> bool:
        """Cancel a running optimization.

        Args:
            optimization_id: Optimization ID

        Returns:
            True if cancellation requested, False if not found
        """
        if optimization_id in self._active_optimizations:
            self._cancellation_flags[optimization_id] = True
            logger.info(f"[Executor] Cancellation requested for {optimization_id}")
            return True

        return False

    def is_active(self, optimization_id: str) -> bool:
        """Check if optimization is active.

        Args:
            optimization_id: Optimization ID

        Returns:
            True if active
        """
        return optimization_id in self._active_optimizations

    def get_active_optimizations(self) -> List[str]:
        """Get list of active optimization IDs.

        Returns:
            List of active optimization IDs
        """
        return list(self._active_optimizations.keys())