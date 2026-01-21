"""
Shared data service for backtest and optimization.

This module provides a unified data loading service that handles:
- Data fetching from TimescaleDB
- Redis caching for performance
- Connection pooling
- Memory-efficient aggregation

All backtest and optimization services should use this instead of directly
calling load_options_backtest_data or implementing their own data loading.
"""

import os
import hashlib
import pickle
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from decimal import Decimal

import pandas as pd
import redis.asyncio as aioredis
from redis.asyncio import Redis
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from quant_vibe.logging import get_logger
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.utils.timestamp_utils import market_hours
from quant_vibe.utils.dataframe_utils import convert_decimals_to_float


logger = get_logger(__name__)


class DataService:
    """
    Unified data service for backtest and optimization.

    This service provides:
    - Centralized data loading from TimescaleDB
    - Redis caching with configurable TTL
    - Connection pooling for efficiency
    - Support for multiple timeframes
    - Automatic fallback to different data sources

    Example:
        ```python
        # Initialize service
        service = DataService(
            redis_url="redis://localhost:6379/0",
            db_url="postgresql://user:pass@localhost/db",
            cache_ttl=3600
        )

        # Load data (with automatic caching)
        options_df, underlying_df = await service.load_backtest_data(
            ticker="$SPX",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
            min_dte=0,
            max_dte=45,
            timeframe="5min"  # Memory efficient
        )
        ```
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        db_url: Optional[str] = None,
        cache_ttl: int = 3600,  # 1 hour default
        cache_prefix: str = "data",
        pool_size: int = 10,
        max_overflow: int = 20,
    ):
        """
        Initialize the data service.

        Args:
            redis_url: Redis connection URL (default: from env)
            db_url: Database connection URL (default: from env)
            cache_ttl: Cache time-to-live in seconds
            cache_prefix: Prefix for cache keys
            pool_size: Database connection pool size
            max_overflow: Maximum overflow connections
        """
        # Redis setup
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis_client: Optional[Redis] = None
        self._binary_redis_client: Optional[Redis] = None

        # Database setup
        self.db_url = db_url or self._get_db_url()
        self.engine = create_engine(
            self.db_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=3600,  # Recycle connections after 1 hour
            pool_pre_ping=True,  # Test connections before using
        )

        # Cache configuration
        self.cache_ttl = cache_ttl
        self.cache_prefix = cache_prefix

        # Statistics
        self.cache_hits = 0
        self.cache_misses = 0

    def _get_db_url(self) -> str:
        """Get database URL from environment."""
        # Check if using remote database
        use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"

        if use_remote:
            host = os.getenv("REMOTE_TIMESCALE_HOST")
            port = os.getenv("REMOTE_TIMESCALE_PORT", "5432")
            db = os.getenv("REMOTE_TIMESCALE_DB")
            user = os.getenv("REMOTE_TIMESCALE_USER")
            password = os.getenv("REMOTE_TIMESCALE_PASSWORD")
        else:
            host = os.getenv("TIMESCALE_HOST", "localhost")
            port = os.getenv("TIMESCALE_PORT", "5432")
            db = os.getenv("TIMESCALE_DB", "options_data")
            user = os.getenv("TIMESCALE_USER", "quantvibe")
            password = os.getenv("TIMESCALE_PASSWORD", "quantvibe_dev")

        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    async def _get_redis(self) -> Redis:
        """Get or create Redis client (text mode)."""
        if self._redis_client is None:
            self._redis_client = await aioredis.from_url(
                self.redis_url,
                decode_responses=True,
            )
        return self._redis_client

    async def _get_binary_redis(self) -> Redis:
        """Get or create Redis client (binary mode for pickle)."""
        if self._binary_redis_client is None:
            self._binary_redis_client = await aioredis.from_url(
                self.redis_url,
                decode_responses=False,
            )
        return self._binary_redis_client

    def _generate_cache_key(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int,
        max_dte: int,
        timeframe: str,
    ) -> str:
        """Generate a unique cache key for the data request."""
        # Create a unique key based on all parameters
        key_parts = [
            self.cache_prefix,
            ticker,
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            str(min_dte),
            str(max_dte),
            timeframe,
        ]

        # Add hash for extra uniqueness
        key_str = ":".join(key_parts)
        key_hash = hashlib.md5(key_str.encode()).hexdigest()[:8]

        return f"{self.cache_prefix}:{ticker}:{key_hash}"

    async def load_backtest_data(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int = 0,
        max_dte: int = 45,
        timeframe: str = "5min",
        use_cache: bool = True,
        verbose: bool = True,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load options and underlying data for backtesting.

        This is the main entry point for all data loading. It handles:
        - Cache checking and storage
        - Data fetching from TimescaleDB
        - Fallback to derived data if needed
        - Memory-efficient aggregation

        Args:
            ticker: Underlying ticker (e.g., "$SPX")
            start_date: Start date for data
            end_date: End date for data
            min_dte: Minimum days to expiration
            max_dte: Maximum days to expiration
            timeframe: Data aggregation ("1min", "5min", "15min", "1hour", "daily")
            use_cache: Whether to use Redis cache
            verbose: Print loading information

        Returns:
            Tuple of (options_df, underlying_df)

        Raises:
            ValueError: If no data is found
        """
        # Normalize ticker (remove $ if present for internal use)
        underlying_ticker = ticker.replace("$", "") if ticker.startswith("$") else ticker

        # Convert to market hours
        start_date = market_hours(start_date)[0]  # Market open
        end_date = market_hours(end_date)[1]  # Market close

        # Generate cache key
        cache_key = self._generate_cache_key(
            underlying_ticker, start_date, end_date, min_dte, max_dte, timeframe
        )

        # Try to get from cache
        if use_cache:
            cached_data = await self._get_from_cache(cache_key)
            if cached_data:
                self.cache_hits += 1
                if verbose:
                    logger.info(f"Cache hit for key: {cache_key}")
                    logger.info(f"Cache statistics: {self.cache_hits} hits, {self.cache_misses} misses")
                return cached_data["options"], cached_data["underlying"]

        # Cache miss - load from database
        self.cache_misses += 1
        if verbose:
            logger.info(f"Cache miss for key: {cache_key}")
            logger.info(f"Loading {underlying_ticker} data from TimescaleDB...")
            if timeframe != "1min":
                memory_savings = {
                    "5min": "95%",
                    "15min": "98%",
                    "1hour": "99%",
                    "daily": "99.9%"
                }
                logger.info(f"Using {timeframe} aggregation (saves ~{memory_savings.get(timeframe, '90%')} memory)")

        # Load data using existing logic
        options_df, underlying_df = await self._load_from_database(
            underlying_ticker, start_date, end_date, min_dte, max_dte, timeframe, verbose
        )

        # Store in cache
        if use_cache:
            await self._store_in_cache(cache_key, options_df, underlying_df)

        return options_df, underlying_df

    async def _load_from_database(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int,
        max_dte: int,
        timeframe: str,
        verbose: bool,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load data from TimescaleDB."""
        # Create TimescaleStore (it will use environment variables for connection)
        ts_store = TimescaleStore()

        try:
            # Load options data
            options_data = ts_store.get_options_for_backtest(
                start_date,
                end_date,
                ticker,
                min_dte=min_dte,
                max_dte=max_dte,
                timeframe=timeframe,
            )

            if not options_data.empty:
                options_data = convert_decimals_to_float(options_data)

            if options_data.empty:
                raise ValueError(
                    f"No {ticker} options data found for {start_date.date()} to {end_date.date()}"
                )

            if verbose:
                logger.info(f"Loaded {len(options_data):,} options bars")
                logger.info(f"Unique contracts: {options_data['option_ticker'].nunique():,}")

            # Load underlying data
            underlying_data = ts_store.get_underlying_bars(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
            )

            if not underlying_data.empty:
                underlying_data = convert_decimals_to_float(underlying_data)
                underlying_data = underlying_data.set_index('timestamp')
            else:
                # Fallback to deriving from options
                if verbose:
                    logger.warning("No underlying bars found, deriving from options bid/ask...")

                underlying_bars = ts_store.get_underlying_price_from_options(
                    underlying_ticker=ticker,
                    start_time=start_date,
                    end_time=end_date,
                )

                if underlying_bars:
                    underlying_data = pd.DataFrame([bar.model_dump() for bar in underlying_bars])
                    underlying_data = convert_decimals_to_float(underlying_data)
                    underlying_data = underlying_data.set_index('timestamp')
                else:
                    underlying_data = pd.DataFrame()

            if underlying_data.empty:
                raise ValueError(f"No underlying price data available for {ticker}")

            if verbose:
                logger.info(f"Loaded {len(underlying_data):,} underlying price bars")

            return options_data, underlying_data

        finally:
            # Don't close the store as it uses a pooled connection
            pass

    async def _get_from_cache(self, key: str) -> Optional[Dict[str, pd.DataFrame]]:
        """Get data from Redis cache."""
        try:
            redis = await self._get_binary_redis()
            cached = await redis.get(key)

            if cached:
                return pickle.loads(cached)

            return None

        except Exception as e:
            logger.warning(f"Cache retrieval failed: {e}")
            return None

    async def _store_in_cache(
        self,
        key: str,
        options_df: pd.DataFrame,
        underlying_df: pd.DataFrame,
    ):
        """Store data in Redis cache."""
        try:
            redis = await self._get_binary_redis()

            # Prepare data for caching
            cache_data = {
                "options": options_df,
                "underlying": underlying_df,
                "cached_at": datetime.utcnow().isoformat(),
            }

            # Serialize and store
            serialized = pickle.dumps(cache_data)
            await redis.setex(key, self.cache_ttl, serialized)

            logger.debug(f"Cached data with key: {key} (TTL: {self.cache_ttl}s)")

        except Exception as e:
            logger.warning(f"Cache storage failed: {e}")

    async def clear_cache(self, pattern: Optional[str] = None):
        """
        Clear cache entries.

        Args:
            pattern: Optional pattern to match keys (e.g., "data:SPX:*")
                    If None, clears all data cache entries
        """
        redis = await self._get_redis()

        if pattern is None:
            pattern = f"{self.cache_prefix}:*"

        keys = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            await redis.delete(*keys)
            logger.info(f"Cleared {len(keys)} cache entries matching pattern: {pattern}")
        else:
            logger.info(f"No cache entries found matching pattern: {pattern}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total * 100) if total > 0 else 0

        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "total_requests": total,
            "hit_rate": f"{hit_rate:.1f}%",
        }

    async def close(self):
        """Close connections."""
        if self._redis_client:
            await self._redis_client.close()

        if self._binary_redis_client:
            await self._binary_redis_client.close()

        self.engine.dispose()