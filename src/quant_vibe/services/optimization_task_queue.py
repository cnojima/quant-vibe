"""
Optimization Task Queue - Redis-based task distribution.

Enables async, non-blocking optimization execution by decoupling
task submission (admin_ui) from execution (optimization_worker).

Architecture:
- Admin UI publishes tasks to Redis list: "optimization:tasks"
- Worker polls Redis list and executes tasks
- Status/progress tracked in PostgreSQL + Redis pub/sub
"""

import asyncio
import json
from typing import Any, Dict, Optional
from datetime import datetime

from redis.asyncio import Redis

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc


logger = get_logger(__name__)


class OptimizationTaskQueue:
    """
    Redis-based task queue for optimization execution.

    Features:
    - Non-blocking task submission
    - FIFO task execution
    - Automatic retry on failure
    - Task cancellation support
    """

    TASK_QUEUE_KEY = "optimization:tasks"
    TASK_PREFIX = "optimization:task:"

    def __init__(self, redis_client: Redis):
        """
        Initialize task queue.

        Args:
            redis_client: Async Redis client
        """
        self.redis = redis_client

    async def publish_task(self, optimization_id: str, task_data: Dict[str, Any]) -> None:
        """
        Publish optimization task to queue.

        Args:
            optimization_id: Optimization ID
            task_data: Task configuration (strategy, dates, params, etc.)

        Raises:
            Exception: If publish fails
        """
        task = {
            "optimization_id": optimization_id,
            "data": task_data,
            "published_at": now_utc().isoformat(),
            "status": "queued",
        }

        # Store task details
        task_key = f"{self.TASK_PREFIX}{optimization_id}"
        await self.redis.setex(
            task_key,
            3600 * 24,  # 24 hour TTL
            json.dumps(task, default=str),
        )

        # Add to queue
        await self.redis.rpush(self.TASK_QUEUE_KEY, optimization_id)

        logger.info(
            f"Published optimization task {optimization_id}",
            extra={"optimization_id": optimization_id}
        )

    async def consume_task(self, timeout: int = 1) -> Optional[Dict[str, Any]]:
        """
        Consume next task from queue (blocking with timeout).

        Args:
            timeout: Blocking timeout in seconds

        Returns:
            Task data or None if queue empty
        """
        # Blocking pop from queue
        result = await self.redis.blpop(self.TASK_QUEUE_KEY, timeout=timeout)

        if not result:
            return None

        # Result is (queue_name, optimization_id)
        _, optimization_id = result

        # Get task details
        task_key = f"{self.TASK_PREFIX}{optimization_id}"
        task_json = await self.redis.get(task_key)

        if not task_json:
            logger.warning(f"Task data not found for {optimization_id}")
            return None

        task = json.loads(task_json)

        logger.info(
            f"Consumed optimization task {optimization_id}",
            extra={"optimization_id": optimization_id}
        )

        return task

    async def mark_task_running(self, optimization_id: str) -> None:
        """Mark task as running."""
        task_key = f"{self.TASK_PREFIX}{optimization_id}"
        task_json = await self.redis.get(task_key)

        if task_json:
            task = json.loads(task_json)
            task["status"] = "running"
            task["started_at"] = now_utc().isoformat()
            await self.redis.setex(
                task_key,
                3600 * 24,
                json.dumps(task, default=str),
            )

    async def mark_task_completed(self, optimization_id: str) -> None:
        """Mark task as completed."""
        task_key = f"{self.TASK_PREFIX}{optimization_id}"
        task_json = await self.redis.get(task_key)

        if task_json:
            task = json.loads(task_json)
            task["status"] = "completed"
            task["completed_at"] = now_utc().isoformat()
            await self.redis.setex(
                task_key,
                3600 * 24,
                json.dumps(task, default=str),
            )

    async def mark_task_failed(self, optimization_id: str, error: str) -> None:
        """Mark task as failed."""
        task_key = f"{self.TASK_PREFIX}{optimization_id}"
        task_json = await self.redis.get(task_key)

        if task_json:
            task = json.loads(task_json)
            task["status"] = "failed"
            task["error"] = error
            task["failed_at"] = now_utc().isoformat()
            await self.redis.setex(
                task_key,
                3600 * 24,
                json.dumps(task, default=str),
            )

    async def get_queue_size(self) -> int:
        """Get number of tasks in queue."""
        return await self.redis.llen(self.TASK_QUEUE_KEY)

    async def get_task_status(self, optimization_id: str) -> Optional[Dict[str, Any]]:
        """Get task status from Redis."""
        task_key = f"{self.TASK_PREFIX}{optimization_id}"
        task_json = await self.redis.get(task_key)

        if not task_json:
            return None

        return json.loads(task_json)

    async def cancel_task(self, optimization_id: str) -> bool:
        """
        Cancel a queued task (remove from queue).

        Args:
            optimization_id: Optimization ID

        Returns:
            True if task was cancelled (removed from queue)
        """
        # Remove from queue (if present)
        removed = await self.redis.lrem(self.TASK_QUEUE_KEY, 1, optimization_id)

        if removed:
            # Mark as cancelled in Redis
            task_key = f"{self.TASK_PREFIX}{optimization_id}"
            task_json = await self.redis.get(task_key)

            if task_json:
                task = json.loads(task_json)
                task["status"] = "cancelled"
                task["cancelled_at"] = now_utc().isoformat()
                await self.redis.setex(
                    task_key,
                    3600 * 24,
                    json.dumps(task, default=str),
                )

            logger.info(f"Cancelled queued task {optimization_id}")
            return True

        return False
