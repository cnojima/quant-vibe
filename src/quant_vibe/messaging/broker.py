"""Message broker abstraction for inter-service communication.

This module provides a message broker abstraction that can be implemented
by different message queue backends (Redis, RabbitMQ, etc.).
"""

import json
import os
import time
import numpy as np
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union, TYPE_CHECKING
from datetime import datetime, date
from decimal import Decimal

import redis
from pydantic import BaseModel

from .topics import Topic
from quant_vibe.utils.timestamp_utils import now_utc
from quant_vibe.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    pass


class PydanticEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Pydantic models, datetime, Decimal, and numpy types."""

    def default(self, obj):
        # Handle Pydantic models
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode='json')
        # Handle Decimal (convert to float for JSON)
        elif isinstance(obj, Decimal):
            return float(obj)
        # Handle datetime/date
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        # Handle numpy types
        elif isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
            return float(obj)
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, (np.str_, str)):
            return str(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class MessageBroker(ABC):
    """Abstract base class for message brokers.

    Provides pub/sub messaging between services with retry logic.
    Supports both Pydantic models and plain dictionaries for messages.
    """

    @abstractmethod
    def publish(self, topic: Topic, message: Union[BaseModel, Dict[str, Any]]) -> bool:
        """Publish a message to a topic.

        Args:
            topic: Topic to publish to
            message: Message data - can be a Pydantic model or dict (will be JSON serialized)

        Returns:
            True if published successfully, False otherwise
        """
        pass

    @abstractmethod
    def subscribe(self, topics: List[Topic], callback: Callable[[Topic, Union[BaseModel, Dict[str, Any]]], None]) -> None:
        """Subscribe to topics and process messages with callback.

        Args:
            topics: List of topics to subscribe to
            callback: Function to call for each message (topic, message_data)
                     message_data will be a Pydantic model if the topic has a registered schema,
                     otherwise it will be a dict
        """
        pass

    @abstractmethod
    def unsubscribe(self, topics: Optional[List[Topic]] = None) -> None:
        """Unsubscribe from topics.

        Args:
            topics: Topics to unsubscribe from (all if None)
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close broker connection."""
        pass


class RedisMessageBroker(MessageBroker):
    """Redis-based message broker implementation.

    Uses Redis pub/sub for real-time messaging between services.
    Provides automatic reconnection and exponential backoff.
    Supports automatic serialization/deserialization of Pydantic models.
    """

    # Topic to Pydantic model mapping for automatic deserialization
    TOPIC_MODEL_MAP: Dict[Topic, type] = {}

    @classmethod
    def register_topic_model(cls, topic: Topic, model_class: type) -> None:
        """Register a Pydantic model for a topic for automatic deserialization.

        Args:
            topic: Topic to register
            model_class: Pydantic model class to use for deserialization
        """
        cls.TOPIC_MODEL_MAP[topic] = model_class

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        db: Optional[int] = None,
        max_retries: int = 5,
        retry_backoff_base: float = 2.0,
    ):
        """Initialize Redis message broker.

        Args:
            host: Redis host (defaults to REDIS_HOST env var or 'localhost')
            port: Redis port (defaults to REDIS_PORT env var or 6379)
            password: Redis password (defaults to REDIS_PASSWORD env var)
            db: Redis database number (defaults to REDIS_DB env var or 0)
            max_retries: Maximum number of retry attempts
            retry_backoff_base: Base for exponential backoff (seconds)
        """
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = int(port or os.getenv("REDIS_PORT", 6379))
        self.password = password or os.getenv("REDIS_PASSWORD", None)
        self.db = int(db or os.getenv("REDIS_DB", 0))

        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base

        # Connection
        self.client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None

        # Subscription state
        self._subscribed_topics: List[Topic] = []
        self._callback: Optional[Callable[[Topic, Dict[str, Any]], None]] = None

        # Connect with retry
        self._connect()

    def _connect(self) -> None:
        """Connect to Redis with retry logic."""
        for attempt in range(self.max_retries):
            try:
                self.client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    password=self.password if self.password else None,
                    db=self.db,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )

                # Test connection
                self.client.ping()
                return

            except (redis.ConnectionError, redis.TimeoutError) as e:
                if attempt == self.max_retries - 1:
                    raise ConnectionError(
                        f"Failed to connect to Redis at {self.host}:{self.port} "
                        f"after {self.max_retries} attempts: {e}"
                    )

                # Exponential backoff
                wait_time = self.retry_backoff_base ** attempt
                time.sleep(wait_time)

    def publish(self, topic: Topic, message: Union[BaseModel, Dict[str, Any]]) -> bool:
        """Publish a message to a topic.

        Args:
            topic: Topic to publish to
            message: Message data - Pydantic model or dict (will be JSON serialized)

        Returns:
            True if published successfully, False otherwise
        """
        if not self.client:
            return False

        try:
            # Add metadata
            enriched_message = {
                "timestamp": now_utc().isoformat(),
                "topic": str(topic),
                "data": message,
            }

            # Serialize and publish (use custom encoder for Pydantic/datetime/numpy/Decimal types)
            serialized = json.dumps(enriched_message, cls=PydanticEncoder)
            self.client.publish(str(topic), serialized)
            return True

        except (redis.ConnectionError, redis.TimeoutError):
            # Retry connection
            try:
                self._connect()
                serialized = json.dumps(enriched_message, cls=PydanticEncoder)
                self.client.publish(str(topic), serialized)
                return True
            except Exception as e:
                logger.error(f"Failed to publish after reconnect: {e}")
                return False

        except TypeError as e:
            msg_type = type(message).__name__
            logger.error(f"JSON serialization error: {e}. Message type: {msg_type}")
            return False

        except Exception as e:
            logger.error(f"Unexpected publish error: {e}")
            return False

    def subscribe(self, topics: List[Topic], callback: Callable[[Topic, Dict[str, Any]], None]) -> None:
        """Subscribe to topics and process messages with callback.

        Args:
            topics: List of topics to subscribe to
            callback: Function to call for each message (topic, message_data)
        """
        if not self.client:
            raise ConnectionError("Not connected to Redis")

        self._subscribed_topics = topics
        self._callback = callback

        # Create pubsub instance
        self.pubsub = self.client.pubsub()

        # Subscribe to all topics
        topic_strs = {str(topic) for topic in topics}
        self.pubsub.subscribe(*topic_strs)

        # IMPORTANT: Consume subscription confirmation messages
        # Redis sends a confirmation message for each subscribe() call
        # We need to consume these before we can get actual data messages
        logger.info(f"Waiting for {len(topic_strs)} subscription confirmations...")

        for i in range(len(topic_strs)):
            msg = self.pubsub.get_message(timeout=1.0)
            logger.info(f"  [{i+1}/{len(topic_strs)}] Got message: {msg}")
            if msg and msg['type'] == 'subscribe':
                logger.info(f"    ✓ Subscribed to channel: {msg.get('channel')}")
            else:
                logger.warning(f"    ✗ Expected 'subscribe' confirmation, got: {msg}")

    def listen(self, timeout: Optional[float] = None) -> None:
        """Listen for messages and invoke callback.

        This is a blocking call that listens for messages indefinitely.

        Args:
            timeout: Timeout in seconds for each message poll (None = block forever)
        """
        if not self.pubsub:
            raise RuntimeError("Not subscribed to any topics")

        if not self._callback:
            raise RuntimeError("No callback registered")

        try:
            for message in self.pubsub.listen():
                if message["type"] == "message":
                    try:
                        # Deserialize message
                        data = json.loads(message["data"])

                        # Extract topic and message data
                        topic_str = data.get("topic")
                        message_data = data.get("data", {})

                        # Find matching topic enum
                        topic = None
                        for t in self._subscribed_topics:
                            if str(t) == topic_str:
                                topic = t
                                break

                        if topic:
                            # Try to deserialize to Pydantic model if registered
                            if topic in self.TOPIC_MODEL_MAP:
                                try:
                                    model_class = self.TOPIC_MODEL_MAP[topic]
                                    message_data = model_class(**message_data)
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to deserialize message to {model_class.__name__}: {e}. "
                                        f"Falling back to dict."
                                    )
                                    # Fall back to dict if deserialization fails

                            # Invoke callback
                            self._callback(topic, message_data)

                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        # Skip malformed messages
                        logger.warning(f"Skipping malformed message: {e}")
                        continue

        except KeyboardInterrupt:
            pass

    def get_message(self, timeout: float = 0.1) -> Optional[tuple[Topic, Union[BaseModel, Dict[str, Any]]]]:
        """Get a single message without blocking (non-blocking mode).

        Args:
            timeout: Timeout in seconds (0.1 = 100ms)

        Returns:
            (topic, message_data) if message received, None otherwise
            message_data will be a Pydantic model if topic has registered schema, otherwise dict
        """
        if not self.pubsub:
            logger.error("get_message() called but pubsub is None!")
            return None

        message = self.pubsub.get_message(timeout=timeout)

        if message and message["type"] == "message":
            try:
                # Deserialize message
                data = json.loads(message["data"])

                # Extract topic and message data
                topic_str = data.get("topic")
                message_data = data.get("data", {})

                # Find matching topic enum
                for topic in self._subscribed_topics:
                    if str(topic) == topic_str:
                        # Try to deserialize to Pydantic model if registered
                        if topic in self.TOPIC_MODEL_MAP:
                            try:
                                model_class = self.TOPIC_MODEL_MAP[topic]
                                message_data = model_class(**message_data)
                            except Exception as e:
                                logger.warning(
                                    f"Failed to deserialize message to {model_class.__name__}: {e}. "
                                    f"Falling back to dict."
                                )

                        # Invoke callback if registered
                        if self._callback:
                            self._callback(topic, message_data)

                        return (topic, message_data)

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                # Log parse errors for debugging
                logger.warning(f"Failed to parse Redis message: {e}. Message: {message}")
                return None

        return None

    def unsubscribe(self, topics: Optional[List[Topic]] = None) -> None:
        """Unsubscribe from topics.

        Args:
            topics: Topics to unsubscribe from (all if None)
        """
        if not self.pubsub:
            return

        if topics is None:
            # Unsubscribe from all
            self.pubsub.unsubscribe()
            self._subscribed_topics = []
        else:
            # Unsubscribe from specific topics
            topic_strs = [str(t) for t in topics]
            self.pubsub.unsubscribe(*topic_strs)
            self._subscribed_topics = [t for t in self._subscribed_topics if t not in topics]

    def close(self) -> None:
        """Close broker connection."""
        if self.pubsub:
            self.pubsub.close()
            self.pubsub = None

        if self.client:
            self.client.close()
            self.client = None
