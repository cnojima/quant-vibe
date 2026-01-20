"""
Cache management for optimization data.

Handles Redis-based caching of options and underlying data for optimization runs.
"""

import hashlib
import pickle
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import redis.asyncio as aioredis
from sqlalchemy import create_engine, text

from quant_vibe.logging import get_logger
from quant_vibe.utils import load_options_backtest_data, now_utc


logger = get_logger(__name__)


class OptimizationCacheManager:
    """Manages caching of optimization data in Redis."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db_connection_string: str,
        data_cache_ttl: int = 3600,  # 1 hour
    ):
        """Initialize cache manager.

        Args:
            redis_client: Async Redis client (text mode)
            db_connection_string: PostgreSQL connection string
            data_cache_ttl: Cache TTL in seconds
        """
        self.redis = redis_client
        self.db_connection_string = db_connection_string
        self.data_cache_ttl = data_cache_ttl

        # Create binary Redis client for pickle data
        self._binary_redis = None
        self._binary_redis_factory = self._create_binary_client_factory()

    def _create_binary_client_factory(self):
        """Create factory for binary Redis client."""
        # Extract connection info from main client
        redis_url = str(self.redis.connection_pool.connection_kwargs.get('host', 'localhost'))
        redis_port = self.redis.connection_pool.connection_kwargs.get('port', 6379)
        redis_db = self.redis.connection_pool.connection_kwargs.get('db', 0)

        async def create_binary_client():
            return await aioredis.from_url(
                f"redis://{redis_url}:{redis_port}/{redis_db}",
                decode_responses=False,  # Return bytes for pickle
            )

        return create_binary_client

    async def _get_binary_redis(self) -> aioredis.Redis:
        """Get or create binary Redis client for pickle operations."""
        if self._binary_redis is None:
            self._binary_redis = await self._binary_redis_factory()
        return self._binary_redis

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

        Args:
            underlying_ticker: Underlying ticker symbol
            start_date: Start date for data
            end_date: End date for data
            min_dte: Minimum days to expiration
            max_dte: Maximum days to expiration
            timeframe: Time aggregation

        Returns:
            Tuple of (options_df, underlying_df) or None if not cached
        """
        cache_key = self.generate_cache_key(
            underlying_ticker, start_date, end_date, min_dte, max_dte, timeframe
        )

        logger.info(f"[Cache] Checking cache for key: {cache_key}")

        # Try to get from cache
        binary_redis = await self._get_binary_redis()
        cached_data = await binary_redis.get(cache_key)

        if cached_data:
            logger.info(f"[Cache] HIT for {cache_key}")
            try:
                # Update access stats
                await self._update_cache_stats(cache_key)

                # Unpickle the data
                data = pickle.loads(cached_data)
                options_df = pd.DataFrame(data['options_data'])
                underlying_df = pd.DataFrame(data['underlying_data'])

                logger.info(
                    f"[Cache] Loaded {len(options_df):,} option rows, "
                    f"{len(underlying_df):,} underlying rows from cache"
                )

                return options_df, underlying_df

            except Exception as e:
                logger.error(f"[Cache] Error loading cached data: {e}")
                # Delete corrupted cache entry
                await binary_redis.delete(cache_key)
                return None

        logger.info(f"[Cache] MISS for {cache_key}")
        return None

    async def store_cached_data(
        self,
        cache_key: str,
        options_df: pd.DataFrame,
        underlying_df: pd.DataFrame,
        metadata: Dict[str, Any],
    ) -> bool:
        """Store data in cache.

        Args:
            cache_key: Cache key
            options_df: Options data
            underlying_df: Underlying data
            metadata: Cache metadata

        Returns:
            True if stored successfully
        """
        try:
            # Prepare data for pickling
            cache_data = {
                'options_data': options_df.to_dict('records'),
                'underlying_data': underlying_df.to_dict('records'),
                'metadata': {
                    'cached_at': now_utc().isoformat(),
                    'options_rows': len(options_df),
                    'underlying_rows': len(underlying_df),
                    **metadata
                }
            }

            # Pickle and store
            binary_redis = await self._get_binary_redis()
            pickled_data = pickle.dumps(cache_data, protocol=pickle.HIGHEST_PROTOCOL)

            # Store with TTL
            await binary_redis.setex(
                cache_key,
                self.data_cache_ttl,
                pickled_data
            )

            # Store metadata
            await self._store_cache_metadata(
                cache_key,
                metadata['underlying_ticker'],
                metadata['start_date'],
                metadata['end_date'],
                metadata['timeframe'],
                len(options_df),
                len(underlying_df),
                len(pickled_data),
            )

            logger.info(
                f"[Cache] Stored {len(options_df):,} option rows, "
                f"{len(underlying_df):,} underlying rows "
                f"({len(pickled_data) / 1024 / 1024:.2f} MB) with TTL={self.data_cache_ttl}s"
            )

            return True

        except Exception as e:
            logger.error(f"[Cache] Error storing data: {e}")
            return False

    async def _store_cache_metadata(
        self,
        cache_key: str,
        underlying_ticker: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str,
        num_options_rows: int,
        num_underlying_rows: int,
        data_size_bytes: int,
    ) -> None:
        """Store cache metadata in PostgreSQL for monitoring.

        Args:
            cache_key: Redis cache key
            underlying_ticker: Ticker symbol
            start_date: Data start date
            end_date: Data end date
            timeframe: Time aggregation
            num_options_rows: Number of option rows
            num_underlying_rows: Number of underlying rows
            data_size_bytes: Size of cached data in bytes
        """
        try:
            engine = create_engine(self.db_connection_string)

            query = text("""
                INSERT INTO optimization_cache_status
                (cache_key, underlying_ticker, start_date, end_date, timeframe,
                 num_options_rows, num_underlying_rows, data_size_mb,
                 created_at, last_accessed_at, hit_count)
                VALUES
                (:cache_key, :ticker, :start_date, :end_date, :timeframe,
                 :num_options, :num_underlying, :size_mb,
                 :created_at, :accessed_at, 1)
                ON CONFLICT (cache_key) DO UPDATE SET
                    hit_count = optimization_cache_status.hit_count + 1,
                    last_accessed_at = EXCLUDED.last_accessed_at
            """)

            with engine.connect() as conn:
                conn.execute(
                    query,
                    {
                        "cache_key": cache_key,
                        "ticker": underlying_ticker,
                        "start_date": start_date,
                        "end_date": end_date,
                        "timeframe": timeframe,
                        "num_options": num_options_rows,
                        "num_underlying": num_underlying_rows,
                        "size_mb": round(data_size_bytes / 1024 / 1024, 2),
                        "created_at": now_utc(),
                        "accessed_at": now_utc(),
                    }
                )
                conn.commit()

        except Exception as e:
            logger.error(f"[Cache] Error storing metadata: {e}")

    async def _update_cache_stats(self, cache_key: str) -> None:
        """Update cache hit statistics.

        Args:
            cache_key: Cache key
        """
        try:
            engine = create_engine(self.db_connection_string)

            query = text("""
                UPDATE optimization_cache_status
                SET hit_count = hit_count + 1,
                    last_accessed_at = :accessed_at
                WHERE cache_key = :cache_key
            """)

            with engine.connect() as conn:
                conn.execute(
                    query,
                    {"cache_key": cache_key, "accessed_at": now_utc()}
                )
                conn.commit()

        except Exception as e:
            logger.error(f"[Cache] Error updating stats: {e}")

    async def clear_cache(self, cache_key: Optional[str] = None) -> int:
        """Clear cached data.

        Args:
            cache_key: Specific cache key or None for all optimization data

        Returns:
            Number of keys deleted
        """
        try:
            binary_redis = await self._get_binary_redis()

            if cache_key:
                # Delete specific key
                result = await binary_redis.delete(cache_key)
                logger.info(f"[Cache] Deleted key: {cache_key}")
                return result

            else:
                # Delete all optimization data keys
                pattern = "optimization:data:*"
                keys = []
                async for key in binary_redis.scan_iter(match=pattern):
                    keys.append(key)

                if keys:
                    result = await binary_redis.delete(*keys)
                    logger.info(f"[Cache] Deleted {result} keys matching {pattern}")
                    return result

                return 0

        except Exception as e:
            logger.error(f"[Cache] Error clearing cache: {e}")
            return 0