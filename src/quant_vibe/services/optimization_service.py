"""
Optimization Service - Centralized async optimization execution.

This service handles the complete optimization lifecycle:
1. Parameter grid generation and validation
2. Data loading with Redis caching
3. Async backtest execution
4. Progress tracking and real-time updates
5. Hybrid result storage (database + filesystem)

Design Goals:
- Replace subprocess approach with in-process async execution
- Cache options data in Redis for repeated optimizations
- Expose param grids dynamically via API
- Track progress with ETA calculation
- Store results in both PostgreSQL and CSV files
"""

import asyncio
import hashlib
import json
import pickle
import itertools
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable
from decimal import Decimal

import pandas as pd
import numpy as np
from redis.asyncio import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from quant_vibe.logging import get_logger
from quant_vibe.strategies.registry import StrategyRegistry
from quant_vibe.utils import load_options_backtest_data, load_options_backtest_data_chunked, now_utc
from quant_vibe.utils.timestamp_utils import to_utc
from backtest import ParameterOptimizer


logger = get_logger(__name__)


class OptimizationService:
    """
    Service for managing strategy parameter optimization.

    Features:
    - Async execution (non-blocking)
    - Redis-based data caching
    - Dynamic param grid generation
    - Real-time progress tracking
    - Hybrid storage (DB + CSV)
    - Permutation count validation
    """

    def __init__(
        self,
        redis_client: Redis,
        db_connection_string: str,
        data_cache_ttl: int = 3600,  # 1 hour
        results_base_dir: str = "results/optimization",
    ):
        """
        Initialize optimization service.

        Args:
            redis_client: Async Redis client for caching and pub/sub
            db_connection_string: PostgreSQL connection string
            data_cache_ttl: Data cache TTL in seconds (default: 1 hour)
            results_base_dir: Base directory for CSV results
        """
        self.redis = redis_client

        # Create a separate binary-safe Redis client for data caching
        # (the main client has decode_responses=True which breaks pickle)
        import redis.asyncio as aioredis

        # Extract connection info from the main client
        redis_url = str(redis_client.connection_pool.connection_kwargs.get('host', 'localhost'))
        redis_port = redis_client.connection_pool.connection_kwargs.get('port', 6379)
        redis_db = redis_client.connection_pool.connection_kwargs.get('db', 0)

        # Create binary client (no decoding)
        async def create_binary_client():
            return await aioredis.from_url(
                f"redis://{redis_url}:{redis_port}/{redis_db}",
                decode_responses=False,  # Return bytes, not strings
            )

        # Store for later async initialization
        self._binary_redis = None
        self._binary_redis_factory = create_binary_client

        self.db_connection_string = db_connection_string
        self.data_cache_ttl = data_cache_ttl
        self.results_base_dir = Path(results_base_dir)
        self.results_base_dir.mkdir(parents=True, exist_ok=True)

        # In-memory tracking of running optimizations
        self.running_optimizations: Dict[str, Dict[str, Any]] = {}

        # Create SQLAlchemy engine for sync DB operations
        self.engine = create_engine(db_connection_string)

    async def _get_binary_redis(self) -> Redis:
        """Get or create binary-safe Redis client."""
        if self._binary_redis is None:
            self._binary_redis = await self._binary_redis_factory()
        return self._binary_redis

    # ========================================================================
    # Parameter Grid Generation & Validation
    # ========================================================================

    def generate_param_grid(
        self,
        strategy_name: str,
        custom_ranges: Optional[Dict[str, List[Any]]] = None,
        optimize_only: Optional[List[str]] = None,
    ) -> Dict[str, List[Any]]:
        """
        Generate parameter grid for optimization.

        Args:
            strategy_name: Strategy name
            custom_ranges: Custom parameter ranges (overrides auto-generated)
            optimize_only: List of parameter names to optimize (others fixed)

        Returns:
            Parameter grid dictionary {param_name: [value1, value2, ...]}

                """
        # Use StrategyRegistry to auto-generate grid
        grid = StrategyRegistry.generate_optimization_grid(
            strategy_name=strategy_name,
            custom_ranges=custom_ranges,
            optimize_only=optimize_only,
        )

        logger.info(
            f"Generated param grid for {strategy_name}",
            extra={
                "strategy": strategy_name,
                "params": list(grid.keys()),
                "combinations": self.count_permutations(grid),
            }
        )

        return grid

    def get_fixed_params(self, strategy_name: str) -> Dict[str, Any]:
        """
        Get fixed (non-optimizable) parameters for a strategy.

        Args:
            strategy_name: Strategy name

        Returns:
            Dictionary of fixed parameters

                """
        # Get all default params
        all_params = StrategyRegistry.get_default_params(strategy_name)

        # Get optimization grid to determine which params are variable
        opt_grid = StrategyRegistry.generate_optimization_grid(strategy_name)

        # Fixed params are those not in the optimization grid
        fixed_params = {
            k: v for k, v in all_params.items()
            if k not in opt_grid
        }

        return fixed_params

    @staticmethod
    def count_permutations(param_grid: Dict[str, List[Any]]) -> int:
        """
        Calculate total number of parameter combinations.

        Args:
            param_grid: Parameter grid

        Returns:
            Total number of combinations

                    ...     'param_a': [1, 2, 3],
            ...     'param_b': [0.5, 1.0]
            ... })
            >>> # Returns: 6 (3 × 2)
        """
        if not param_grid:
            return 0

        total = 1
        for values in param_grid.values():
            total *= len(values)

        return total

    def validate_param_grid(
        self,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        max_combinations: int = 200,
    ) -> Dict[str, Any]:
        """
        Validate parameter grid and return validation result.

        Args:
            strategy_name: Strategy name
            param_grid: Parameter grid to validate
            max_combinations: Maximum allowed combinations

        Returns:
            Validation result dictionary with keys:
            - valid: bool
            - total_combinations: int
            - warnings: List[str]
            - errors: List[str]

                    ...     print(result['errors'])
        """
        result = {
            "valid": True,
            "total_combinations": 0,
            "warnings": [],
            "errors": [],
        }

        # Check if param grid is empty
        if not param_grid:
            result["valid"] = False
            result["errors"].append("Parameter grid is empty")
            return result

        # Calculate permutations
        total_combinations = self.count_permutations(param_grid)
        result["total_combinations"] = total_combinations

        # Check max combinations
        if total_combinations > max_combinations:
            result["warnings"].append(
                f"High combination count ({total_combinations} > {max_combinations}). "
                f"Optimization may take a long time."
            )

        # Validate parameter names against strategy
        try:
            param_specs = StrategyRegistry.get_param_specs(strategy_name)
            valid_params = set(param_specs.keys())
            provided_params = set(param_grid.keys())

            # Check for unknown parameters
            unknown_params = provided_params - valid_params
            if unknown_params:
                result["valid"] = False
                result["errors"].append(
                    f"Unknown parameters: {sorted(unknown_params)}. "
                    f"Valid parameters: {sorted(valid_params)}"
                )

            # Validate individual values (basic type checking)
            for param_name, values in param_grid.items():
                if param_name not in param_specs:
                    continue  # Already caught above

                spec = param_specs[param_name]
                for value in values:
                    # Check type compatibility
                    expected_type = spec.get('type', 'Unknown')
                    if expected_type == 'float' and not isinstance(value, (int, float)):
                        result["errors"].append(
                            f"Parameter '{param_name}' expects float, got {type(value).__name__}"
                        )
                        result["valid"] = False

                    # Check constraints (ge, le, gt, lt)
                    if 'ge' in spec and value < spec['ge']:
                        result["errors"].append(
                            f"Parameter '{param_name}' value {value} < minimum {spec['ge']}"
                        )
                        result["valid"] = False

                    if 'le' in spec and value > spec['le']:
                        result["errors"].append(
                            f"Parameter '{param_name}' value {value} > maximum {spec['le']}"
                        )
                        result["valid"] = False

        except Exception as e:
            result["valid"] = False
            result["errors"].append(f"Validation error: {str(e)}")

        return result

    # ========================================================================
    # Data Caching
    # ========================================================================

    def _generate_cache_key(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int,
        max_dte: int,
        timeframe: str,
    ) -> str:
        """Generate Redis cache key for options data."""
        key_data = f"{ticker}:{start_date.date()}:{end_date.date()}:{min_dte}:{max_dte}:{timeframe}"
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"opt_data:{ticker}:{key_hash}"

    async def get_cached_data(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int,
        max_dte: int,
        timeframe: str = "5min",
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load options/underlying data with Redis caching.

        Args:
            ticker: Underlying ticker
            start_date: Start date
            end_date: End date
            min_dte: Minimum DTE
            max_dte: Maximum DTE
            timeframe: Time aggregation

        Returns:
            Tuple of (options_data, underlying_data) DataFrames

        Raises:
            ValueError: If data not available
        """
        cache_key = self._generate_cache_key(
            ticker, start_date, end_date, min_dte, max_dte, timeframe
        )

        logger.info(
            f"Loading data for {ticker}",
            extra={
                "ticker": ticker,
                "start": start_date.date(),
                "end": end_date.date(),
                "dte_range": f"{min_dte}-{max_dte}",
                "timeframe": timeframe,
                "cache_key": cache_key,
            }
        )

        # Try Redis cache (use binary client for pickled data)
        try:
            binary_redis = await self._get_binary_redis()
            cached = await binary_redis.get(cache_key)
            if cached:
                cached_size_mb = len(cached) / 1024 / 1024
                logger.info(f"Cache hit! Unpickling {cached_size_mb:.2f}MB from Redis...")

                try:
                    data = pickle.loads(cached)
                    options_data, underlying_data = data
                except Exception as unpickle_error:
                    logger.error(f"Unpickle failed: {unpickle_error}", exc_info=True)
                    # Fall through to database load
                    raise

                logger.info(
                    f"✅ Cache HIT for {ticker}",
                    extra={
                        "cache_key": cache_key,
                        "options_rows": len(options_data),
                        "underlying_rows": len(underlying_data),
                        "cached_size_mb": cached_size_mb,
                    }
                )

                # Update cache stats in DB
                await self._update_cache_stats(cache_key)

                return options_data, underlying_data

        except Exception as e:
            logger.warning(f"Redis cache read error: {e}", exc_info=True)

        # Cache miss - load from database
        logger.info(f"Cache MISS for {ticker}, loading from database...")

        # Calculate date range to decide on loading strategy
        date_range_days = (end_date - start_date).days

        # Always use chunked loading to avoid query timeouts and OOM
        # Recent expiration weeks can have 1M+ rows per day
        if date_range_days > 1:
            logger.info(f"Using chunked loading for {date_range_days} day range (1-day chunks)...")
            options_data, underlying_data = await asyncio.to_thread(
                load_options_backtest_data_chunked,
                underlying_ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                min_dte=min_dte,
                max_dte=max_dte,
                timeframe=timeframe,
                verbose=True,
                chunk_days=1,  # 1-day chunks to avoid OOM on high-volume periods
            )
        else:
            # Load data directly for smaller ranges (sync operation)
            options_data, underlying_data = await asyncio.to_thread(
                load_options_backtest_data,
                underlying_ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                min_dte=min_dte,
                max_dte=max_dte,
                timeframe=timeframe,
                verbose=True,
            )

        # Cache in Redis (use binary client for pickled data)
        try:
            binary_redis = await self._get_binary_redis()
            data = (options_data, underlying_data)

            # Pickle with protocol 4 (more efficient, but compatible)
            logger.info(f"Pickling data for cache ({len(options_data)} option rows, {len(underlying_data)} underlying rows)...")
            try:
                pickled = pickle.dumps(data, protocol=4)
            except Exception as pickle_error:
                logger.error(f"Pickle serialization failed: {pickle_error}", exc_info=True)
                raise

            pickled_size_mb = len(pickled) / 1024 / 1024
            logger.info(f"Pickled size: {pickled_size_mb:.2f} MB")

            # Sanity check - don't cache if too large (>2GB)
            if pickled_size_mb > 2048:
                logger.warning(f"Pickled data too large ({pickled_size_mb:.2f}MB), skipping Redis cache")
                return options_data, underlying_data

            # Store in Redis
            logger.info(f"Storing {pickled_size_mb:.2f}MB in Redis...")
            try:
                await binary_redis.setex(cache_key, self.data_cache_ttl, pickled)
            except Exception as redis_error:
                logger.error(f"Redis storage failed: {redis_error}", exc_info=True)
                raise

            # Store cache metadata in DB
            await self._store_cache_metadata(
                cache_key=cache_key,
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                min_dte=min_dte,
                max_dte=max_dte,
                timeframe=timeframe,
                num_options_rows=len(options_data),
                num_underlying_rows=len(underlying_data),
                data_size_mb=pickled_size_mb,
            )

            logger.info(
                f"✅ Cached data for {ticker}",
                extra={
                    "cache_key": cache_key,
                    "size_mb": pickled_size_mb,
                    "ttl": self.data_cache_ttl,
                }
            )

        except Exception as e:
            logger.warning(f"Failed to cache data: {e}", exc_info=True)

        return options_data, underlying_data

    async def _store_cache_metadata(
        self,
        cache_key: str,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int,
        max_dte: int,
        timeframe: str,
        num_options_rows: int,
        num_underlying_rows: int,
        data_size_mb: float,
    ) -> None:
        """Store cache metadata in database."""
        try:
            query = text("""
                INSERT INTO optimization_cache_status (
                    cache_key, underlying_ticker, start_date, end_date,
                    min_dte, max_dte, timeframe, num_options_rows,
                    num_underlying_rows, data_size_mb, redis_stored,
                    expires_at, created_at, last_accessed_at
                )
                VALUES (
                    :cache_key, :ticker, :start_date, :end_date,
                    :min_dte, :max_dte, :timeframe, :num_options_rows,
                    :num_underlying_rows, :data_size_mb, TRUE,
                    :expires_at, :created_at, :last_accessed_at
                )
                ON CONFLICT (cache_key) DO UPDATE SET
                    hit_count = optimization_cache_status.hit_count + 1,
                    last_accessed_at = :last_accessed_at
            """)

            now = now_utc()
            expires_at = now + timedelta(seconds=self.data_cache_ttl)

            with self.engine.connect() as conn:
                conn.execute(query, {
                    "cache_key": cache_key,
                    "ticker": ticker,
                    "start_date": start_date,
                    "end_date": end_date,
                    "min_dte": min_dte,
                    "max_dte": max_dte,
                    "timeframe": timeframe,
                    "num_options_rows": num_options_rows,
                    "num_underlying_rows": num_underlying_rows,
                    "data_size_mb": data_size_mb,
                    "expires_at": expires_at,
                    "created_at": now,
                    "last_accessed_at": now,
                })
                conn.commit()

        except SQLAlchemyError as e:
            logger.warning(f"Failed to store cache metadata: {e}")

    async def _update_cache_stats(self, cache_key: str) -> None:
        """Update cache hit count."""
        try:
            query = text("""
                UPDATE optimization_cache_status
                SET hit_count = hit_count + 1,
                    last_accessed_at = :now
                WHERE cache_key = :cache_key
            """)

            with self.engine.connect() as conn:
                conn.execute(query, {"cache_key": cache_key, "now": now_utc()})
                conn.commit()

        except SQLAlchemyError as e:
            logger.warning(f"Failed to update cache stats: {e}")

    async def clear_cache(self, cache_key: Optional[str] = None) -> int:
        """
        Clear cached data.

        Args:
            cache_key: Specific cache key to clear (or None for all)

        Returns:
            Number of keys deleted
        """
        binary_redis = await self._get_binary_redis()

        if cache_key:
            # Clear specific key
            deleted = await binary_redis.delete(cache_key)
        else:
            # Clear all optimization data caches
            keys = []
            async for key in binary_redis.scan_iter(match="optimization:data:*"):
                keys.append(key)

            if keys:
                deleted = await binary_redis.delete(*keys)
            else:
                deleted = 0

        logger.info(f"Cleared {deleted} cache keys")
        return deleted

    # ========================================================================
    # Optimization Execution
    # ========================================================================

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
        """
        Create a new optimization run.

        Args:
            strategy_name: Strategy name
            train_start_date: Training period start
            train_end_date: Training period end
            param_grid: Parameter grid
            optimization_type: Type ('grid_search' or 'walk_forward')
            test_start_date: Test period start (for walk-forward)
            test_end_date: Test period end (for walk-forward)
            initial_capital: Initial capital
            fixed_params: Fixed parameters
            underlying_ticker: Underlying ticker
            timeframe: Time aggregation

        Returns:
            Optimization ID

        Raises:
            ValueError: If validation fails
        """
        # Validate param grid
        validation = self.validate_param_grid(strategy_name, param_grid)
        if not validation["valid"]:
            raise ValueError(
                f"Invalid parameter grid: {', '.join(validation['errors'])}"
            )

        # Generate optimization ID
        timestamp = now_utc().strftime("%Y%m%d_%H%M%S")
        optimization_id = f"{strategy_name}_{optimization_type}_{timestamp}"

        # Get fixed params (merge with defaults)
        default_fixed = self.get_fixed_params(strategy_name)
        if fixed_params:
            default_fixed.update(fixed_params)
        fixed_params = default_fixed

        # Calculate total combinations
        total_combinations = self.count_permutations(param_grid)

        # Store in database
        try:
            query = text("""
                INSERT INTO optimization_runs (
                    optimization_id, strategy_name, optimization_type,
                    train_start_date, train_end_date, test_start_date, test_end_date,
                    initial_capital, param_grid, fixed_params, total_combinations,
                    underlying_ticker, timeframe, status, progress_current, progress_total,
                    created_at
                )
                VALUES (
                    :optimization_id, :strategy_name, :optimization_type,
                    :train_start, :train_end, :test_start, :test_end,
                    :initial_capital, :param_grid, :fixed_params, :total_combinations,
                    :ticker, :timeframe, 'pending', 0, :total_combinations,
                    :created_at
                )
            """)

            with self.engine.connect() as conn:
                conn.execute(query, {
                    "optimization_id": optimization_id,
                    "strategy_name": strategy_name,
                    "optimization_type": optimization_type,
                    "train_start": train_start_date,
                    "train_end": train_end_date,
                    "test_start": test_start_date,
                    "test_end": test_end_date,
                    "initial_capital": initial_capital,
                    # For JSONB columns, pass dict directly or JSON string
                    "param_grid": json.dumps(param_grid) if isinstance(param_grid, dict) else param_grid,
                    "fixed_params": json.dumps(fixed_params) if isinstance(fixed_params, dict) else fixed_params,
                    "total_combinations": total_combinations,
                    "ticker": underlying_ticker,
                    "timeframe": timeframe,
                    "created_at": now_utc(),
                })
                conn.commit()

        except SQLAlchemyError as e:
            logger.error(f"Failed to create optimization: {e}", exc_info=True)
            raise ValueError(f"Database error: {e}")

        logger.info(
            f"Created optimization {optimization_id}",
            extra={
                "optimization_id": optimization_id,
                "strategy": strategy_name,
                "combinations": total_combinations,
            }
        )

        return optimization_id

    async def run_optimization(self, optimization_id: str) -> None:
        """
        Run optimization in background (async).

        This method spawns an async task to execute the optimization.
        Use get_status() to monitor progress.

        Args:
            optimization_id: Optimization ID from create_optimization()

        Raises:
            ValueError: If optimization not found or already running
        """
        # Check if already running
        if optimization_id in self.running_optimizations:
            raise ValueError(f"Optimization {optimization_id} is already running")

        # Load optimization config from DB
        try:
            query = text("""
                SELECT strategy_name, optimization_type, train_start_date, train_end_date,
                       test_start_date, test_end_date, initial_capital, param_grid,
                       fixed_params, underlying_ticker, timeframe, total_combinations
                FROM optimization_runs
                WHERE optimization_id = :opt_id
            """)

            with self.engine.connect() as conn:
                result = conn.execute(query, {"opt_id": optimization_id}).fetchone()

            if not result:
                raise ValueError(f"Optimization {optimization_id} not found")

            config = {
                "optimization_id": optimization_id,
                "strategy_name": result[0],
                "optimization_type": result[1],
                "train_start_date": result[2],
                "train_end_date": result[3],
                "test_start_date": result[4],
                "test_end_date": result[5],
                "initial_capital": float(result[6]),
                # JSONB fields are already returned as dicts by PostgreSQL
                "param_grid": result[7] if isinstance(result[7], dict) else json.loads(result[7]),
                "fixed_params": result[8] if isinstance(result[8], dict) else (json.loads(result[8]) if result[8] else {}),
                "underlying_ticker": result[9],
                "timeframe": result[10],
                "total_combinations": result[11],
            }

        except SQLAlchemyError as e:
            logger.error(f"Failed to load optimization config: {e}", exc_info=True)
            raise ValueError(f"Database error: {e}")

        # Mark as running
        self.running_optimizations[optimization_id] = {
            "config": config,
            "start_time": now_utc(),
            "cancel_requested": False,
        }

        # Update status in DB
        await self._update_optimization_status(optimization_id, "running")

        # Start async task with error handling
        task = asyncio.create_task(self._run_optimization_impl(optimization_id, config))

        # Add task callback to catch exceptions
        def task_done_callback(task):
            try:
                task.result()  # This will raise if task had an exception
            except Exception as e:
                logger.error(f"Optimization task {optimization_id} failed with uncaught exception: {e}", exc_info=True)

        task.add_done_callback(task_done_callback)

        logger.info(f"Started optimization task {optimization_id}")

    async def _run_optimization_impl(
        self,
        optimization_id: str,
        config: Dict[str, Any],
    ) -> None:
        """
        Internal optimization implementation (runs as async task).

        Args:
            optimization_id: Optimization ID
            config: Optimization configuration
        """
        try:
            logger.info(f"[OPTIMIZATION {optimization_id}] Task started, loading data...")
            logger.info(
                f"Running optimization {optimization_id}",
                extra={
                    "optimization_id": optimization_id,
                    "strategy": config["strategy_name"],
                    "combinations": config["total_combinations"],
                }
            )

            # Load data with caching
            min_dte = config["fixed_params"].get("min_dte", 0)
            max_dte = config["fixed_params"].get("max_dte", 45)

            logger.info(f"[OPTIMIZATION {optimization_id}] Loading data from {config['train_start_date']} to {config['train_end_date']}...")
            options_data, underlying_data = await self.get_cached_data(
                ticker=config["underlying_ticker"],
                start_date=config["train_start_date"],
                end_date=config["train_end_date"],
                min_dte=min_dte,
                max_dte=max_dte,
                timeframe=config["timeframe"],
            )
            logger.info(f"[OPTIMIZATION {optimization_id}] Data loaded: {len(options_data)} option bars, {len(underlying_data)} underlying bars")

            # Get strategy class
            logger.info(f"[OPTIMIZATION {optimization_id}] Getting strategy class...")
            strategy_class = StrategyRegistry.get_strategy_class(config["strategy_name"])

            # Create optimizer
            logger.info(f"[OPTIMIZATION {optimization_id}] Creating optimizer...")
            optimizer = ParameterOptimizer(
                strategy_class=strategy_class,
                underlying_data=underlying_data,
                options_data=options_data,
                initial_capital=config["initial_capital"],
                start_date=config["train_start_date"],
                end_date=config["train_end_date"],
            )

            # Progress callback (async)
            async def progress_callback(current: int, total: int, params: Dict, metrics: Dict):
                # Check for cancellation
                if self.running_optimizations[optimization_id]["cancel_requested"]:
                    raise asyncio.CancelledError("Optimization cancelled by user")

                # Update progress in DB
                await self._update_optimization_progress(
                    optimization_id, current, total, params, metrics
                )

                # Publish progress to Redis pub/sub for real-time UI updates
                await self.redis.publish(
                    f"optimization.{optimization_id}.progress",
                    json.dumps({
                        "current": current,
                        "total": total,
                        "params": params,
                        "metrics": {k: float(v) if isinstance(v, (int, float, Decimal)) else v
                                   for k, v in metrics.items()},
                        "timestamp": now_utc().isoformat(),
                    })
                )

            # Get the current event loop (we're in the async context)
            loop = asyncio.get_running_loop()

            # Wrap async callback for sync context (thread-safe)
            def sync_progress_callback(current: int, total: int, params: Dict, metrics: Dict):
                """
                Called from optimizer thread - schedule coroutine in main event loop.
                """
                # Schedule the async callback in the main event loop
                future = asyncio.run_coroutine_threadsafe(
                    progress_callback(current, total, params, metrics),
                    loop
                )
                # Don't wait for completion (fire-and-forget)
                # Add error handler
                def handle_callback_error(fut):
                    try:
                        fut.result()
                    except Exception as e:
                        logger.warning(f"Progress callback error: {e}")

                future.add_done_callback(handle_callback_error)

            # Run grid search (in thread to avoid blocking event loop)
            logger.info(f"[OPTIMIZATION {optimization_id}] Starting grid search with {config['total_combinations']} combinations...")
            results_df = await asyncio.to_thread(
                optimizer.grid_search,
                param_grid=config["param_grid"],
                fixed_params=config["fixed_params"],
                verbose=True,
                progress_callback=sync_progress_callback,
            )
            logger.info(f"[OPTIMIZATION {optimization_id}] Grid search completed, processing results...")

            # Save results to database
            await self._save_results_to_db(optimization_id, results_df)

            # Save results to CSV (for backup/export)
            await self._save_results_to_csv(optimization_id, config["strategy_name"], results_df)

            # Compute rankings
            await self._compute_rankings(optimization_id)

            # Get best result
            best_result = results_df.loc[results_df["sharpe_ratio"].idxmax()]

            # Mark as completed
            await self._complete_optimization(
                optimization_id,
                best_params=best_result["params"],
                best_sharpe=float(best_result["sharpe_ratio"]),
                best_return=float(best_result["total_return"]),
                best_win_rate=float(best_result["win_rate"]),
            )

            logger.info(
                f"✅ Optimization {optimization_id} completed successfully",
                extra={
                    "optimization_id": optimization_id,
                    "best_sharpe": float(best_result["sharpe_ratio"]),
                }
            )

        except asyncio.CancelledError:
            logger.info(f"Optimization {optimization_id} cancelled")
            await self._update_optimization_status(optimization_id, "cancelled")

        except Exception as e:
            logger.error(f"Optimization {optimization_id} failed: {e}", exc_info=True)
            await self._update_optimization_status(
                optimization_id, "failed", error_message=str(e)
            )

        finally:
            # Clean up
            if optimization_id in self.running_optimizations:
                del self.running_optimizations[optimization_id]

    async def _update_optimization_status(
        self,
        optimization_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Update optimization status in database."""
        try:
            if status == "running":
                query = text("""
                    UPDATE optimization_runs
                    SET status = :status, started_at = :started_at, updated_at = :updated_at
                    WHERE optimization_id = :opt_id
                """)
                params = {
                    "status": status,
                    "started_at": now_utc(),
                    "updated_at": now_utc(),
                    "opt_id": optimization_id,
                }
            elif error_message:
                query = text("""
                    UPDATE optimization_runs
                    SET status = :status, error_message = :error, updated_at = :updated_at
                    WHERE optimization_id = :opt_id
                """)
                params = {
                    "status": status,
                    "error": error_message,
                    "updated_at": now_utc(),
                    "opt_id": optimization_id,
                }
            else:
                query = text("""
                    UPDATE optimization_runs
                    SET status = :status, updated_at = :updated_at
                    WHERE optimization_id = :opt_id
                """)
                params = {
                    "status": status,
                    "updated_at": now_utc(),
                    "opt_id": optimization_id,
                }

            with self.engine.connect() as conn:
                conn.execute(query, params)
                conn.commit()

        except SQLAlchemyError as e:
            logger.warning(f"Failed to update status: {e}")

    async def _update_optimization_progress(
        self,
        optimization_id: str,
        current: int,
        total: int,
        params: Dict,
        metrics: Dict,
    ) -> None:
        """Update optimization progress."""
        try:
            # Calculate ETA
            if optimization_id in self.running_optimizations:
                start_time = self.running_optimizations[optimization_id]["start_time"]
                elapsed = (now_utc() - start_time).total_seconds()
                if current > 0:
                    avg_time_per_combo = elapsed / current
                    remaining_combos = total - current
                    eta_seconds = remaining_combos * avg_time_per_combo
                    eta = now_utc() + timedelta(seconds=eta_seconds)
                else:
                    eta = None
            else:
                eta = None

            query = text("""
                UPDATE optimization_runs
                SET progress_current = :current,
                    estimated_completion_time = :eta,
                    updated_at = :updated_at
                WHERE optimization_id = :opt_id
            """)

            with self.engine.connect() as conn:
                conn.execute(query, {
                    "current": current,
                    "eta": eta,
                    "updated_at": now_utc(),
                    "opt_id": optimization_id,
                })
                conn.commit()

        except SQLAlchemyError as e:
            logger.warning(f"Failed to update progress: {e}")

    async def _save_results_to_db(
        self,
        optimization_id: str,
        results_df: pd.DataFrame,
    ) -> None:
        """Save optimization results to database."""
        try:
            for idx, row in results_df.iterrows():
                # Create param hash for deduplication
                params_str = json.dumps(row["params"], sort_keys=True)
                param_hash = hashlib.md5(params_str.encode()).hexdigest()

                query = text("""
                    INSERT INTO optimization_results (
                        optimization_id, params, param_hash,
                        sharpe_ratio, total_return, total_return_pct,
                        total_trades, winning_trades, losing_trades,
                        win_rate, avg_win, avg_loss, profit_factor,
                        max_drawdown, final_capital
                    )
                    VALUES (
                        :opt_id, :params, :param_hash,
                        :sharpe, :total_return, :total_return_pct,
                        :total_trades, :num_winning, :num_losing,
                        :win_rate, :avg_win, :avg_loss, :profit_factor,
                        :max_drawdown, :final_capital
                    )
                    ON CONFLICT (optimization_id, param_hash) DO UPDATE SET
                        sharpe_ratio = EXCLUDED.sharpe_ratio,
                        total_return = EXCLUDED.total_return,
                        total_return_pct = EXCLUDED.total_return_pct,
                        total_trades = EXCLUDED.total_trades
                """)

                with self.engine.connect() as conn:
                    conn.execute(query, {
                        "opt_id": optimization_id,
                        "params": params_str,
                        "param_hash": param_hash,
                        "sharpe": float(row["sharpe_ratio"]) if pd.notna(row["sharpe_ratio"]) else None,
                        "total_return": float(row["total_return"]) if pd.notna(row["total_return"]) else None,
                        "total_return_pct": float(row["total_return"]) if pd.notna(row["total_return"]) else None,
                        "total_trades": int(row["total_trades"]) if pd.notna(row["total_trades"]) else 0,
                        "num_winning": None,  # Not in results_df
                        "num_losing": None,  # Not in results_df
                        "win_rate": float(row["win_rate"]) if pd.notna(row["win_rate"]) else None,
                        "avg_win": None,  # Not in results_df
                        "avg_loss": None,  # Not in results_df
                        "profit_factor": float(row["profit_factor"]) if pd.notna(row["profit_factor"]) else None,
                        "max_drawdown": float(row["max_drawdown"]) if pd.notna(row["max_drawdown"]) else None,
                        "final_capital": None,  # Not in results_df
                    })
                    conn.commit()

            logger.info(f"Saved {len(results_df)} results to database")

        except SQLAlchemyError as e:
            logger.error(f"Failed to save results to DB: {e}", exc_info=True)

    async def _save_results_to_csv(
        self,
        optimization_id: str,
        strategy_name: str,
        results_df: pd.DataFrame,
    ) -> None:
        """Save results to CSV file."""
        try:
            output_dir = self.results_base_dir / optimization_id
            output_dir.mkdir(parents=True, exist_ok=True)

            csv_file = output_dir / f"{strategy_name}_results.csv"
            results_df.to_csv(csv_file, index=False)

            logger.info(f"Saved results to {csv_file}")

        except Exception as e:
            logger.warning(f"Failed to save CSV: {e}")

    async def _compute_rankings(self, optimization_id: str) -> None:
        """Compute result rankings."""
        try:
            query = text("SELECT compute_optimization_rankings(:opt_id)")

            with self.engine.connect() as conn:
                conn.execute(query, {"opt_id": optimization_id})
                conn.commit()

        except SQLAlchemyError as e:
            logger.warning(f"Failed to compute rankings: {e}")

    async def _complete_optimization(
        self,
        optimization_id: str,
        best_params: Dict,
        best_sharpe: float,
        best_return: float,
        best_win_rate: float,
    ) -> None:
        """Mark optimization as completed."""
        try:
            query = text("""
                UPDATE optimization_runs
                SET status = 'completed',
                    completed_at = :completed_at,
                    best_params = :best_params,
                    best_sharpe_ratio = :best_sharpe,
                    best_total_return = :best_return,
                    best_win_rate = :best_win_rate,
                    updated_at = :updated_at
                WHERE optimization_id = :opt_id
            """)

            with self.engine.connect() as conn:
                conn.execute(query, {
                    "completed_at": now_utc(),
                    "best_params": json.dumps(best_params),
                    "best_sharpe": best_sharpe,
                    "best_return": best_return,
                    "best_win_rate": best_win_rate,
                    "updated_at": now_utc(),
                    "opt_id": optimization_id,
                })
                conn.commit()

        except SQLAlchemyError as e:
            logger.warning(f"Failed to mark as completed: {e}")

    async def cancel_optimization(self, optimization_id: str) -> None:
        """
        Cancel a running optimization.

        Args:
            optimization_id: Optimization ID

        Raises:
            ValueError: If optimization not running
        """
        if optimization_id not in self.running_optimizations:
            raise ValueError(f"Optimization {optimization_id} is not running")

        # Set cancel flag
        self.running_optimizations[optimization_id]["cancel_requested"] = True

        logger.info(f"Cancellation requested for {optimization_id}")

    async def get_status(self, optimization_id: str) -> Dict[str, Any]:
        """
        Get optimization status.

        Args:
            optimization_id: Optimization ID

        Returns:
            Status dictionary with keys:
            - status: str
            - progress_current: int
            - progress_total: int
            - estimated_completion_time: datetime
            - best_params: dict (if completed)
            - best_sharpe_ratio: float (if completed)
            - error_message: str (if failed)

        Raises:
            ValueError: If optimization not found
        """
        try:
            query = text("""
                SELECT status, progress_current, progress_total,
                       estimated_completion_time, best_params,
                       best_sharpe_ratio, best_total_return, best_win_rate,
                       error_message, started_at, completed_at,
                       strategy_name, optimization_type, total_combinations
                FROM optimization_runs
                WHERE optimization_id = :opt_id
            """)

            with self.engine.connect() as conn:
                result = conn.execute(query, {"opt_id": optimization_id}).fetchone()

            if not result:
                raise ValueError(f"Optimization {optimization_id} not found")

            return {
                "optimization_id": optimization_id,
                "status": result[0],
                "progress_current": result[1],
                "progress_total": result[2],
                "estimated_completion_time": result[3].isoformat() if result[3] else None,
                # JSONB field - already a dict if from PostgreSQL
                "best_params": result[4] if isinstance(result[4], dict) else (json.loads(result[4]) if result[4] else None),
                "best_sharpe_ratio": float(result[5]) if result[5] else None,
                "best_total_return": float(result[6]) if result[6] else None,
                "best_win_rate": float(result[7]) if result[7] else None,
                "error_message": result[8],
                "started_at": result[9].isoformat() if result[9] else None,
                "completed_at": result[10].isoformat() if result[10] else None,
                "strategy_name": result[11],
                "optimization_type": result[12],
                "total_combinations": result[13],
            }

        except SQLAlchemyError as e:
            logger.error(f"Failed to get status: {e}", exc_info=True)
            raise ValueError(f"Database error: {e}")

    async def get_results(
        self,
        optimization_id: str,
        limit: int = 100,
        sort_by: str = "sharpe_ratio",
    ) -> Dict[str, Any]:
        """
        Get optimization results.

        Args:
            optimization_id: Optimization ID
            limit: Max number of results to return
            sort_by: Sort column ('sharpe_ratio', 'total_return', 'win_rate')

        Returns:
            Results dictionary with keys:
            - optimization_id: str
            - status: str
            - results: List[Dict] (top N results)
            - best_params: Dict
            - summary: Dict (aggregated stats)

        Raises:
            ValueError: If optimization not found
        """
        # Get status
        status = await self.get_status(optimization_id)

        # Get top results
        try:
            query = text(f"""
                SELECT params, sharpe_ratio, total_return, win_rate,
                       total_trades, max_drawdown, profit_factor,
                       rank_by_sharpe, rank_by_return, rank_by_win_rate
                FROM optimization_results
                WHERE optimization_id = :opt_id
                  AND {sort_by} IS NOT NULL
                ORDER BY {sort_by} DESC NULLS LAST
                LIMIT :limit
            """)

            with self.engine.connect() as conn:
                results = conn.execute(query, {
                    "opt_id": optimization_id,
                    "limit": limit,
                }).fetchall()

            results_list = [
                {
                    # JSONB field - already a dict if from PostgreSQL
                    "params": row[0] if isinstance(row[0], dict) else json.loads(row[0]),
                    "sharpe_ratio": float(row[1]) if row[1] else None,
                    "total_return": float(row[2]) if row[2] else None,
                    "win_rate": float(row[3]) if row[3] else None,
                    "total_trades": int(row[4]) if row[4] else 0,
                    "max_drawdown": float(row[5]) if row[5] else None,
                    "profit_factor": float(row[6]) if row[6] else None,
                    "rank_by_sharpe": int(row[7]) if row[7] else None,
                    "rank_by_return": int(row[8]) if row[8] else None,
                    "rank_by_win_rate": int(row[9]) if row[9] else None,
                }
                for row in results
            ]

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
                "results": results_list,
                "started_at": status["started_at"],
                "completed_at": status["completed_at"],
            }

        except SQLAlchemyError as e:
            logger.error(f"Failed to get results: {e}", exc_info=True)
            raise ValueError(f"Database error: {e}")
