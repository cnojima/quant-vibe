#!/usr/bin/env python3
"""
Test script to create and run an optimization through the full pipeline.

This will test the complete flow:
1. Create optimization
2. Queue task
3. Worker processes it
4. Results are saved
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import redis.asyncio as aioredis
from optimization.client import OptimizationClient
from quant_vibe.logging import get_logger, setup_normalized_logging


# Configure logging
setup_normalized_logging(log_level="INFO")
logger = get_logger(__name__)


async def test_optimization_execution():
    """Test creating and executing an optimization."""
    logger.info("=" * 80)
    logger.info("Testing Optimization Execution")
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
        # Create a simple optimization
        logger.info("\n1. Creating optimization...")

        # Small param grid for quick test
        param_grid = {
            "spread_width": [10.0],
            "profit_target_min": [0.5],
        }

        result = await client.run_optimization(
            strategy_name="bullish_vertical_put",
            train_start_date=datetime(2024, 1, 1),
            train_end_date=datetime(2024, 1, 7),  # Just 1 week for quick test
            param_grid=param_grid,
            initial_capital=100000.0,
            underlying_ticker="SPX",
            timeframe="1hour",
        )

        optimization_id = result["optimization_id"]
        logger.info(f"   Created optimization: {optimization_id}")
        logger.info(f"   Status: {result['status']}")

        # Wait a bit for worker to process
        logger.info("\n2. Waiting for worker to process (30 seconds)...")
        await asyncio.sleep(30)

        # Check status
        status = await client.get_status(optimization_id)
        logger.info(f"   Current status: {status.get('status', 'unknown')}")
        logger.info(f"   Progress: {status.get('progress_current', 0)}/{status.get('total_combinations', 0)}")

        # Check if results were saved
        if status.get('status') == 'completed':
            logger.info("\n3. Checking results...")
            results = await client.get_results(optimization_id, limit=10)
            logger.info(f"   Results found: {len(results.get('results', []))}")

            if results.get('results'):
                best_result = results['results'][0]
                logger.info(f"   Best Sharpe Ratio: {best_result.get('sharpe_ratio', 'N/A')}")
                logger.info(f"   Best Total Return: {best_result.get('total_return', 'N/A')}%")
                logger.info(f"   Best Win Rate: {best_result.get('win_rate', 'N/A')}%")

        elif status.get('status') == 'failed':
            logger.error(f"   Optimization failed: {status.get('error_message', 'Unknown error')}")
        else:
            logger.info(f"   Optimization still in progress or queued")

        logger.info("\n✅ Optimization execution test completed!")

    except Exception as e:
        logger.error(f"   Test failed: {e}", exc_info=True)

    finally:
        await redis_client.aclose()


async def main():
    """Run all tests."""
    logger.info("Starting Optimization Execution Test")
    logger.info("=" * 80)

    try:
        await test_optimization_execution()

        logger.info("\n" + "=" * 80)
        logger.info("🎉 Test completed!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())