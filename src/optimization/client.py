"""
Client for accessing the optimization service.

This client can be used by other services (like admin_ui) to interact
with the optimization service whether it's running locally or remotely.
"""

import os
from datetime import datetime
from typing import Optional, Dict, Any, List
import httpx
import redis.asyncio as aioredis

from quant_vibe.logging import get_logger
from .service import OptimizationService
from .queue.task_queue import OptimizationTaskQueue


logger = get_logger(__name__)


class OptimizationClient:
    """Client for interacting with the optimization service.

    This client can work in two modes:
    1. Direct mode: Uses the OptimizationService directly (for embedded use)
    2. HTTP mode: Calls the optimization API service (for distributed use)
    """

    def __init__(
        self,
        mode: str = "direct",
        api_base_url: Optional[str] = None,
        redis_client: Optional[aioredis.Redis] = None,
        db_connection_string: Optional[str] = None,
    ):
        """Initialize the optimization client.

        Args:
            mode: 'direct' for direct service access, 'http' for API access
            api_base_url: Base URL for API (required if mode='http')
            redis_client: Redis client (required if mode='direct')
            db_connection_string: Database connection (required if mode='direct')
        """
        self.mode = mode
        self.api_base_url = api_base_url or "http://localhost:8200"
        self._service: Optional[OptimizationService] = None
        self._task_queue: Optional[OptimizationTaskQueue] = None
        self._redis_client = redis_client
        self._db_connection_string = db_connection_string

        if mode == "http":
            self._http_client = httpx.AsyncClient(timeout=30.0)
        else:
            self._http_client = None

    async def _get_service(self) -> OptimizationService:
        """Get or initialize the optimization service (direct mode only)."""
        if self.mode != "direct":
            raise RuntimeError("Service only available in direct mode")

        if self._service is None:
            if not self._redis_client or not self._db_connection_string:
                raise ValueError("Redis client and DB connection required for direct mode")

            self._service = OptimizationService(
                redis_client=self._redis_client,
                db_connection_string=self._db_connection_string,
            )

        return self._service

    async def _get_task_queue(self) -> OptimizationTaskQueue:
        """Get or initialize the task queue (direct mode only)."""
        if self.mode != "direct":
            raise RuntimeError("Task queue only available in direct mode")

        if self._task_queue is None:
            if not self._redis_client:
                raise ValueError("Redis client required for task queue")

            self._task_queue = OptimizationTaskQueue(self._redis_client)

        return self._task_queue

    # ============================================================================
    # Parameter Grid Methods
    # ============================================================================

    async def generate_param_grid(
        self,
        strategy_name: str,
        custom_ranges: Optional[Dict[str, List[Any]]] = None,
        optimize_only: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate parameter grid for a strategy.

        Args:
            strategy_name: Strategy name
            custom_ranges: Custom parameter ranges
            optimize_only: List of parameters to optimize

        Returns:
            Parameter grid with total combinations
        """
        if self.mode == "direct":
            service = await self._get_service()
            param_grid = service.generate_param_grid(
                strategy_name=strategy_name,
                custom_ranges=custom_ranges,
                optimize_only=optimize_only,
            )
            total_combinations = service.count_permutations(param_grid)

            return {
                "strategy_name": strategy_name,
                "param_grid": param_grid,
                "total_combinations": total_combinations,
            }

        else:
            # HTTP mode
            response = await self._http_client.post(
                f"{self.api_base_url}/api/optimization/param-grid/generate",
                json={
                    "strategy_name": strategy_name,
                    "custom_ranges": custom_ranges,
                    "optimize_only": optimize_only,
                },
            )
            response.raise_for_status()
            return response.json()

    async def validate_param_grid(
        self,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        max_combinations: int = 200,
    ) -> Dict[str, Any]:
        """Validate parameter grid.

        Args:
            strategy_name: Strategy name
            param_grid: Parameter grid to validate
            max_combinations: Maximum allowed combinations

        Returns:
            Validation result
        """
        if self.mode == "direct":
            service = await self._get_service()
            return service.validate_param_grid(
                strategy_name=strategy_name,
                param_grid=param_grid,
                max_combinations=max_combinations,
            )

        else:
            # HTTP mode
            response = await self._http_client.post(
                f"{self.api_base_url}/api/optimization/param-grid/validate",
                json={
                    "strategy_name": strategy_name,
                    "param_grid": param_grid,
                    "max_combinations": max_combinations,
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_fixed_params(self, strategy_name: str) -> Dict[str, Any]:
        """Get fixed parameters for a strategy.

        Args:
            strategy_name: Strategy name

        Returns:
            Fixed parameters
        """
        if self.mode == "direct":
            service = await self._get_service()
            return {
                "strategy_name": strategy_name,
                "fixed_params": service.get_fixed_params(strategy_name),
            }

        else:
            # HTTP mode
            response = await self._http_client.get(
                f"{self.api_base_url}/api/optimization/fixed-params/{strategy_name}"
            )
            response.raise_for_status()
            return response.json()

    # ============================================================================
    # Optimization Execution Methods
    # ============================================================================

    async def run_optimization(
        self,
        strategy_name: str,
        train_start_date: datetime,
        train_end_date: datetime,
        param_grid: Optional[Dict[str, List[Any]]] = None,
        optimization_type: str = "grid_search",
        test_start_date: Optional[datetime] = None,
        test_end_date: Optional[datetime] = None,
        initial_capital: float = 100000.0,
        fixed_params: Optional[Dict[str, Any]] = None,
        underlying_ticker: str = "SPX",
        timeframe: str = "5min",
    ) -> Dict[str, Any]:
        """Start a new optimization run.

        Args:
            strategy_name: Strategy name
            train_start_date: Training period start
            train_end_date: Training period end
            param_grid: Custom parameter grid (None for auto-generate)
            optimization_type: Type of optimization
            test_start_date: Test period start (walk-forward only)
            test_end_date: Test period end (walk-forward only)
            initial_capital: Initial capital
            fixed_params: Fixed parameters
            underlying_ticker: Underlying ticker
            timeframe: Time aggregation

        Returns:
            Optimization ID and status
        """
        if self.mode == "direct":
            service = await self._get_service()
            task_queue = await self._get_task_queue()

            # Generate or validate param grid
            if param_grid is None:
                param_grid = service.generate_param_grid(strategy_name)
            else:
                validation = service.validate_param_grid(
                    strategy_name=strategy_name,
                    param_grid=param_grid,
                )
                if not validation["valid"]:
                    raise ValueError(f"Invalid parameter grid: {', '.join(validation['errors'])}")

            # Create optimization
            optimization_id = await service.create_optimization(
                strategy_name=strategy_name,
                train_start_date=train_start_date,
                train_end_date=train_end_date,
                param_grid=param_grid,
                optimization_type=optimization_type,
                test_start_date=test_start_date,
                test_end_date=test_end_date,
                initial_capital=initial_capital,
                fixed_params=fixed_params,
                underlying_ticker=underlying_ticker,
                timeframe=timeframe,
            )

            # Publish task to queue
            await task_queue.publish_task(
                optimization_id=optimization_id,
                task_data={
                    "strategy_name": strategy_name,
                    "train_start_date": train_start_date.isoformat(),
                    "train_end_date": train_end_date.isoformat(),
                    "optimization_type": optimization_type,
                },
            )

            queue_size = await task_queue.get_queue_size()

            return {
                "optimization_id": optimization_id,
                "status": "queued",
                "message": f"Optimization queued for execution (queue size: {queue_size})",
                "queue_position": queue_size,
            }

        else:
            # HTTP mode
            request_data = {
                "strategy_name": strategy_name,
                "train_start_date": train_start_date.isoformat(),
                "train_end_date": train_end_date.isoformat(),
                "param_grid": param_grid,
                "optimization_type": optimization_type,
                "initial_capital": initial_capital,
                "fixed_params": fixed_params,
                "underlying_ticker": underlying_ticker,
                "timeframe": timeframe,
            }

            if test_start_date:
                request_data["test_start_date"] = test_start_date.isoformat()
            if test_end_date:
                request_data["test_end_date"] = test_end_date.isoformat()

            response = await self._http_client.post(
                f"{self.api_base_url}/api/optimization/run",
                json=request_data,
            )
            response.raise_for_status()
            return response.json()

    async def get_status(self, optimization_id: str) -> Dict[str, Any]:
        """Get optimization status.

        Args:
            optimization_id: Optimization ID

        Returns:
            Status information
        """
        if self.mode == "direct":
            service = await self._get_service()
            return await service.get_status(optimization_id)

        else:
            # HTTP mode
            response = await self._http_client.get(
                f"{self.api_base_url}/api/optimization/status/{optimization_id}"
            )
            response.raise_for_status()
            return response.json()

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
            Optimization results
        """
        if self.mode == "direct":
            service = await self._get_service()
            return await service.get_results(
                optimization_id=optimization_id,
                limit=limit,
                sort_by=sort_by,
            )

        else:
            # HTTP mode
            response = await self._http_client.get(
                f"{self.api_base_url}/api/optimization/results/{optimization_id}",
                params={"limit": limit, "sort_by": sort_by},
            )
            response.raise_for_status()
            return response.json()

    async def cancel_optimization(self, optimization_id: str) -> Dict[str, Any]:
        """Cancel an optimization.

        Args:
            optimization_id: Optimization ID

        Returns:
            Cancellation result
        """
        if self.mode == "direct":
            service = await self._get_service()
            task_queue = await self._get_task_queue()

            # Try to cancel queued task first
            cancelled_from_queue = await task_queue.cancel_task(optimization_id)

            if cancelled_from_queue:
                await service._update_optimization_status(optimization_id, "cancelled")
                return {
                    "message": f"Optimization {optimization_id} cancelled (removed from queue)",
                    "cancelled_from_queue": True,
                }

            # Try to cancel running optimization
            await service.cancel_optimization(optimization_id)
            return {
                "message": f"Optimization {optimization_id} cancellation requested",
                "cancelled_from_queue": False,
            }

        else:
            # HTTP mode
            response = await self._http_client.post(
                f"{self.api_base_url}/api/optimization/cancel/{optimization_id}"
            )
            response.raise_for_status()
            return response.json()

    async def clear_cache(self, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """Clear optimization cache.

        Args:
            cache_key: Specific cache key or None for all

        Returns:
            Number of keys cleared
        """
        if self.mode == "direct":
            service = await self._get_service()
            deleted = await service.clear_cache(cache_key=cache_key)
            return {
                "message": f"Cleared {deleted} cache keys",
                "deleted_count": deleted,
            }

        else:
            # HTTP mode
            response = await self._http_client.post(
                f"{self.api_base_url}/api/optimization/cache/clear",
                json={"cache_key": cache_key} if cache_key else {},
            )
            response.raise_for_status()
            return response.json()

    async def close(self):
        """Close the client and cleanup resources."""
        if self._http_client:
            await self._http_client.aclose()