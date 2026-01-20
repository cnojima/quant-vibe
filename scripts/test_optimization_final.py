#!/usr/bin/env python3
"""
Final test of optimization execution after all fixes.
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


async def test_optimization():
    """Test creating and executing an optimization."""
    logger.info("=" * 80)
    logger.info("Final Optimization Execution Test")
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
            train_end_date=datetime(2024, 1, 3),  # Just 3 days for very quick test
            param_grid=param_grid,
            initial_capital=100000.0,
            underlying_ticker="SPX",
            timeframe="1hour",
        )

        optimization_id = result["optimization_id"]
        logger.info(f"   Created optimization: {optimization_id}")
        logger.info(f"   Status: {result['status']}")

        # Wait for worker to process
        logger.info("\n2. Waiting for worker (60 seconds)...")
        for i in range(12):
            await asyncio.sleep(5)
            status = await client.get_status(optimization_id)
            logger.info(f"   [{i*5}s] Status: {status.get('status', 'unknown')} - Progress: {status.get('progress_current', 0)}/{status.get('total_combinations', 0)}")

            if status.get('status') in ['completed', 'failed']:
                break

        # Final check
        status = await client.get_status(optimization_id)
        logger.info(f"\n3. Final status: {status.get('status', 'unknown')}")

        if status.get('status') == 'completed':
            logger.info("   ✅ Optimization completed successfully!")

            # Check results
            results = await client.get_results(optimization_id, limit=10)
            logger.info(f"   Results found: {len(results.get('results', []))}")

            if results.get('results'):
                best_result = results['results'][0]
                logger.info(f"   Best Sharpe Ratio: {best_result.get('sharpe_ratio', 'N/A')}")
                logger.info(f"   Best Total Return: {best_result.get('total_return', 'N/A')}%")
                logger.info(f"   Best Win Rate: {best_result.get('win_rate', 'N/A')}%")
                logger.info(f"   Total Trades: {best_result.get('total_trades', 'N/A')}")

        elif status.get('status') == 'failed':
            logger.error(f"   ❌ Optimization failed: {status.get('error_message', 'Unknown error')}")
        else:
            logger.warning(f"   ⚠️ Optimization still in progress or queued after 60 seconds")

    except Exception as e:
        logger.error(f"   Test failed: {e}", exc_info=True)

    finally:
        await redis_client.aclose()


async def main():
    """Run the test."""
    try:
        await test_optimization()
        logger.info("\n" + "=" * 80)
        logger.info("Test completed!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())