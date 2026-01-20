#!/usr/bin/env python3
"""
Optimization Worker - Dedicated service for running parameter optimizations.

This worker can run in API mode or Worker mode based on configuration.
"""

import asyncio
import os
import sys
import signal
import traceback
import gc
import faulthandler
from datetime import datetime
from typing import Optional, Dict, Any

import redis.asyncio as aioredis
from sqlalchemy import create_engine
import psutil

from quant_vibe.logging import get_logger
from .service import OptimizationService
from .queue.task_queue import OptimizationTaskQueue
from .config import OptimizationConfig


logger = get_logger(__name__)


class OptimizationWorker:
    """Worker for processing optimization tasks."""

    def __init__(self, config: OptimizationConfig):
        """Initialize the optimization worker.

        Args:
            config: Configuration for the optimization service
        """
        self.config = config
        self.redis_client: Optional[aioredis.Redis] = None
        self.task_queue: Optional[OptimizationTaskQueue] = None
        self.optimization_service: Optional[OptimizationService] = None
        self.shutdown_event = asyncio.Event()

        # Enable faulthandler for debugging
        faulthandler.enable(file=sys.stderr, all_threads=True)

        # Register signal handlers
        self._register_signal_handlers()

    def _register_signal_handlers(self):
        """Register signal handlers for graceful shutdown and debugging."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGSEGV, self._signal_handler)  # Segmentation fault
        signal.signal(signal.SIGABRT, self._signal_handler)  # Abort
        signal.signal(signal.SIGILL, self._signal_handler)   # Illegal instruction

    def _signal_handler(self, signum, frame):
        """Handle signals for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal {sig_name} ({signum})")

        # For fatal signals, log detailed info
        if signum in (signal.SIGSEGV, signal.SIGABRT, signal.SIGILL):
            logger.error(f"Fatal signal {sig_name} received")
            logger.error(f"Stack trace:\n{''.join(traceback.format_stack(frame))}")
            self._log_memory_stats()
            sys.exit(1)

        # For shutdown signals, trigger graceful shutdown
        logger.info("Initiating graceful shutdown...")
        self.shutdown_event.set()

    def _log_memory_stats(self):
        """Log current memory statistics."""
        try:
            process = psutil.Process()
            mem_info = process.memory_info()
            logger.info(
                f"Memory stats: RSS={mem_info.rss / 1024**3:.2f}GB, "
                f"VMS={mem_info.vms / 1024**3:.2f}GB"
            )
        except Exception as e:
            logger.warning(f"Could not get memory stats: {e}")

    def _log_system_info(self):
        """Log system information for debugging."""
        import platform
        logger.info("=" * 80)
        logger.info("System Information")
        logger.info("=" * 80)
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Platform: {platform.platform()}")
        logger.info(f"Recursion limit: {sys.getrecursionlimit()}")
        self._log_memory_stats()

    async def initialize(self):
        """Initialize worker components."""
        logger.info("=" * 80)
        logger.info("Optimization Worker Initializing")
        logger.info("=" * 80)

        self._log_system_info()

        # Initialize Redis client
        logger.info(f"Connecting to Redis: {self.config.redis_host}:{self.config.redis_port}/{self.config.redis_db}")
        self.redis_client = await aioredis.from_url(
            f"redis://{self.config.redis_host}:{self.config.redis_port}/{self.config.redis_db}",
            decode_responses=True,
        )
        logger.info("Connected to Redis")

        # Initialize task queue
        self.task_queue = OptimizationTaskQueue(self.redis_client)
        logger.info("Initialized task queue")

        # Initialize optimization service
        db_connection_string = (
            f"postgresql://{self.config.db_user}:{self.config.db_password}@"
            f"{self.config.db_host}:{self.config.db_port}/{self.config.db_name}"
        )
        self.optimization_service = OptimizationService(
            redis_client=self.redis_client,
            db_connection_string=db_connection_string,
            data_cache_ttl=self.config.data_cache_ttl,
            results_base_dir=self.config.results_base_dir,
        )
        logger.info("Initialized OptimizationService")

        logger.info("=" * 80)
        logger.info("Worker ready, waiting for tasks...")
        logger.info("=" * 80)

    async def process_task(self, task: Dict[str, Any]) -> None:
        """Process a single optimization task.

        Args:
            task: Task data from the queue
        """
        optimization_id = task["optimization_id"]
        task_data = task["data"]

        logger.info("=" * 80)
        logger.info(f"Processing optimization: {optimization_id}")
        logger.info(f"Strategy: {task_data.get('strategy_name', 'unknown')}")
        logger.info(f"Date range: {task_data.get('start_date', '')} to {task_data.get('end_date', '')}")
        logger.info("=" * 80)

        # Mark task as running
        await self.task_queue.mark_task_running(optimization_id)

        try:
            # Log memory before execution
            mem_before = psutil.Process().memory_info()
            logger.info(f"Memory before optimization: RSS={mem_before.rss / 1024**3:.2f}GB")

            # Execute optimization
            logger.info(f"Starting optimization execution for {optimization_id}...")
            await self.optimization_service.run_optimization(optimization_id)

            logger.info(f"Optimization {optimization_id} completed successfully")

            # Log memory after execution
            mem_after = psutil.Process().memory_info()
            logger.info(f"Memory after optimization: RSS={mem_after.rss / 1024**3:.2f}GB")
            logger.info(f"Memory delta: {(mem_after.rss - mem_before.rss) / 1024**3:.2f}GB")

            # Force garbage collection
            gc.collect()
            logger.info("Garbage collection completed")

            # Mark task as completed
            await self.task_queue.mark_task_completed(optimization_id)

        except Exception as e:
            logger.error(
                f"Optimization {optimization_id} failed: {e}",
                exc_info=True
            )

            # Log detailed error information
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(f"Exception args: {e.args}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")

            # Log memory at error
            self._log_memory_stats()

            # Mark task as failed
            await self.task_queue.mark_task_failed(optimization_id, str(e))

            # Force garbage collection after error
            gc.collect()

    async def run(self):
        """Main worker loop."""
        await self.initialize()

        # Main processing loop
        while not self.shutdown_event.is_set():
            try:
                # Wait for task (with timeout for checking shutdown)
                task = await asyncio.wait_for(
                    self.task_queue.consume_task(timeout=5),
                    timeout=5
                )

                if task:
                    await self.process_task(task)

            except asyncio.TimeoutError:
                # Normal timeout, check for shutdown
                continue

            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                # Continue processing (don't crash on errors)
                await asyncio.sleep(1)

        # Cleanup
        await self.cleanup()

    async def cleanup(self):
        """Clean up resources on shutdown."""
        logger.info("Worker shutting down...")

        if self.redis_client:
            await self.redis_client.close()
            logger.info("Closed Redis connection")

        logger.info("Worker shutdown complete")


async def main():
    """Main entry point for the worker."""
    # Load configuration from environment
    config = OptimizationConfig.from_environment()

    # Create and run worker
    worker = OptimizationWorker(config)

    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())