"""
Refactored Optimization Service - Orchestration layer.

This service orchestrates the optimization lifecycle using
modular components for better maintainability and testability.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from quant_vibe.logging import get_logger

from .core.cache_manager import OptimizationCacheManager
from .core.parameter_grid import ParameterGridManager
from .core.progress_tracker import OptimizationProgressTracker
from .core.result_processor import OptimizationResultProcessor
from .core.executor import OptimizationExecutor
from .storage.repository import OptimizationRepository
from .resilience.circuit_breaker import CircuitBreakerManager
from .resilience.retry_policy import get_database_retry_policy
from .resilience.health_check import (
    HealthCheckManager,
    RedisHealthCheck,
    DatabaseHealthCheck,
    SystemHealthCheck,
    OptimizationHealthCheck,
)


logger = get_logger(__name__)


class OptimizationService:
    """Refactored optimization service using modular components."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db_connection_string: str,
        data_cache_ttl: int = 3600,
        results_base_dir: str = "results/optimization",
    ):
        """Initialize optimization service with dependency injection.

        Args:
            redis_client: Async Redis client for caching and pub/sub
            db_connection_string: PostgreSQL connection string
            data_cache_ttl: Data cache TTL in seconds (default: 1 hour)
            results_base_dir: Base directory for CSV results
        """
        # Initialize components
        self.cache_manager = OptimizationCacheManager(
            redis_client=redis_client,
            db_connection_string=db_connection_string,
            data_cache_ttl=data_cache_ttl,
        )

        self.param_grid_manager = ParameterGridManager()

        self.progress_tracker = OptimizationProgressTracker(redis_client)

        self.result_processor = OptimizationResultProcessor(results_base_dir)

        self.repository = OptimizationRepository(db_connection_string)

        self.executor = OptimizationExecutor(
            cache_manager=self.cache_manager,
            param_grid_manager=self.param_grid_manager,
            progress_tracker=self.progress_tracker,
            result_processor=self.result_processor,
            db_connection_string=db_connection_string,
        )

        # Initialize resilience components
        self.circuit_breaker_manager = CircuitBreakerManager()
        self.retry_policy = get_database_retry_policy()

        # Initialize health checks
        self.health_check_manager = HealthCheckManager()
        self.health_check_manager.add_check(RedisHealthCheck(redis_client))
        self.health_check_manager.add_check(DatabaseHealthCheck(db_connection_string))
        self.health_check_manager.add_check(SystemHealthCheck())
        self.health_check_manager.add_check(
            OptimizationHealthCheck(self.executor, self.repository)
        )

        # Track running tasks
        self._running_tasks = {}

        logger.info("[Service] Optimization service initialized with modular components")

    # ============================================================================
    # Parameter Grid Management
    # ============================================================================

    def generate_param_grid(
        self,
        strategy_name: str,
        custom_ranges: Optional[Dict[str, List[Any]]] = None,
        optimize_only: Optional[List[str]] = None,
    ) -> Dict[str, List[Any]]:
        """Generate parameter grid for optimization.

        Args:
            strategy_name: Name of strategy
            custom_ranges: Custom parameter ranges
            optimize_only: List of parameters to optimize

        Returns:
            Parameter grid dictionary
        """
        return self.param_grid_manager.generate_param_grid(
            strategy_name=strategy_name,
            custom_ranges=custom_ranges,
            optimize_only=optimize_only,
        )

    def get_fixed_params(self, strategy_name: str) -> Dict[str, Any]:
        """Get fixed parameters for a strategy.

        Args:
            strategy_name: Name of strategy

        Returns:
            Fixed parameters dictionary
        """
        return self.param_grid_manager.get_fixed_params(strategy_name)

    def count_permutations(self, param_grid: Dict[str, List[Any]]) -> int:
        """Count total parameter combinations.

        Args:
            param_grid: Parameter grid

        Returns:
            Number of combinations
        """
        return self.param_grid_manager.count_permutations(param_grid)

    def validate_param_grid(
        self,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        max_combinations: int = 10000,
    ) -> Dict[str, Any]:
        """Validate parameter grid.

        Args:
            strategy_name: Strategy name
            param_grid: Parameter grid to validate
            max_combinations: Maximum allowed combinations

        Returns:
            Validation result dictionary
        """
        return self.param_grid_manager.validate_param_grid(
            strategy_name=strategy_name,
            param_grid=param_grid,
            max_combinations=max_combinations,
        )

    # ============================================================================
    # Cache Management
    # ============================================================================

    async def clear_cache(self, cache_key: Optional[str] = None) -> int:
        """Clear optimization cache.

        Args:
            cache_key: Specific cache key or None for all

        Returns:
            Number of keys cleared
        """
        return await self.cache_manager.clear_cache(cache_key)

    # ============================================================================
    # Optimization Execution
    # ============================================================================

    async def create_optimization(
        self,
        strategy_name: str,
        train_start_date: datetime,
        train_end_date: datetime,
        param_grid: Dict[str, List[Any]],
        optimization_type: str = "grid_search",
        test_start_date: Optional[datetime] = None,
        test_end_date: Optional[datetime] = None,
        initial_capital: float = 100000.0,
        fixed_params: Optional[Dict[str, Any]] = None,
        underlying_ticker: str = "SPX",
        timeframe: str = "5min",
    ) -> str:
        """Create a new optimization run.

        Args:
            strategy_name: Strategy name
            train_start_date: Training period start
            train_end_date: Training period end
            param_grid: Parameter grid
            optimization_type: Type of optimization
            test_start_date: Test period start
            test_end_date: Test period end
            initial_capital: Initial capital
            fixed_params: Fixed parameters
            underlying_ticker: Underlying ticker
            timeframe: Data timeframe

        Returns:
            Optimization ID
        """
        # Generate optimization ID
        import uuid
        optimization_id = str(uuid.uuid4())[:8]

        # Count permutations
        total_combinations = self.count_permutations(param_grid)

        # Create database record with retry
        success = await self.retry_policy.execute(
            self.repository.create_optimization_run,
            optimization_id=optimization_id,
            strategy_name=strategy_name,
            param_grid=param_grid,
            train_start_date=train_start_date,
            train_end_date=train_end_date,
            total_combinations=total_combinations,
            optimization_type=optimization_type,
            test_start_date=test_start_date,
            test_end_date=test_end_date,
            initial_capital=initial_capital,
            fixed_params=fixed_params,
            underlying_ticker=underlying_ticker,
            timeframe=timeframe,
        )

        if not success:
            raise ValueError("Failed to create optimization run in database")

        logger.info(
            f"[Service] Created optimization {optimization_id}: "
            f"{strategy_name} with {total_combinations} combinations"
        )

        return optimization_id

    async def run_optimization(self, optimization_id: str) -> None:
        """Run an optimization asynchronously.

        Args:
            optimization_id: Optimization ID
        """
        logger.info(f"[Service] Starting optimization {optimization_id}")

        # Get optimization details from database
        optimization = await self.retry_policy.execute(
            self.repository.get_optimization_status,
            optimization_id,
        )

        if not optimization:
            raise ValueError(f"Optimization {optimization_id} not found")

        # Update status to running
        await self.repository.update_optimization_status(
            optimization_id, "running"
        )

        # Create task for async execution
        task = asyncio.create_task(
            self._run_optimization_task(optimization_id, optimization)
        )

        # Store task reference
        self._running_tasks[optimization_id] = task

        # Add callback to clean up on completion
        def task_done_callback(future):
            self._running_tasks.pop(optimization_id, None)
            logger.info(f"[Service] Optimization task {optimization_id} completed")

        task.add_done_callback(task_done_callback)

    async def _run_optimization_task(
        self,
        optimization_id: str,
        optimization: Dict[str, Any],
    ) -> None:
        """Run optimization task.

        Args:
            optimization_id: Optimization ID
            optimization: Optimization details
        """
        try:
            # Progress callback
            async def progress_callback(current, total, params, metrics):
                await self.repository.update_optimization_progress(
                    optimization_id,
                    current,
                    total,
                )

            # Result callback
            results_buffer = []

            async def result_callback(result):
                results_buffer.append(result)
                # Save results in batches
                if len(results_buffer) >= 100:
                    await self._save_results_batch(optimization_id, results_buffer)
                    results_buffer.clear()

            # Execute optimization with circuit breaker
            circuit_breaker = self.circuit_breaker_manager.get_breaker(
                f"optimization_{optimization_id}"
            )

            result = await circuit_breaker.call(
                self.executor.execute_optimization,
                optimization_id=optimization_id,
                strategy_name=optimization["strategy_name"],
                param_grid=optimization["param_grid"],
                train_start_date=optimization["train_start_date"],
                train_end_date=optimization["train_end_date"],
                test_start_date=optimization.get("test_start_date"),
                test_end_date=optimization.get("test_end_date"),
                initial_capital=optimization.get("initial_capital", 100000),
                fixed_params=optimization.get("fixed_params"),
                underlying_ticker=optimization.get("underlying_ticker", "SPX"),
                timeframe=optimization.get("timeframe", "5min"),
                optimization_type=optimization.get("optimization_type", "grid_search"),
                progress_callback=progress_callback,
                result_callback=result_callback,
            )

            # Save any remaining results
            if results_buffer:
                await self._save_results_batch(optimization_id, results_buffer)

            # Save results to CSV
            csv_path = await self.result_processor.save_results_to_csv(
                optimization_id,
                result["results"],
                metadata={
                    "strategy_name": optimization["strategy_name"],
                    "optimization_type": optimization.get("optimization_type"),
                }
            )

            # Update best results in database
            if result["summary"] and result["summary"].get("best_metrics"):
                best_metrics = result["summary"]["best_metrics"]
                await self.repository.update_best_results(
                    optimization_id,
                    result["summary"].get("best_params", {}),
                    best_metrics.get("sharpe_ratio", 0),
                    best_metrics.get("total_return", 0),
                    best_metrics.get("win_rate", 0),
                    best_metrics.get("max_drawdown", 0),
                )

            # Compute rankings
            await self.repository.compute_rankings(optimization_id)

            # Update status to completed
            await self.repository.update_optimization_status(
                optimization_id, "completed"
            )

            logger.info(
                f"[Service] Optimization {optimization_id} completed successfully"
            )

        except Exception as e:
            logger.error(f"[Service] Optimization {optimization_id} failed: {e}")

            # Update status to failed
            await self.repository.update_optimization_status(
                optimization_id, "failed", str(e)
            )

    async def _save_results_batch(
        self,
        optimization_id: str,
        results: List[Dict[str, Any]],
    ) -> None:
        """Save a batch of results to database.

        Args:
            optimization_id: Optimization ID
            results: List of results to save
        """
        try:
            await self.retry_policy.execute(
                self.repository.save_optimization_results,
                optimization_id,
                results,
            )
        except Exception as e:
            logger.error(f"[Service] Failed to save results batch: {e}")

    async def cancel_optimization(self, optimization_id: str) -> None:
        """Cancel a running optimization.

        Args:
            optimization_id: Optimization ID
        """
        # Cancel in executor
        cancelled = self.executor.cancel_optimization(optimization_id)

        if cancelled:
            # Cancel in progress tracker
            await self.progress_tracker.cancel_progress(optimization_id)

            # Update database status
            await self.repository.update_optimization_status(
                optimization_id, "cancelled"
            )

            # Cancel task if running
            task = self._running_tasks.get(optimization_id)
            if task and not task.done():
                task.cancel()

            logger.info(f"[Service] Cancelled optimization {optimization_id}")
        else:
            logger.warning(f"[Service] Optimization {optimization_id} not found for cancellation")

    # ============================================================================
    # Status and Results
    # ============================================================================

    async def get_status(self, optimization_id: str) -> Dict[str, Any]:
        """Get optimization status.

        Args:
            optimization_id: Optimization ID

        Returns:
            Status dictionary
        """
        # Get from database
        status = await self.repository.get_optimization_status(optimization_id)

        if not status:
            raise ValueError(f"Optimization {optimization_id} not found")

        # Merge with progress tracker data
        progress = await self.progress_tracker.get_progress(optimization_id)
        if progress:
            status.update(progress)

        return status

    async def get_results(
        self,
        optimization_id: str,
        limit: int = 100,
        sort_by: str = "sharpe_ratio",
    ) -> Dict[str, Any]:
        """Get optimization results.

        Args:
            optimization_id: Optimization ID
            limit: Maximum number of results
            sort_by: Sort criterion

        Returns:
            Results dictionary
        """
        # Get optimization status
        status = await self.repository.get_optimization_status(optimization_id)

        if not status:
            raise ValueError(f"Optimization {optimization_id} not found")

        # Get results from database
        results = await self.repository.get_optimization_results(
            optimization_id,
            limit=limit,
            sort_by=sort_by,
        )

        # Aggregate results
        sorted_results, summary = self.result_processor.aggregate_results(
            results,
            sort_by=sort_by,
            limit=limit,
        )

        return {
            "optimization_id": optimization_id,
            "status": status["status"],
            "strategy_name": status["strategy_name"],
            "optimization_type": status["optimization_type"],
            "total_combinations": status["total_combinations"],
            "best_params": status["best_params"],
            "best_sharpe_ratio": status["best_sharpe_ratio"],
            "best_total_return": status["best_total_return"],
            "best_win_rate": status["best_win_rate"],
            "started_at": status["started_at"],
            "completed_at": status["completed_at"],
            "results": sorted_results,
            "summary": summary,
        }

    # ============================================================================
    # Health Checks
    # ============================================================================

    async def check_health(self) -> Dict[str, Any]:
        """Check service health.

        Returns:
            Health status dictionary
        """
        return await self.health_check_manager.check_all()

    async def _update_optimization_status(self, optimization_id: str, status: str) -> None:
        """Update optimization status (for compatibility).

        Args:
            optimization_id: Optimization ID
            status: New status
        """
        await self.repository.update_optimization_status(optimization_id, status)