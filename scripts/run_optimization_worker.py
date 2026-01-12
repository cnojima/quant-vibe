#!/usr/bin/env python3
"""
Optimization Worker - Dedicated service for running parameter optimizations.

This worker runs in a separate container from admin_ui, preventing long-running
optimizations from blocking the UI.

Architecture:
1. Admin UI publishes optimization tasks to Redis queue
2. Worker polls queue and executes tasks
3. Worker uses OptimizationService to run optimizations
4. Progress/results stored in PostgreSQL + Redis pub/sub
"""

import asyncio
import os
import sys
import signal
import traceback
import gc
import faulthandler
from pathlib import Path

# Enable faulthandler for segfault debugging
faulthandler.enable(file=sys.stderr, all_threads=True)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime
import redis.asyncio as aioredis
from sqlalchemy import create_engine

from quant_vibe.logging import get_logger
from quant_vibe.services.optimization_service import OptimizationService
from quant_vibe.services.optimization_task_queue import OptimizationTaskQueue


logger = get_logger(__name__)


# Signal handlers for debugging
def signal_handler(signum, frame):
    """Handle signals to debug crashes."""
    sig_name = signal.Signals(signum).name
    logger.error(f"Received signal {sig_name} ({signum})")
    logger.error(f"Stack trace at signal:\n{''.join(traceback.format_stack(frame))}")

    # Log memory stats
    import psutil
    process = psutil.Process()
    mem_info = process.memory_info()
    logger.error(f"Memory at crash: RSS={mem_info.rss / 1024**3:.2f}GB, VMS={mem_info.vms / 1024**3:.2f}GB")

    sys.exit(1)


# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGSEGV, signal_handler)  # Segmentation fault
signal.signal(signal.SIGABRT, signal_handler)  # Abort
signal.signal(signal.SIGILL, signal_handler)   # Illegal instruction


async def main():
    """Worker main loop."""
    logger.info("=" * 80)
    logger.info("Optimization Worker Starting")
    logger.info("=" * 80)

    # Log system info
    import platform
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {platform.platform()}")
    logger.info(f"Recursion limit: {sys.getrecursionlimit()}")

    # Check if we can import psutil
    try:
        import psutil
        process = psutil.Process()
        mem_info = process.memory_info()
        logger.info(f"Initial memory: RSS={mem_info.rss / 1024**3:.2f}GB, VMS={mem_info.vms / 1024**3:.2f}GB")
    except ImportError:
        logger.warning("psutil not available - memory tracking disabled")

    # Get configuration from environment
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_db = int(os.getenv("REDIS_DB", "0"))

    db_host = os.getenv("TIMESCALE_HOST", "localhost")
    db_port = os.getenv("TIMESCALE_PORT", "5432")
    db_name = os.getenv("TIMESCALE_DB", "options_data")
    db_user = os.getenv("TIMESCALE_USER", "quantvibe")
    db_password = os.getenv("TIMESCALE_PASSWORD", "quantvibe_dev")

    logger.info(f"Redis: {redis_host}:{redis_port}/{redis_db}")
    logger.info(f"Database: {db_user}@{db_host}:{db_port}/{db_name}")

    # Initialize Redis client
    redis_client = await aioredis.from_url(
        f"redis://{redis_host}:{redis_port}/{redis_db}",
        decode_responses=True,
    )
    logger.info("Connected to Redis")

    # Initialize task queue
    task_queue = OptimizationTaskQueue(redis_client)

    # Initialize optimization service
    db_connection_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    optimization_service = OptimizationService(
        redis_client=redis_client,
        db_connection_string=db_connection_string,
        data_cache_ttl=3600,  # 1 hour
        results_base_dir="/app/results/optimization",
    )
    logger.info("Initialized OptimizationService")

    logger.info("=" * 80)
    logger.info("Worker ready, waiting for tasks...")
    logger.info("=" * 80)

    # Main worker loop
    while True:
        try:
            # Wait for task (blocking with timeout)
            task = await task_queue.consume_task(timeout=5)

            if not task:
                # No task available, continue polling
                continue

            optimization_id = task["optimization_id"]
            task_data = task["data"]

            logger.info("=" * 80)
            logger.info(f"Processing optimization: {optimization_id}")
            logger.info("=" * 80)

            # Mark task as running
            await task_queue.mark_task_running(optimization_id)

            try:
                # Log memory before execution
                import psutil
                process = psutil.Process()
                mem_before = process.memory_info()
                logger.info(f"Memory before optimization: RSS={mem_before.rss / 1024**3:.2f}GB, VMS={mem_before.vms / 1024**3:.2f}GB")

                # Execute optimization using OptimizationService
                logger.info(f"Starting optimization execution for {optimization_id}...")

                try:
                    await optimization_service.run_optimization(optimization_id)
                except Exception as opt_error:
                    # Log detailed error with stack trace
                    logger.error(f"Optimization execution error: {opt_error}")
                    logger.error(f"Full traceback:\n{traceback.format_exc()}")

                    # Log memory at error
                    mem_error = process.memory_info()
                    logger.error(f"Memory at error: RSS={mem_error.rss / 1024**3:.2f}GB, VMS={mem_error.vms / 1024**3:.2f}GB")

                    raise  # Re-raise to be caught by outer handler

                logger.info(f"Optimization {optimization_id} completed successfully")

                # Log memory after execution
                mem_after = process.memory_info()
                logger.info(f"Memory after optimization: RSS={mem_after.rss / 1024**3:.2f}GB, VMS={mem_after.vms / 1024**3:.2f}GB")
                logger.info(f"Memory delta: {(mem_after.rss - mem_before.rss) / 1024**3:.2f}GB")

                # Force garbage collection
                gc.collect()

                # Mark task as completed
                await task_queue.mark_task_completed(optimization_id)

            except Exception as e:
                logger.error(
                    f"Optimization {optimization_id} failed: {e}",
                    exc_info=True
                )

                # Log full exception details
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception args: {e.args}")
                logger.error(f"Full traceback:\n{traceback.format_exc()}")

                # Mark task as failed
                await task_queue.mark_task_failed(optimization_id, str(e))

        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
            break

        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            # Continue processing (don't crash on errors)
            await asyncio.sleep(1)

    logger.info("Worker shutting down")
    await redis_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker crashed: {e}", exc_info=True)
        sys.exit(1)
