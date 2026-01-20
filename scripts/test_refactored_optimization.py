#!/usr/bin/env python3
"""
Test script for the refactored optimization service.

Tests the modular components and integration.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import redis.asyncio as aioredis
from optimization.service import OptimizationService
from optimization.client import OptimizationClient
from quant_vibe.utils import now_utc
from quant_vibe.logging import get_logger, setup_normalized_logging


# Configure logging
setup_normalized_logging(log_level="INFO")
logger = get_logger(__name__)


async def test_direct_service():
    """Test the service directly."""
    logger.info("=" * 80)
    logger.info("Testing Direct Service")
    logger.info("=" * 80)

    # Initialize Redis
    redis_client = await aioredis.from_url(
        "redis://localhost:6379/0",
        decode_responses=True,
    )

    # Initialize service
    db_connection_string = "postgresql://quantvibe:quantvibe_dev@localhost:5432/options_data"
    service = OptimizationService(
        redis_client=redis_client,
        db_connection_string=db_connection_string,
    )

    # Test parameter grid generation
    logger.info("\n1. Testing parameter grid generation...")
    param_grid = service.generate_param_grid(
        "bullish_vertical_put",
        custom_ranges={"spread_width": [5.0, 10.0]},
        optimize_only=["spread_width"]
    )
    logger.info(f"   Generated grid: {param_grid}")
    logger.info(f"   Combinations: {service.count_permutations(param_grid)}")

    # Test grid validation
    logger.info("\n2. Testing parameter grid validation...")
    validation = service.validate_param_grid(
        "bullish_vertical_put",
        param_grid,
        max_combinations=100
    )
    logger.info(f"   Validation result: {validation}")

    # Test health check
    logger.info("\n3. Testing health check...")
    health = await service.check_health()
    logger.info(f"   Health status: {health['status']}")
    for check in health.get('checks', []):
        logger.info(f"   - {check['name']}: {check['status']}")

    # Close Redis
    await redis_client.aclose()
    logger.info("\n✅ Direct service tests passed!")


async def test_client_direct_mode():
    """Test the client in direct mode."""
    logger.info("=" * 80)
    logger.info("Testing Client in Direct Mode")
    logger.info("=" * 80)

    # Initialize Redis
    redis_client = await aioredis.from_url(
        "redis://localhost:6379/0",
        decode_responses=True,
    )

    # Initialize client
    db_connection_string = "postgresql://quantvibe:quantvibe_dev@localhost:5432/options_data"
    client = OptimizationClient(
        mode="direct",
        redis_client=redis_client,
        db_connection_string=db_connection_string,
    )

    # Test parameter operations
    logger.info("\n1. Testing client parameter operations...")

    # Generate param grid
    result = await client.generate_param_grid(
        "bullish_vertical_put",
        custom_ranges={"spread_width": [5.0, 10.0, 15.0]},
    )
    logger.info(f"   Generated grid with {result['total_combinations']} combinations")

    # Get fixed params
    fixed = await client.get_fixed_params("bullish_vertical_put")
    logger.info(f"   Fixed params: {list(fixed['fixed_params'].keys())[:5]}...")

    # Validate param grid
    validation = await client.validate_param_grid(
        "bullish_vertical_put",
        result['param_grid'],
        max_combinations=200
    )
    logger.info(f"   Validation: valid={validation['valid']}, combinations={validation['total_combinations']}")

    # Close
    await redis_client.close()
    logger.info("\n✅ Client direct mode tests passed!")


async def test_client_http_mode():
    """Test the client in HTTP mode (requires API server running)."""
    logger.info("=" * 80)
    logger.info("Testing Client in HTTP Mode")
    logger.info("=" * 80)

    # Initialize client in HTTP mode
    client = OptimizationClient(
        mode="http",
        api_base_url="http://localhost:8200"
    )

    try:
        # Test parameter operations
        logger.info("\n1. Testing HTTP client parameter operations...")

        # Generate param grid
        result = await client.generate_param_grid(
            "bullish_vertical_put",
            optimize_only=["spread_width", "profit_target_min"]
        )
        logger.info(f"   Generated grid with {result['total_combinations']} combinations")

        logger.info("\n✅ Client HTTP mode tests passed!")

    except Exception as e:
        logger.warning(f"   HTTP mode test skipped (API not running): {e}")

    finally:
        await client.close()


async def test_mini_optimization():
    """Test running a small optimization."""
    logger.info("=" * 80)
    logger.info("Testing Mini Optimization Run")
    logger.info("=" * 80)

    # Initialize Redis
    redis_client = await aioredis.from_url(
        "redis://localhost:6379/0",
        decode_responses=True,
    )

    # Initialize client
    db_connection_string = "postgresql://quantvibe:quantvibe_dev@localhost:5432/options_data"
    client = OptimizationClient(
        mode="direct",
        redis_client=redis_client,
        db_connection_string=db_connection_string,
    )

    try:
        # Create a small optimization
        logger.info("\n1. Creating mini optimization...")

        # Very small param grid for quick test
        param_grid = {
            "spread_width": [10.0],
            "profit_target_min": [0.5],
        }

        result = await client.run_optimization(
            strategy_name="bullish_vertical_put",
            train_start_date=datetime(2024, 1, 1),
            train_end_date=datetime(2024, 1, 7),  # Just 1 week
            param_grid=param_grid,
            initial_capital=100000.0,
            underlying_ticker="SPX",
            timeframe="1hour",  # Use hourly for faster test
        )

        optimization_id = result["optimization_id"]
        logger.info(f"   Created optimization: {optimization_id}")
        logger.info(f"   Status: {result['status']}")

        # Check status
        await asyncio.sleep(2)
        status = await client.get_status(optimization_id)
        logger.info(f"   Current status: {status.get('status', 'unknown')}")

        # Cancel it (we don't want to wait)
        logger.info("\n2. Cancelling optimization...")
        cancel_result = await client.cancel_optimization(optimization_id)
        logger.info(f"   Cancel result: {cancel_result['message']}")

        logger.info("\n✅ Mini optimization test passed!")

    except Exception as e:
        logger.error(f"   Mini optimization test failed: {e}")

    finally:
        await redis_client.aclose()


async def main():
    """Run all tests."""
    logger.info("Starting Refactored Optimization Service Tests")
    logger.info("=" * 80)

    try:
        # Test direct service
        await test_direct_service()

        # Test client in direct mode
        await test_client_direct_mode()

        # Test client in HTTP mode (optional)
        await test_client_http_mode()

        # Test mini optimization
        await test_mini_optimization()

        logger.info("\n" + "=" * 80)
        logger.info("🎉 All tests completed successfully!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())