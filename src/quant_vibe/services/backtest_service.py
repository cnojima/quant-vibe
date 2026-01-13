"""
Backtest Service - Centralized async backtest execution.

This service handles the complete backtest lifecycle:
1. Data loading with Redis caching (reuses optimization cache)
2. Async backtest execution (non-blocking)
3. Progress tracking and real-time updates
4. Database result storage
5. Cancellation support

Design Goals:
- Replace subprocess approach with in-process async execution
- Reuse Redis caching from OptimizationService
- Track progress with real-time updates
- Support cancellation of running backtests
- Store results in database for immediate access

Key Differences from OptimizationService:
- Single backtest execution (not grid search)
- Simpler progress tracking (no permutation count)
- Direct strategy execution (no parameter iteration)
"""

import asyncio
import hashlib
import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from redis.asyncio import Redis
from sqlalchemy import create_engine

from quant_vibe.logging import get_logger
from quant_vibe.strategies.registry import StrategyRegistry
from quant_vibe.utils import (
    load_options_backtest_data,
    now_utc,
    save_backtest_to_db,
)
from quant_vibe.utils.timestamp_utils import to_utc
from backtest.options_engine import OptionsBacktestEngine


logger = get_logger(__name__)


class BacktestService:
    """
    Service for managing async backtest execution.

    Features:
    - Async execution (non-blocking)
    - Redis-based data caching
    - Real-time progress tracking
    - Database result storage
    - Cancellation support
    """

    def __init__(
        self,
        redis_client: Redis,
        db_connection_string: str,
        data_cache_ttl: int = 3600,  # 1 hour
        results_base_dir: str = "reports/backtests",
    ):
        """
        Initialize backtest service.

        Args:
            redis_client: Async Redis client for caching and pub/sub
            db_connection_string: PostgreSQL connection string
            data_cache_ttl: Data cache TTL in seconds (default: 1 hour)
            results_base_dir: Base directory for CSV results (legacy)
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

        # In-memory tracking of running backtests
        self.running_backtests: Dict[str, Dict[str, Any]] = {}

        # Create SQLAlchemy engine for sync DB operations
        self.engine = create_engine(db_connection_string)

    async def _get_binary_redis(self) -> Redis:
        """Get or create binary-safe Redis client."""
        if self._binary_redis is None:
            self._binary_redis = await self._binary_redis_factory()
        return self._binary_redis

    # ========================================================================
    # Data Loading & Caching
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
        """
        Generate cache key for data loading.

        Args:
            ticker: Underlying ticker
            start_date: Start date
            end_date: End date
            min_dte: Minimum DTE
            max_dte: Maximum DTE
            timeframe: Data timeframe

        Returns:
            Cache key string
        """
        # Create deterministic hash of parameters
        params = f"{ticker}:{start_date.isoformat()}:{end_date.isoformat()}:{min_dte}:{max_dte}:{timeframe}"
        hash_key = hashlib.md5(params.encode()).hexdigest()[:16]
        return f"backtest:data:{hash_key}"

    async def _load_data_with_cache(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int,
        max_dte: int,
        timeframe: str,
        db_profile: Optional[str] = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load backtest data with Redis caching.

        Args:
            ticker: Underlying ticker
            start_date: Start date
            end_date: End date
            min_dte: Minimum DTE
            max_dte: Maximum DTE
            timeframe: Data timeframe
            db_profile: Database profile (optional)

        Returns:
            Tuple of (options_data, underlying_data)
        """
        cache_key = self._generate_cache_key(
            ticker, start_date, end_date, min_dte, max_dte, timeframe
        )

        # Try to get from cache
        binary_redis = await self._get_binary_redis()
        cached_data = await binary_redis.get(cache_key)

        if cached_data:
            logger.info(f"Cache HIT for {cache_key}")
            try:
                # Unpickle the cached data
                data = pickle.loads(cached_data)
                options_data = data['options_data']
                underlying_data = data['underlying_data']
                logger.info(f"Loaded from cache: {len(options_data):,} options bars, {len(underlying_data):,} underlying bars")
                return options_data, underlying_data
            except Exception as e:
                logger.warning(f"Failed to unpickle cached data: {e}, will reload from database")

        # Cache miss - load from database
        logger.info(f"Cache MISS for {cache_key}, loading from database")

        options_data, underlying_data = load_options_backtest_data(
            underlying_ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            min_dte=min_dte,
            max_dte=max_dte,
            verbose=True,
            db_profile=db_profile,
            timeframe=timeframe,
        )

        # Cache the data
        try:
            data_to_cache = {
                'options_data': options_data,
                'underlying_data': underlying_data,
            }
            pickled_data = pickle.dumps(data_to_cache, protocol=pickle.HIGHEST_PROTOCOL)
            await binary_redis.setex(cache_key, self.data_cache_ttl, pickled_data)
            logger.info(f"Cached data with key {cache_key} (TTL: {self.data_cache_ttl}s)")
        except Exception as e:
            logger.warning(f"Failed to cache data: {e}")

        return options_data, underlying_data

    # ========================================================================
    # Backtest Execution
    # ========================================================================

    async def create_backtest(
        self,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 100000.0,
        parameters: Optional[Dict[str, Any]] = None,
        min_dte: int = 0,
        max_dte: int = 60,
        timeframe: str = "5min",
        ticker: str = "SPX",
        db_profile: Optional[str] = None,
        backtest_id: Optional[str] = None,
    ) -> str:
        """
        Create a new backtest (does not start execution).

        Args:
            strategy_name: Strategy name
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Initial capital
            parameters: Strategy parameters (optional, uses defaults if not provided)
            min_dte: Minimum DTE for options
            max_dte: Maximum DTE for options
            timeframe: Data timeframe (1min, 5min, 15min, 1hour, daily)
            ticker: Underlying ticker
            db_profile: Database profile (optional)
            backtest_id: Optional backtest ID (auto-generated if not provided)

        Returns:
            Backtest ID
        """
        # Use provided ID or generate one
        if backtest_id is None:
            backtest_id = f"{strategy_name}_{now_utc().strftime('%Y%m%d_%H%M%S')}"

        # Validate strategy exists by checking available strategies
        available_strategies = StrategyRegistry.list_strategies()
        if strategy_name not in available_strategies:
            raise ValueError(
                f"Strategy '{strategy_name}' not found in registry. "
                f"Available strategies: {', '.join(available_strategies)}"
            )

        # Get default parameters and merge with provided params
        default_params = StrategyRegistry.get_default_params(strategy_name)
        merged_params = {**default_params, **(parameters or {})}

        # Initialize backtest state
        self.running_backtests[backtest_id] = {
            "backtest_id": backtest_id,
            "strategy_name": strategy_name,
            "status": "pending",
            "progress": 0,
            "message": "Backtest created, waiting to start",
            "created_at": now_utc().isoformat(),
            "started_at": None,
            "completed_at": None,
            "error": None,
            "config": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "initial_capital": initial_capital,
                "parameters": merged_params,
                "min_dte": min_dte,
                "max_dte": max_dte,
                "timeframe": timeframe,
                "ticker": ticker,
                "db_profile": db_profile,
            },
        }

        # Publish status update
        await self._publish_status(backtest_id)

        logger.info(f"Created backtest {backtest_id}")
        return backtest_id

    async def run_backtest(self, backtest_id: str):
        """
        Run a backtest asynchronously.

        Args:
            backtest_id: Backtest ID to run

        Raises:
            ValueError: If backtest not found or already running
        """
        if backtest_id not in self.running_backtests:
            raise ValueError(f"Backtest {backtest_id} not found")

        backtest_state = self.running_backtests[backtest_id]

        if backtest_state["status"] == "running":
            raise ValueError(f"Backtest {backtest_id} is already running")

        # Update status
        backtest_state["status"] = "running"
        backtest_state["started_at"] = now_utc().isoformat()
        backtest_state["progress"] = 5
        backtest_state["message"] = "Loading data from cache/database"
        await self._publish_status(backtest_id)

        try:
            config = backtest_state["config"]

            # Parse dates
            start_date = datetime.fromisoformat(config["start_date"])
            end_date = datetime.fromisoformat(config["end_date"])

            # Load data with caching
            options_data, underlying_data = await self._load_data_with_cache(
                ticker=config["ticker"],
                start_date=start_date,
                end_date=end_date,
                min_dte=config["min_dte"],
                max_dte=config["max_dte"],
                timeframe=config["timeframe"],
                db_profile=config.get("db_profile"),
            )

            # Update progress
            backtest_state["progress"] = 20
            backtest_state["message"] = f"Data loaded: {len(options_data):,} options bars"
            await self._publish_status(backtest_id)

            # Create strategy instance
            strategy = StrategyRegistry.create_strategy(
                strategy_name=backtest_state["strategy_name"],
                params=config["parameters"],
                validate=True,
            )

            # Update progress
            backtest_state["progress"] = 30
            backtest_state["message"] = "Running backtest engine"
            await self._publish_status(backtest_id)

            # Run backtest (this is synchronous, but we'll run it in executor)
            engine = OptionsBacktestEngine(initial_capital=config["initial_capital"])

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                engine.run,
                strategy,
                underlying_data,
                options_data,
                start_date,
                end_date,
            )

            # Update progress
            backtest_state["progress"] = 80
            backtest_state["message"] = "Saving results to database"
            await self._publish_status(backtest_id)

            # Save to database
            await loop.run_in_executor(
                None,
                save_backtest_to_db,
                backtest_id,
                backtest_state["strategy_name"],
                start_date,
                end_date,
                config["initial_capital"],
                results,
                config["parameters"],
                1,  # max_positions
                True,  # verbose
                config.get("db_profile"),
            )

            # Update progress
            backtest_state["progress"] = 100
            backtest_state["status"] = "completed"
            backtest_state["completed_at"] = now_utc().isoformat()
            backtest_state["message"] = "Backtest completed successfully"
            backtest_state["results_summary"] = {
                "total_trades": len(results.get("trades", [])),
                "equity_points": len(results.get("equity_curve", [])),
            }
            await self._publish_status(backtest_id)

            logger.info(f"Backtest {backtest_id} completed successfully")

        except asyncio.CancelledError:
            # Backtest was cancelled
            backtest_state["status"] = "cancelled"
            backtest_state["completed_at"] = now_utc().isoformat()
            backtest_state["message"] = "Backtest cancelled by user"
            await self._publish_status(backtest_id)
            logger.info(f"Backtest {backtest_id} cancelled")
            raise

        except Exception as e:
            # Backtest failed
            backtest_state["status"] = "failed"
            backtest_state["completed_at"] = now_utc().isoformat()
            backtest_state["error"] = str(e)
            backtest_state["message"] = f"Backtest failed: {str(e)}"
            await self._publish_status(backtest_id)
            logger.error(f"Backtest {backtest_id} failed: {e}", exc_info=True)
            raise

    async def cancel_backtest(self, backtest_id: str) -> bool:
        """
        Cancel a running backtest.

        Args:
            backtest_id: Backtest ID to cancel

        Returns:
            True if cancelled, False if not running

        Note: Cancellation is cooperative - the backtest must check for cancellation.
        """
        if backtest_id not in self.running_backtests:
            raise ValueError(f"Backtest {backtest_id} not found")

        backtest_state = self.running_backtests[backtest_id]

        if backtest_state["status"] != "running":
            return False

        # Mark as cancelled (the running task should check this)
        backtest_state["status"] = "cancelled"
        backtest_state["completed_at"] = now_utc().isoformat()
        backtest_state["message"] = "Cancellation requested"
        await self._publish_status(backtest_id)

        logger.info(f"Backtest {backtest_id} cancellation requested")
        return True

    async def get_status(self, backtest_id: str) -> Dict[str, Any]:
        """
        Get backtest status.

        Args:
            backtest_id: Backtest ID

        Returns:
            Status dictionary

        Raises:
            ValueError: If backtest not found
        """
        if backtest_id not in self.running_backtests:
            raise ValueError(f"Backtest {backtest_id} not found")

        return self.running_backtests[backtest_id].copy()

    # ========================================================================
    # Progress Tracking
    # ========================================================================

    async def _publish_status(self, backtest_id: str):
        """
        Publish backtest status update to Redis pub/sub.

        Args:
            backtest_id: Backtest ID
        """
        if backtest_id not in self.running_backtests:
            return

        status = self.running_backtests[backtest_id]
        channel = f"backtest:status:{backtest_id}"

        try:
            await self.redis.publish(
                channel,
                json.dumps({
                    "backtest_id": backtest_id,
                    "status": status["status"],
                    "progress": status["progress"],
                    "message": status["message"],
                    "timestamp": now_utc().isoformat(),
                })
            )
        except Exception as e:
            logger.warning(f"Failed to publish status update: {e}")

    # ========================================================================
    # Cleanup
    # ========================================================================

    async def clear_cache(self, cache_key: Optional[str] = None):
        """
        Clear data cache.

        Args:
            cache_key: Specific cache key to clear (or all if None)
        """
        binary_redis = await self._get_binary_redis()

        if cache_key:
            await binary_redis.delete(cache_key)
            logger.info(f"Cleared cache key: {cache_key}")
        else:
            # Clear all backtest data cache keys
            keys = await binary_redis.keys("backtest:data:*")
            if keys:
                await binary_redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} backtest data cache keys")

    async def cleanup_completed(self, max_age_seconds: int = 3600):
        """
        Clean up completed backtests from memory.

        Args:
            max_age_seconds: Max age for completed backtests (default: 1 hour)
        """
        now = now_utc()
        to_remove = []

        for backtest_id, state in self.running_backtests.items():
            if state["status"] in ("completed", "failed", "cancelled"):
                completed_at = datetime.fromisoformat(state["completed_at"])
                age = (now - completed_at).total_seconds()

                if age > max_age_seconds:
                    to_remove.append(backtest_id)

        for backtest_id in to_remove:
            del self.running_backtests[backtest_id]
            logger.info(f"Cleaned up backtest {backtest_id}")

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} completed backtests")

    async def close(self):
        """Close Redis connections."""
        if self._binary_redis:
            await self._binary_redis.close()
