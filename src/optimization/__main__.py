#!/usr/bin/env python3
"""
Main entry point for optimization service.

Can run in two modes:
- API mode: Serves REST API endpoints for optimization management
- Worker mode: Processes optimization tasks from the queue
"""

import asyncio
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from quant_vibe.logging import get_logger
from .config import OptimizationConfig
from .worker import OptimizationWorker
from .api import routes


logger = get_logger(__name__)


def create_api_app(config: OptimizationConfig) -> FastAPI:
    """Create FastAPI app for API mode.

    Args:
        config: Service configuration

    Returns:
        Configured FastAPI app
    """
    app = FastAPI(
        title="Optimization Service API",
        description="API for managing strategy parameter optimizations",
        version="2.0.0"
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on environment
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes
    app.include_router(routes.router, prefix="/api/optimization")

    @app.on_event("startup")
    async def startup_event():
        """Initialize service on startup."""
        logger.info("Optimization API starting up...")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown."""
        logger.info("Optimization API shutting down...")

    return app


async def run_api_mode(config: OptimizationConfig):
    """Run the service in API mode.

    Args:
        config: Service configuration
    """
    logger.info("=" * 80)
    logger.info("Starting Optimization Service in API mode")
    logger.info(f"API will be available at http://{config.api_host}:{config.api_port}")
    logger.info("=" * 80)

    # Create and run FastAPI app
    app = create_api_app(config)

    config_dict = {
        "app": app,
        "host": config.api_host,
        "port": config.api_port,
        "log_level": config.log_level.lower(),
    }

    server = uvicorn.Server(uvicorn.Config(**config_dict))
    await server.serve()


async def run_worker_mode(config: OptimizationConfig):
    """Run the service in worker mode.

    Args:
        config: Service configuration
    """
    logger.info("=" * 80)
    logger.info("Starting Optimization Service in Worker mode")
    logger.info(f"Worker concurrency: {config.worker_concurrency}")
    logger.info(f"Max memory: {config.max_memory_mb}MB")
    logger.info("=" * 80)

    # Create and run worker
    worker = OptimizationWorker(config)
    await worker.run()


async def main():
    """Main entry point."""
    # Load configuration
    config = OptimizationConfig.from_environment()

    try:
        # Validate configuration
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Log configuration
    logger.info("=" * 80)
    logger.info("Optimization Service Configuration")
    logger.info("=" * 80)
    logger.info(f"Service mode: {config.service_mode}")
    logger.info(f"Redis: {config.redis_host}:{config.redis_port}/{config.redis_db}")
    logger.info(f"Database: {config.db_user}@{config.db_host}:{config.db_port}/{config.db_name}")
    logger.info(f"Log level: {config.log_level}")
    logger.info("=" * 80)

    # Run in appropriate mode
    if config.service_mode == "api":
        await run_api_mode(config)
    else:
        await run_worker_mode(config)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.error(f"Service crashed: {e}", exc_info=True)
        sys.exit(1)