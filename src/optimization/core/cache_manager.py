"""
Cache management for optimization data.

This module now delegates to the shared DataService for data loading
and CacheManager for general caching operations.
"""

import hashlib
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import redis.asyncio as aioredis

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc

# Import shared components
from backtest.data_service import DataService
from backtest.cache import CacheManager


logger = get_logger(__name__)


class OptimizationCacheManager:
    """
    Manages caching of optimization data using shared components.

    This is now a thin wrapper around the shared DataService and CacheManager,
    maintaining backward compatibility while eliminating duplicate code.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db_connection_string: str,
        data_cache_ttl: int = 3600,  # 1 hour
    ):
        """Initialize cache manager with shared components.

        Args:
            redis_client: Async Redis client (text mode)
            db_connection_string: PostgreSQL connection string
            data_cache_ttl: Cache TTL in seconds
        """
        self.redis = redis_client
        self.db_connection_string = db_connection_string
        self.data_cache_ttl = data_cache_ttl

        # Get Redis URL from connection info
        redis_host = redis_client.connection_pool.connection_kwargs.get('host', 'localhost')
        redis_port = redis_client.connection_pool.connection_kwargs.get('port', 6379)
        redis_db = redis_client.connection_pool.connection_kwargs.get('db', 0)
        redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"

        # Initialize shared components
        self.data_service = DataService(
            redis_url=redis_url,
            db_url=db_connection_string,
            cache_ttl=data_cache_ttl,
            cache_prefix="optimization:data"
        )

        self.cache_manager = CacheManager(
            redis_url=redis_url,
            default_ttl=data_cache_ttl,
            prefix="optimization"
        )

        logger.info("[Cache] Initialized with shared DataService and CacheManager")

    def generate_cache_key(
        self,
        underlying_ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int = 0,
        max_dte: int = 60,
        timeframe: str = "5min",
    ) -> str:
        """Generate cache key for data lookup.

        Args:
            underlying_ticker: Underlying ticker symbol
            start_date: Start date for data
            end_date: End date for data
            min_dte: Minimum days to expiration
            max_dte: Maximum days to expiration
            timeframe: Time aggregation

        Returns:
            Cache key string
        """
        key_parts = {
            "ticker": underlying_ticker.upper(),
            "start": start_date.strftime("%Y%m%d"),
            "end": end_date.strftime("%Y%m%d"),
            "min_dte": min_dte,
            "max_dte": max_dte,
            "timeframe": timeframe,
        }

        # Create deterministic hash
        key_str = "|".join(f"{k}={v}" for k, v in sorted(key_parts.items()))
        key_hash = hashlib.md5(key_str.encode()).hexdigest()[:8]

        return f"optimization:data:{key_hash}"

    async def get_cached_data(
        self,
        underlying_ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int = 0,
        max_dte: int = 60,
        timeframe: str = "5min",
    ) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
        """Get cached data or load and cache it.

        This method now delegates to the shared DataService which handles
        all caching and data loading logic.

        Args:
            underlying_ticker: Underlying ticker symbol
            start_date: Start date for data
            end_date: End date for data
            min_dte: Minimum days to expiration
            max_dte: Maximum days to expiration
            timeframe: Time aggregation

        Returns:
            Tuple of (options_df, underlying_df) or None if loading fails
        """
        try:
            # Delegate to shared data service
            options_df, underlying_df = await self.data_service.load_backtest_data(
                ticker=underlying_ticker,
                start_date=start_date,
                end_date=end_date,
                min_dte=min_dte,
                max_dte=max_dte,
                timeframe=timeframe,
                use_cache=True,
                verbose=False,  # Less verbose for optimization runs
            )

            logger.info(
                f"[Cache] Loaded {len(options_df):,} option rows, "
                f"{len(underlying_df):,} underlying rows"
            )

            return options_df, underlying_df

        except Exception as e:
            logger.error(f"[Cache] Error loading data: {e}")
            return None

    async def store_cached_data(
        self,
        cache_key: str,
        options_df: pd.DataFrame,
        underlying_df: pd.DataFrame,
        metadata: Dict[str, Any],
    ) -> bool:
        """Store data in cache.

        Note: The shared DataService handles caching automatically,
        so this method is maintained for backward compatibility but
        doesn't need to do anything.

        Args:
            cache_key: Cache key (ignored)
            options_df: Options data (ignored)
            underlying_df: Underlying data (ignored)
            metadata: Cache metadata (ignored)

        Returns:
            Always returns True for compatibility
        """
        # Data is automatically cached by DataService
        logger.debug(f"[Cache] Data automatically cached by DataService")
        return True

    async def load_data_with_cache(
        self,
        underlying_ticker: str,
        start_date: datetime,
        end_date: datetime,
        min_dte: int = 0,
        max_dte: int = 60,
        timeframe: str = "5min",
        verbose: bool = False,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load data with caching support.

        This is the main entry point for optimization data loading.
        It delegates to the shared DataService for consistent behavior.

        Args:
            underlying_ticker: Underlying ticker symbol
            start_date: Start date
            end_date: End date
            min_dte: Minimum days to expiration
            max_dte: Maximum days to expiration
            timeframe: Time aggregation
            verbose: Print loading information

        Returns:
            Tuple of (options_df, underlying_df)

        Raises:
            ValueError: If data cannot be loaded
        """
        # Delegate to shared data service
        result = await self.data_service.load_backtest_data(
            ticker=underlying_ticker,
            start_date=start_date,
            end_date=end_date,
            min_dte=min_dte,
            max_dte=max_dte,
            timeframe=timeframe,
            use_cache=True,
            verbose=verbose,
        )

        if result is None or len(result) != 2:
            raise ValueError(f"Failed to load data for {underlying_ticker}")

        return result

    async def _update_cache_stats(self, cache_key: str):
        """Update cache statistics.

        Args:
            cache_key: Cache key that was accessed
        """
        try:
            # Track in general cache
            stats_key = self.cache_manager.make_key("stats", "access")
            await self.cache_manager.set(stats_key, {
                "last_access": now_utc().isoformat(),
                "cache_key": cache_key,
            })

            # Increment hit counter
            counter_key = self.cache_manager.make_key("stats", "hits")
            await self.redis.incr(counter_key)

        except Exception as e:
            logger.debug(f"[Cache] Could not update stats: {e}")

    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        # Get stats from shared components
        data_stats = self.data_service.get_cache_stats()
        cache_stats = self.cache_manager.get_stats()

        return {
            "data_service": data_stats,
            "cache_manager": cache_stats,
            "combined": {
                "total_hits": data_stats["cache_hits"] + cache_stats["hits"],
                "total_misses": data_stats["cache_misses"] + cache_stats["misses"],
                "data_hit_rate": data_stats.get("hit_rate", "0%"),
                "general_hit_rate": cache_stats.get("hit_rate", "0%"),
            }
        }

    async def clear_cache(self, pattern: Optional[str] = None):
        """Clear cache entries.

        Args:
            pattern: Optional pattern to match keys
        """
        # Clear from both shared components
        await self.data_service.clear_cache(pattern)

        if pattern:
            await self.cache_manager.delete_pattern(pattern)
        else:
            await self.cache_manager.clear_all()

        logger.info(f"[Cache] Cleared cache entries matching: {pattern or '*'}")

    async def close(self):
        """Close connections."""
        await self.data_service.close()
        await self.cache_manager.close()