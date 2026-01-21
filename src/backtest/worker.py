"""
Async worker for processing backtest tasks.

This module implements a worker that pulls tasks from Redis queue
and processes them asynchronously.
"""

import asyncio
import json
import signal
import sys
from typing import Optional
from datetime import datetime

from redis.asyncio import Redis

from quant_vibe.logging import get_logger
from .service import BacktestService
from .repository import BacktestRepository


logger = get_logger(__name__)


class BacktestWorker:
    """
    Worker for processing backtest tasks from Redis queue.

    Features:
    - Pulls tasks from Redis queue
    - Processes backtests asynchronously
    - Updates status in real-time
    - Handles graceful shutdown
    """

    def __init__(
        self,
        redis_client: Redis,
        backtest_service: BacktestService,
        backtest_repository: BacktestRepository,
        queue_name: str = "backtest:queue",
        poll_interval: float = 1.0,
    ):
        """
        Initialize backtest worker.

        Args:
            redis_client: Redis client for queue operations
            backtest_service: Backtest service instance
            backtest_repository: Backtest repository instance
            queue_name: Redis queue name
            poll_interval: Queue polling interval in seconds
        """
        self.redis = redis_client
        self.service = backtest_service
        self.repository = backtest_repository
        self.queue_name = queue_name
        self.poll_interval = poll_interval
        self.running = False
        self.tasks = set()  # Track running tasks

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self.running = False

    async def start(self):
        """
        Start the worker process.

        This method runs continuously, pulling tasks from the queue
        and processing them asynchronously.
        """
        logger.info("Backtest worker started")
        self.running = True

        try:
            while self.running:
                # Pull task from queue
                task_id = await self._pull_task()

                if task_id:
                    # Process task asynchronously
                    task = asyncio.create_task(self._process_task(task_id))
                    self.tasks.add(task)

                    # Clean up completed tasks
                    self.tasks = {t for t in self.tasks if not t.done()}

                else:
                    # No tasks available, wait before polling again
                    await asyncio.sleep(self.poll_interval)

        except Exception as e:
            logger.error(f"Worker error: {str(e)}")
            raise

        finally:
            # Wait for all running tasks to complete
            if self.tasks:
                logger.info(f"Waiting for {len(self.tasks)} tasks to complete")
                await asyncio.gather(*self.tasks, return_exceptions=True)

            logger.info("Backtest worker stopped")

    async def stop(self):
        """Stop the worker gracefully."""
        logger.info("Stopping backtest worker")
        self.running = False

        # Wait for running tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _pull_task(self) -> Optional[str]:
        """
        Pull a task from the Redis queue.

        Returns:
            Task ID or None if queue is empty
        """
        try:
            # Use BLPOP for blocking pop with timeout
            result = await self.redis.blpop(
                self.queue_name,
                timeout=self.poll_interval,
            )

            if result:
                _, task_id = result
                logger.info(f"Pulled task {task_id} from queue")
                return task_id

            return None

        except Exception as e:
            logger.error(f"Failed to pull task from queue: {str(e)}")
            return None

    async def _process_task(self, backtest_id: str):
        """
        Process a single backtest task.

        Args:
            backtest_id: Backtest ID to process
        """
        logger.info(f"Processing backtest {backtest_id}")

        try:
            # Update status to running in database and Redis
            self.repository.update_backtest_status(
                backtest_id=backtest_id,
                status="running",
                progress=0.0,
            )

            # Also update Redis for immediate API visibility
            await self.redis.hset(
                f"backtest:{backtest_id}",
                mapping={
                    "status": "running",
                    "progress": 0.0,
                    "started_at": datetime.utcnow().isoformat(),
                }
            )

            # Run the backtest
            results = await self.service.run_backtest(backtest_id)

            # Store results in database
            self.repository.save_backtest_results(
                backtest_id=backtest_id,
                results=results,
            )

            # Update status to completed in database and Redis
            self.repository.update_backtest_status(
                backtest_id=backtest_id,
                status="completed",
                progress=100.0,
            )

            # Also update Redis for immediate API visibility
            await self.redis.hset(
                f"backtest:{backtest_id}",
                mapping={
                    "status": "completed",
                    "progress": 100.0,
                    "completed_at": datetime.utcnow().isoformat(),
                }
            )

            # Publish completion update for WebSocket subscribers
            update_msg = {
                "status": "completed",
                "progress": 100.0,
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self.redis.publish(
                f"backtest:updates:{backtest_id}",
                json.dumps(update_msg),
            )

            logger.info(f"Backtest {backtest_id} completed successfully")

        except asyncio.CancelledError:
            # Task was cancelled, update status
            logger.warning(f"Backtest {backtest_id} was cancelled")

            # Update both database and Redis
            self.repository.update_backtest_status(
                backtest_id=backtest_id,
                status="cancelled",
            )

            # Also update Redis for immediate API visibility
            await self.redis.hset(
                f"backtest:{backtest_id}",
                mapping={
                    "status": "cancelled",
                    "completed_at": datetime.utcnow().isoformat(),
                }
            )

            # Publish cancellation update for WebSocket subscribers
            update_msg = {
                "status": "cancelled",
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self.redis.publish(
                f"backtest:updates:{backtest_id}",
                json.dumps(update_msg),
            )

            raise

        except Exception as e:
            # Task failed, update status with error
            logger.error(f"Backtest {backtest_id} failed: {str(e)}")

            # Update both database and Redis with the error
            self.repository.update_backtest_status(
                backtest_id=backtest_id,
                status="failed",
                error_message=str(e),
            )

            # Also update Redis so the error is immediately visible via API
            await self.redis.hset(
                f"backtest:{backtest_id}",
                mapping={
                    "status": "failed",
                    "error": str(e),
                    "completed_at": datetime.utcnow().isoformat(),
                }
            )

            # Publish error update for WebSocket subscribers
            update_msg = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self.redis.publish(
                f"backtest:updates:{backtest_id}",
                json.dumps(update_msg),
            )

            # Optionally, add to dead letter queue for retry
            await self._add_to_dlq(backtest_id, str(e))

    async def _add_to_dlq(self, backtest_id: str, error: str):
        """
        Add failed task to dead letter queue for potential retry.

        Args:
            backtest_id: Backtest ID
            error: Error message
        """
        dlq_entry = {
            "backtest_id": backtest_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": 0,
        }

        await self.redis.rpush(
            f"{self.queue_name}:dlq",
            json.dumps(dlq_entry),
        )

        logger.info(f"Added backtest {backtest_id} to dead letter queue")


async def main():
    """
    Main entry point for running the worker standalone.
    """
    import os

    # Get configuration from environment
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    db_url = os.getenv("DATABASE_URL", "postgresql://quantvibe:quantvibe_dev@localhost:5432/options_data")

    # Initialize Redis client
    import redis.asyncio as aioredis

    redis_client = await aioredis.from_url(
        redis_url,
        decode_responses=True,
    )

    # Initialize repository
    repository = BacktestRepository(db_url)

    # Initialize service
    service = BacktestService(
        redis_client=redis_client,
        db_connection_string=db_url,
    )

    # Initialize worker
    worker = BacktestWorker(
        redis_client=redis_client,
        backtest_service=service,
        backtest_repository=repository,
    )

    # Start worker
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down")
    finally:
        await worker.stop()
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())