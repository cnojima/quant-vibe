"""
Generic caching functionality for backtest and optimization services.

This module provides reusable caching components that can be used by any service
for storing and retrieving data from Redis.
"""

import hashlib
import json
import pickle
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from enum import Enum

import redis.asyncio as aioredis
from redis.asyncio import Redis

from quant_vibe.logging import get_logger


logger = get_logger(__name__)


class CacheMode(Enum):
    """Cache serialization modes."""
    TEXT = "text"      # JSON serialization (for simple data)
    BINARY = "binary"  # Pickle serialization (for complex objects like DataFrames)


class CacheManager:
    """
    Generic cache manager for Redis operations.

    This manager provides:
    - Multiple serialization modes (text/JSON, binary/pickle)
    - TTL management
    - Key pattern generation
    - Cache statistics
    - Bulk operations

    Example:
        ```python
        # Initialize cache manager
        cache = CacheManager(
            redis_url="redis://localhost:6379/0",
            default_ttl=3600,
            prefix="myservice"
        )

        # Store simple data (JSON)
        await cache.set("user:123", {"name": "John", "age": 30})

        # Store complex data (pickle)
        await cache.set_binary("dataframe:abc", my_dataframe)

        # Get with default value
        user = await cache.get("user:123", default={})

        # Bulk operations
        await cache.set_many({
            "key1": "value1",
            "key2": "value2"
        })

        # Pattern-based deletion
        await cache.delete_pattern("user:*")
        ```
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl: int = 3600,
        prefix: str = "cache",
        max_connections: int = 50,
    ):
        """
        Initialize cache manager.

        Args:
            redis_url: Redis connection URL
            default_ttl: Default time-to-live in seconds
            prefix: Default prefix for cache keys
            max_connections: Maximum Redis connections
        """
        self.redis_url = redis_url or "redis://localhost:6379/0"
        self.default_ttl = default_ttl
        self.prefix = prefix
        self.max_connections = max_connections

        # Separate clients for text and binary modes
        self._text_client: Optional[Redis] = None
        self._binary_client: Optional[Redis] = None

        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
        }

    async def _get_text_client(self) -> Redis:
        """Get or create text mode Redis client."""
        if self._text_client is None:
            self._text_client = await aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=self.max_connections,
            )
        return self._text_client

    async def _get_binary_client(self) -> Redis:
        """Get or create binary mode Redis client."""
        if self._binary_client is None:
            self._binary_client = await aioredis.from_url(
                self.redis_url,
                decode_responses=False,
                max_connections=self.max_connections,
            )
        return self._binary_client

    def make_key(self, *parts: str) -> str:
        """
        Create a cache key from parts.

        Args:
            *parts: Key components

        Returns:
            Formatted cache key

        Example:
            cache.make_key("user", "123", "profile")
            # Returns: "cache:user:123:profile"
        """
        return f"{self.prefix}:{':'.join(str(p) for p in parts)}"

    def hash_key(self, data: Union[str, Dict, List]) -> str:
        """
        Generate a hash key from data.

        Args:
            data: Data to hash

        Returns:
            MD5 hash (first 16 chars)
        """
        if isinstance(data, (dict, list)):
            data_str = json.dumps(data, sort_keys=True)
        else:
            data_str = str(data)

        return hashlib.md5(data_str.encode()).hexdigest()[:16]

    # ========================================================================
    # Text/JSON Operations
    # ========================================================================

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache (JSON mode).

        Args:
            key: Cache key
            default: Default value if not found

        Returns:
            Cached value or default
        """
        try:
            client = await self._get_text_client()
            value = await client.get(key)

            if value is None:
                self.stats["misses"] += 1
                return default

            self.stats["hits"] += 1

            # Try to parse as JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.warning(f"Cache get error for {key}: {e}")
            self.stats["errors"] += 1
            return default

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache (JSON mode).

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds

        Returns:
            Success status
        """
        try:
            client = await self._get_text_client()

            # Serialize value
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)

            # Set with TTL
            ttl = ttl or self.default_ttl
            await client.setex(key, ttl, value_str)

            self.stats["sets"] += 1
            return True

        except Exception as e:
            logger.warning(f"Cache set error for {key}: {e}")
            self.stats["errors"] += 1
            return False

    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        Get multiple values from cache.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of key-value pairs
        """
        try:
            client = await self._get_text_client()
            values = await client.mget(keys)

            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        result[key] = value

            return result

        except Exception as e:
            logger.warning(f"Cache get_many error: {e}")
            self.stats["errors"] += 1
            return {}

    async def set_many(
        self,
        data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set multiple values in cache.

        Args:
            data: Dictionary of key-value pairs
            ttl: Time-to-live in seconds

        Returns:
            Success status
        """
        try:
            client = await self._get_text_client()
            ttl = ttl or self.default_ttl

            # Use pipeline for efficiency
            pipe = client.pipeline()
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)
                pipe.setex(key, ttl, value_str)

            await pipe.execute()

            self.stats["sets"] += len(data)
            return True

        except Exception as e:
            logger.warning(f"Cache set_many error: {e}")
            self.stats["errors"] += 1
            return False

    # ========================================================================
    # Binary/Pickle Operations
    # ========================================================================

    async def get_binary(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache (binary/pickle mode).

        Args:
            key: Cache key
            default: Default value if not found

        Returns:
            Cached value or default
        """
        try:
            client = await self._get_binary_client()
            value = await client.get(key)

            if value is None:
                self.stats["misses"] += 1
                return default

            self.stats["hits"] += 1
            return pickle.loads(value)

        except Exception as e:
            logger.warning(f"Cache get_binary error for {key}: {e}")
            self.stats["errors"] += 1
            return default

    async def set_binary(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache (binary/pickle mode).

        Args:
            key: Cache key
            value: Value to cache (can be complex objects)
            ttl: Time-to-live in seconds

        Returns:
            Success status
        """
        try:
            client = await self._get_binary_client()

            # Serialize with pickle
            value_bytes = pickle.dumps(value)

            # Set with TTL
            ttl = ttl or self.default_ttl
            await client.setex(key, ttl, value_bytes)

            self.stats["sets"] += 1
            return True

        except Exception as e:
            logger.warning(f"Cache set_binary error for {key}: {e}")
            self.stats["errors"] += 1
            return False

    # ========================================================================
    # Utility Operations
    # ========================================================================

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            client = await self._get_text_client()
            return await client.exists(key) > 0
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        try:
            client = await self._get_text_client()
            deleted = await client.delete(key)
            self.stats["deletes"] += deleted
            return deleted > 0
        except Exception as e:
            logger.warning(f"Cache delete error for {key}: {e}")
            self.stats["errors"] += 1
            return False

    async def delete_many(self, keys: List[str]) -> int:
        """Delete multiple keys from cache."""
        try:
            client = await self._get_text_client()
            deleted = await client.delete(*keys)
            self.stats["deletes"] += deleted
            return deleted
        except Exception as e:
            logger.warning(f"Cache delete_many error: {e}")
            self.stats["errors"] += 1
            return 0

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Args:
            pattern: Redis pattern (e.g., "user:*")

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._get_text_client()

            # Find all matching keys
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await client.delete(*keys)
                self.stats["deletes"] += deleted
                return deleted

            return 0

        except Exception as e:
            logger.warning(f"Cache delete_pattern error: {e}")
            self.stats["errors"] += 1
            return 0

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration time for a key."""
        try:
            client = await self._get_text_client()
            return await client.expire(key, ttl)
        except Exception:
            return False

    async def ttl(self, key: str) -> int:
        """Get remaining TTL for a key."""
        try:
            client = await self._get_text_client()
            return await client.ttl(key)
        except Exception:
            return -1

    async def clear_all(self, pattern: Optional[str] = None) -> int:
        """
        Clear all cache entries.

        Args:
            pattern: Optional pattern to match

        Returns:
            Number of keys deleted
        """
        pattern = pattern or f"{self.prefix}:*"
        return await self.delete_pattern(pattern)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = (
            (self.stats["hits"] / total_requests * 100)
            if total_requests > 0
            else 0
        )

        return {
            **self.stats,
            "total_requests": total_requests,
            "hit_rate": f"{hit_rate:.1f}%",
        }

    def reset_stats(self):
        """Reset cache statistics."""
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
        }

    async def close(self):
        """Close Redis connections."""
        if self._text_client:
            await self._text_client.close()

        if self._binary_client:
            await self._binary_client.close()


# ========================================================================
# Decorator for Method Caching
# ========================================================================

def cached(
    ttl: int = 3600,
    key_prefix: Optional[str] = None,
    mode: CacheMode = CacheMode.TEXT,
):
    """
    Decorator for caching method results.

    Args:
        ttl: Time-to-live in seconds
        key_prefix: Custom key prefix
        mode: Cache mode (text/binary)

    Example:
        ```python
        class MyService:
            def __init__(self):
                self.cache = CacheManager()

            @cached(ttl=600, key_prefix="user")
            async def get_user(self, user_id: int):
                # Expensive database query
                return await db.get_user(user_id)
        ```
    """
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            # Ensure the instance has a cache manager
            if not hasattr(self, 'cache'):
                # No cache, just call the function
                return await func(self, *args, **kwargs)

            # Generate cache key
            cache_manager: CacheManager = self.cache
            key_parts = [
                key_prefix or func.__name__,
                *[str(a) for a in args],
                *[f"{k}={v}" for k, v in sorted(kwargs.items())],
            ]
            cache_key = cache_manager.make_key(*key_parts)

            # Try to get from cache
            if mode == CacheMode.BINARY:
                cached_value = await cache_manager.get_binary(cache_key)
            else:
                cached_value = await cache_manager.get(cache_key)

            if cached_value is not None:
                return cached_value

            # Call the function
            result = await func(self, *args, **kwargs)

            # Store in cache
            if mode == CacheMode.BINARY:
                await cache_manager.set_binary(cache_key, result, ttl)
            else:
                await cache_manager.set(cache_key, result, ttl)

            return result

        return wrapper
    return decorator