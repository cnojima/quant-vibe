"""
Backtest Service - Centralized async backtest execution.

This service handles the complete backtest lifecycle:
1. Request validation and queuing
2. Data loading with Redis caching
3. Async backtest execution
4. Progress tracking and real-time updates
5. Result storage (database + filesystem)

Design Goals:
- Replace subprocess approach with API-based async execution
- Cache options data in Redis for repeated backtests
- Provide real-time progress updates via WebSocket
- Support concurrent backtest execution
- Store results in both PostgreSQL and CSV files
"""

import asyncio
import hashlib
import json
import pickle
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

import pandas as pd
import numpy as np
from redis.asyncio import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from quant_vibe.logging import get_logger
from quant_vibe.strategies.registry import StrategyRegistry
from quant_vibe.utils import now_utc
from quant_vibe.utils.timestamp_utils import to_utc
from backtest import OptionsBacktestEngine, BacktestReporter
from .data_service import DataService
from .cache import CacheManager


logger = get_logger(__name__)


class BacktestService:
    """
    Service for managing strategy backtests.

    Features:
    - Async execution (non-blocking)
    - Redis-based data caching
    - Real-time progress tracking via pub/sub
    - Concurrent backtest support
    - Hybrid storage (DB + CSV)
    - WebSocket support for live updates
    """

    def __init__(
        self,
        redis_client: Redis,
        db_connection_string: str,
        data_cache_ttl: int = 3600,  # 1 hour
        results_base_dir: str = "results/backtests",
        max_concurrent_backtests: int = 5,
    ):
        """
        Initialize backtest service.

        Args:
            redis_client: Async Redis client for caching and pub/sub
            db_connection_string: PostgreSQL connection string
            data_cache_ttl: Data cache TTL in seconds (default: 1 hour)
            results_base_dir: Base directory for CSV results
            max_concurrent_backtests: Maximum concurrent backtests
        """
        self.redis = redis_client

        # Get Redis URL from connection info
        redis_host = redis_client.connection_pool.connection_kwargs.get('host', 'localhost')
        redis_port = redis_client.connection_pool.connection_kwargs.get('port', 6379)
        redis_db = redis_client.connection_pool.connection_kwargs.get('db', 0)
        redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"

        # Initialize shared data service
        self.data_service = DataService(
            redis_url=redis_url,
            db_url=db_connection_string,
            cache_ttl=data_cache_ttl,
            cache_prefix="backtest:data"
        )

        # Initialize cache manager for general caching
        self.cache = CacheManager(
            redis_url=redis_url,
            default_ttl=data_cache_ttl,
            prefix="backtest"
        )

        self.db_connection_string = db_connection_string
        self.data_cache_ttl = data_cache_ttl
        self.results_base_dir = Path(results_base_dir)
        self.results_base_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent_backtests = max_concurrent_backtests

        # In-memory tracking of running backtests
        self.running_backtests: Dict[str, Dict[str, Any]] = {}

        # Create SQLAlchemy engine for sync DB operations
        self.engine = create_engine(db_connection_string)

        # Semaphore to limit concurrent backtests
        self.semaphore = asyncio.Semaphore(max_concurrent_backtests)


    # ========================================================================
    # Backtest Management
    # ========================================================================

    async def create_backtest(
        self,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        params: Dict[str, Any],
        ticker: str = "$SPX",
        timeframe: str = "5min",
        description: Optional[str] = None,
    ) -> str:
        """
        Create a new backtest task.

        Args:
            strategy_name: Strategy to backtest
            start_date: Start date for backtest
            end_date: End date for backtest
            initial_capital: Starting capital
            params: Strategy parameters
            ticker: Ticker symbol (default: $SPX)
            timeframe: Data timeframe (default: 5min)
            description: Optional description

        Returns:
            Backtest ID
        """
        backtest_id = str(uuid.uuid4())

        # Store backtest metadata in Redis
        backtest_data = {
            "id": backtest_id,
            "strategy_name": strategy_name,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "initial_capital": initial_capital,
            "params": json.dumps(params, default=str),
            "ticker": ticker,
            "timeframe": timeframe,
            "description": description or "",  # Redis doesn't accept None
            "status": "pending",
            "progress": 0.0,
            "created_at": now_utc().isoformat(),
            "started_at": "",  # Redis doesn't accept None
            "completed_at": "",  # Redis doesn't accept None
            "error": "",  # Redis doesn't accept None
        }

        # Store in Redis
        await self.redis.hset(f"backtest:{backtest_id}", mapping=backtest_data)

        # Add to pending queue
        await self.redis.rpush("backtest:queue", backtest_id)

        # Store in running backtests
        self.running_backtests[backtest_id] = backtest_data

        logger.info(
            f"Created backtest {backtest_id}",
            extra={
                "backtest_id": backtest_id,
                "strategy": strategy_name,
                "date_range": f"{start_date} to {end_date}",
            }
        )

        return backtest_id

    async def run_backtest(self, backtest_id: str) -> Dict[str, Any]:
        """
        Execute a backtest asynchronously.

        Args:
            backtest_id: Backtest ID to run

        Returns:
            Backtest results
        """
        async with self.semaphore:
            try:
                # Update status to running
                await self._update_status(backtest_id, "running", progress=0.0)

                # Get backtest metadata
                metadata = await self._get_backtest_metadata(backtest_id)
                if not metadata:
                    raise ValueError(f"Backtest {backtest_id} not found")

                # Load cached data or fetch new
                data = await self._load_data_with_cache(
                    ticker=metadata["ticker"],
                    start_date=datetime.fromisoformat(metadata["start_date"]),
                    end_date=datetime.fromisoformat(metadata["end_date"]),
                    timeframe=metadata["timeframe"],
                )

                # Progress: Data loaded (20%)
                await self._update_status(backtest_id, "running", progress=20.0)

                # Run backtest using existing engine
                results = await self._run_backtest_engine(
                    backtest_id=backtest_id,
                    strategy_name=metadata["strategy_name"],
                    data=data,
                    params=json.loads(metadata["params"]),
                    initial_capital=metadata["initial_capital"],
                )

                # Progress: Backtest complete (80%)
                await self._update_status(backtest_id, "running", progress=80.0)

                # Store results
                await self._store_results(backtest_id, results)

                # Update status to completed
                await self._update_status(backtest_id, "completed", progress=100.0)

                logger.info(f"Backtest {backtest_id} completed successfully")

                return results

            except Exception as e:
                logger.error(f"Backtest {backtest_id} failed: {str(e)}")
                await self._update_status(
                    backtest_id, "failed", error=str(e)
                )
                raise

    async def get_status(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backtest status and progress.

        Args:
            backtest_id: Backtest ID

        Returns:
            Status dictionary or None if not found
        """
        data = await self.redis.hgetall(f"backtest:{backtest_id}")
        if not data:
            return None

        # Parse stored data
        status = {
            "id": data.get("id"),
            "status": data.get("status"),
            "progress": float(data.get("progress", 0)),
            "strategy_name": data.get("strategy_name"),
            "created_at": data.get("created_at"),
            "started_at": data.get("started_at"),
            "completed_at": data.get("completed_at"),
            "error": data.get("error"),
        }

        # Add ETA if running
        if status["status"] == "running" and status["progress"] > 0:
            status["eta"] = self._calculate_eta(
                started_at=status["started_at"],
                progress=status["progress"],
            )

        return status

    async def cancel_backtest(self, backtest_id: str) -> bool:
        """
        Cancel a running backtest.

        Args:
            backtest_id: Backtest ID to cancel

        Returns:
            True if cancelled, False if not found or not running
        """
        status = await self.get_status(backtest_id)
        if not status or status["status"] not in ["pending", "running"]:
            return False

        # Update status to cancelled
        await self._update_status(backtest_id, "cancelled")

        # Remove from running backtests
        self.running_backtests.pop(backtest_id, None)

        logger.info(f"Cancelled backtest {backtest_id}")

        return True

    async def list_backtests(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List backtests with optional filtering.

        Args:
            status: Filter by status (pending, running, completed, failed, cancelled)
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of backtest metadata
        """
        # Get all backtest keys
        pattern = "backtest:*"
        cursor = "0"
        keys = []

        while cursor != 0:
            cursor, batch = await self.redis.scan(
                cursor=cursor,
                match=pattern,
                count=100,
            )
            keys.extend(batch)
            if cursor == "0":
                break

        # Filter out queue keys
        backtest_keys = [k for k in keys if not k.endswith(":queue")]

        # Get all backtest data
        backtests = []
        for key in backtest_keys:
            data = await self.redis.hgetall(key)
            if data:
                # Apply status filter if provided
                if status and data.get("status") != status:
                    continue
                backtests.append(data)

        # Sort by created_at descending
        backtests.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )

        # Apply pagination
        return backtests[offset:offset + limit]

    # ========================================================================
    # Private Methods
    # ========================================================================

    async def _get_backtest_metadata(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """Get backtest metadata from Redis."""
        return await self.redis.hgetall(f"backtest:{backtest_id}")

    async def _update_status(
        self,
        backtest_id: str,
        status: str,
        progress: Optional[float] = None,
        error: Optional[str] = None,
    ):
        """Update backtest status in Redis and publish update."""
        updates = {"status": status}

        if progress is not None:
            updates["progress"] = str(progress)

        if error:
            updates["error"] = error

        if status == "running" and not await self.redis.hexists(f"backtest:{backtest_id}", "started_at"):
            updates["started_at"] = now_utc().isoformat()

        if status in ["completed", "failed", "cancelled"]:
            updates["completed_at"] = now_utc().isoformat()

        # Update Redis
        await self.redis.hset(f"backtest:{backtest_id}", mapping=updates)

        # Publish update for WebSocket subscribers
        update_msg = {
            "backtest_id": backtest_id,
            "status": status,
            "progress": progress,
            "error": error,
            "timestamp": now_utc().isoformat(),
        }
        await self.redis.publish(
            f"backtest:updates:{backtest_id}",
            json.dumps(update_msg),
        )

    async def _load_data_with_cache(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str,
        min_dte: int = 0,
        max_dte: int = 45,
    ) -> Dict[str, pd.DataFrame]:
        """
        Load data using the shared data service.

        Returns cached data if available, otherwise loads and caches.
        """
        # Use the shared data service
        df_options, df_underlying = await self.data_service.load_backtest_data(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            min_dte=min_dte,
            max_dte=max_dte,
            timeframe=timeframe,
            use_cache=True,
            verbose=True,
        )

        # Return in the expected format
        return {
            "options": df_options,
            "underlying": df_underlying,
        }

    async def _run_backtest_engine(
        self,
        backtest_id: str,
        strategy_name: str,
        data: Dict[str, pd.DataFrame],
        params: Dict[str, Any],
        initial_capital: float,
    ) -> Dict[str, Any]:
        """
        Run backtest using the existing engine.

        This method runs in a thread pool to avoid blocking.
        """
        # Get strategy class
        strategy_class = StrategyRegistry.get_strategy(strategy_name)

        # Initialize strategy with params
        strategy = strategy_class(**params)

        # Initialize backtest engine
        engine = OptionsBacktestEngine(
            strategy=strategy,
            initial_capital=initial_capital,
        )

        # Run backtest (this is CPU-intensive, so we run it in a thread pool)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            self._run_backtest_sync,
            engine,
            data["options"],
            data["underlying"],
            backtest_id,
        )

        return results

    def _run_backtest_sync(
        self,
        engine: OptionsBacktestEngine,
        df_options: pd.DataFrame,
        df_underlying: pd.DataFrame,
        backtest_id: str,
    ) -> Dict[str, Any]:
        """
        Synchronous backtest execution.

        This runs in a thread pool executor.
        """
        # Run the backtest
        engine.run(df_options, df_underlying)

        # Generate report
        reporter = BacktestReporter(engine)
        report = reporter.generate_report()

        # Add backtest ID to results
        report["backtest_id"] = backtest_id

        return report

    async def _store_results(
        self,
        backtest_id: str,
        results: Dict[str, Any],
    ):
        """
        Store backtest results in database and filesystem.
        """
        # Store summary in database
        await self._store_results_db(backtest_id, results)

        # Store detailed results in CSV
        await self._store_results_csv(backtest_id, results)

        # Store reference in Redis
        await self.redis.hset(
            f"backtest:{backtest_id}",
            "results_stored",
            "true",
        )

    async def _store_results_db(
        self,
        backtest_id: str,
        results: Dict[str, Any],
    ):
        """Store results summary in PostgreSQL."""
        # Implementation depends on your database schema
        # This is a simplified example
        pass

    async def _store_results_csv(
        self,
        backtest_id: str,
        results: Dict[str, Any],
    ):
        """Store detailed results in CSV files."""
        # Create directory for this backtest
        backtest_dir = self.results_base_dir / backtest_id
        backtest_dir.mkdir(parents=True, exist_ok=True)

        # Save trades if present
        if "trades" in results and results["trades"] is not None:
            trades_df = pd.DataFrame(results["trades"])
            trades_df.to_csv(backtest_dir / "trades.csv", index=False)

        # Save performance metrics
        metrics_file = backtest_dir / "metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(results.get("metrics", {}), f, indent=2, default=str)

    def _calculate_eta(
        self,
        started_at: Optional[str],
        progress: float,
    ) -> Optional[str]:
        """Calculate estimated time of completion."""
        if not started_at or progress <= 0:
            return None

        try:
            started = datetime.fromisoformat(started_at)
            elapsed = (now_utc() - started).total_seconds()

            if progress >= 100:
                return None

            # Estimate remaining time
            rate = progress / elapsed  # percent per second
            remaining_progress = 100 - progress
            remaining_seconds = remaining_progress / rate

            eta = now_utc() + timedelta(seconds=remaining_seconds)
            return eta.isoformat()

        except Exception:
            return None