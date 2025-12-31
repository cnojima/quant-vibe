"""
Redis client for pub/sub and real-time updates.

Subscribes to topics from streaming and live trading services,
then broadcasts to WebSocket clients.
"""

import asyncio
import json
from typing import Any, Optional

import redis.asyncio as aioredis
from fastapi import WebSocket

from admin_ui.backend.config import get_settings

# Global Redis client
_redis: Optional[aioredis.Redis] = None
_pubsub: Optional[aioredis.client.PubSub] = None

# WebSocket clients for broadcasting
_websocket_clients: set[WebSocket] = set()


async def init_redis() -> None:
    """Initialize Redis connection and pub/sub."""
    global _redis, _pubsub

    if _redis is not None:
        return

    settings = get_settings()

    _redis = await aioredis.from_url(
        f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
        encoding="utf-8",
        decode_responses=True,
    )

    _pubsub = _redis.pubsub()


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis, _pubsub

    if _pubsub is not None:
        await _pubsub.close()
        _pubsub = None

    if _redis is not None:
        await _redis.close()
        _redis = None


def get_redis() -> aioredis.Redis:
    """Get Redis client."""
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis


def get_pubsub() -> aioredis.client.PubSub:
    """Get Redis pub/sub client."""
    if _pubsub is None:
        raise RuntimeError("Redis pub/sub not initialized. Call init_redis() first.")
    return _pubsub


async def subscribe_to_topics(topics: list[str]) -> None:
    """
    Subscribe to Redis pub/sub topics.

    Args:
        topics: List of topic patterns to subscribe to
    """
    pubsub = get_pubsub()
    await pubsub.psubscribe(*topics)


async def listen_to_redis() -> None:
    """
    Listen to Redis pub/sub and broadcast to WebSocket clients.

    This should be run as a background task.
    """
    pubsub = get_pubsub()

    # Subscribe to trading and system topics only (not streaming bars - too noisy)
    await subscribe_to_topics([
        # "streaming.*",  # DISABLED - too many messages (1800/sec)
        "trading.*",    # trading.signal, trading.order, trading.fill
        "system.*",     # system.heartbeat, system.error
        "heartbeat.*",  # heartbeat.live_trading, heartbeat.streaming, etc.
    ])

    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                # Forward to WebSocket clients
                await broadcast_to_websockets({
                    "topic": message["channel"],
                    "data": message["data"],
                })
    except asyncio.CancelledError:
        # Graceful shutdown
        await pubsub.unsubscribe()


async def broadcast_to_websockets(message: dict[str, Any]) -> None:
    """
    Broadcast a message to all connected WebSocket clients.

    Args:
        message: Message to broadcast (will be JSON serialized)
    """
    if not _websocket_clients:
        return

    # Send to all clients, removing disconnected ones
    disconnected = set()
    for websocket in _websocket_clients:
        try:
            await websocket.send_json(message)
        except Exception:
            disconnected.add(websocket)

    # Remove disconnected clients
    _websocket_clients.difference_update(disconnected)


def register_websocket(websocket: WebSocket) -> None:
    """Register a WebSocket client for broadcasts."""
    _websocket_clients.add(websocket)


def unregister_websocket(websocket: WebSocket) -> None:
    """Unregister a WebSocket client."""
    _websocket_clients.discard(websocket)


async def publish_message(topic: str, data: Any) -> None:
    """
    Publish a message to a Redis topic.

    Args:
        topic: Topic to publish to
        data: Data to publish (will be JSON serialized if dict/list)
    """
    redis = get_redis()

    if isinstance(data, (dict, list)):
        data = json.dumps(data)

    await redis.publish(topic, data)


async def test_connection() -> bool:
    """
    Test Redis connectivity.

    Returns:
        True if connection successful, False otherwise
    """
    try:
        redis = get_redis()
        await redis.ping()
        return True
    except Exception:
        return False
