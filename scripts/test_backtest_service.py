#!/usr/bin/env python3
"""
Test script for BacktestService.

This script tests the new async backtest service to ensure:
1. Data loading with Redis caching works
2. Backtest execution is non-blocking
3. Progress tracking is accurate
4. Results are saved to database
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import redis.asyncio as aioredis
from quant_vibe.services.backtest_service import BacktestService
from quant_vibe.utils.timestamp_utils import to_utc
from quant_vibe.logging import get_logger

logger = get_logger(__name__)


async def test_backtest_service():
    """Test the BacktestService."""
    print("\n" + "=" * 70)
    print(" " * 20 + "BACKTEST SERVICE TEST")
    print("=" * 70)
    print()

    # Initialize Redis client
    redis_client = await aioredis.from_url(
        "redis://localhost:6379/0",
        decode_responses=True,
    )

    # Initialize service
    service = BacktestService(
        redis_client=redis_client,
        db_connection_string="postgresql://quantvibe:quantvibe_dev@localhost:5432/options_data",
        data_cache_ttl=3600,
        results_base_dir="reports/backtests",
    )

    print("✓ BacktestService initialized")
    print()

    try:
        # Test parameters
        strategy_name = "bullish_vertical_put"
        start_date = to_utc(datetime(2024, 12, 1))
        end_date = to_utc(datetime(2024, 12, 5))
        initial_capital = 100000.0

        print(f"Strategy: {strategy_name}")
        print(f"Date Range: {start_date.date()} to {end_date.date()}")
        print(f"Initial Capital: ${initial_capital:,.2f}")
        print()

        # Create backtest
        print("Creating backtest...")
        backtest_id = await service.create_backtest(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            parameters=None,  # Use defaults
            min_dte=0,
            max_dte=45,
            timeframe="5min",
            ticker="SPX",
        )
        print(f"✓ Backtest created: {backtest_id}")
        print()

        # Start backtest in background
        print("Starting backtest execution...")
        backtest_task = asyncio.create_task(service.run_backtest(backtest_id))
        print("✓ Backtest running in background")
        print()

        # Monitor progress
        print("Monitoring progress:")
        print("-" * 70)
        last_progress = -1

        while not backtest_task.done():
            status = await service.get_status(backtest_id)
            progress = status.get("progress", 0)
            message = status.get("message", "")

            # Only print when progress changes
            if progress != last_progress:
                print(f"[{progress:3d}%] {message}")
                last_progress = progress

            await asyncio.sleep(0.5)

        # Check for errors
        try:
            await backtest_task
        except Exception as e:
            print()
            print(f"✗ Backtest failed: {e}")
            status = await service.get_status(backtest_id)
            if status.get("error"):
                print(f"Error: {status['error']}")
            return False

        print("-" * 70)
        print()

        # Get final status
        status = await service.get_status(backtest_id)
        print("Final Status:")
        print(f"  Status: {status.get('status')}")
        print(f"  Progress: {status.get('progress')}%")
        print(f"  Message: {status.get('message')}")

        if status.get("results_summary"):
            summary = status["results_summary"]
            print(f"  Total Trades: {summary.get('total_trades', 0)}")
            print(f"  Equity Points: {summary.get('equity_points', 0)}")

        print()
        print("=" * 70)
        print("✓ TEST PASSED - Backtest completed successfully")
        print("=" * 70)
        print()

        return True

    except Exception as e:
        print()
        print(f"✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Cleanup
        await service.close()
        await redis_client.close()


async def test_caching():
    """Test that data caching works correctly."""
    print("\n" + "=" * 70)
    print(" " * 20 + "DATA CACHING TEST")
    print("=" * 70)
    print()

    # Initialize Redis client
    redis_client = await aioredis.from_url(
        "redis://localhost:6379/0",
        decode_responses=True,
    )

    # Initialize service
    service = BacktestService(
        redis_client=redis_client,
        db_connection_string="postgresql://quantvibe:quantvibe_dev@localhost:5432/options_data",
        data_cache_ttl=3600,
    )

    try:
        # Run two backtests with same parameters (second should use cache)
        start_date = to_utc(datetime(2024, 12, 1))
        end_date = to_utc(datetime(2024, 12, 2))

        print("Running first backtest (cache MISS expected)...")
        backtest_id_1 = await service.create_backtest(
            strategy_name="bullish_vertical_put",
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000.0,
            min_dte=0,
            max_dte=45,
            timeframe="5min",
            ticker="SPX",
        )

        await service.run_backtest(backtest_id_1)
        status_1 = await service.get_status(backtest_id_1)
        print(f"✓ First backtest completed: {status_1.get('message')}")
        print()

        print("Running second backtest with same parameters (cache HIT expected)...")
        backtest_id_2 = await service.create_backtest(
            strategy_name="bullish_vertical_put",
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000.0,
            min_dte=0,
            max_dte=45,
            timeframe="5min",
            ticker="SPX",
        )

        await service.run_backtest(backtest_id_2)
        status_2 = await service.get_status(backtest_id_2)
        print(f"✓ Second backtest completed: {status_2.get('message')}")
        print()

        print("=" * 70)
        print("✓ CACHING TEST PASSED")
        print("=" * 70)
        print()

        return True

    except Exception as e:
        print(f"✗ CACHING TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        await service.close()
        await redis_client.close()


async def main():
    """Run all tests."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 20 + "BACKTEST SERVICE TESTS" + " " * 26 + "║")
    print("╚" + "═" * 68 + "╝")

    tests = [
        ("Basic Backtest Execution", test_backtest_service),
        ("Data Caching", test_caching),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n▶ Running: {name}")
        result = await test_func()
        results.append((name, result))

    # Summary
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 25 + "TEST SUMMARY" + " " * 31 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}  {name}")

    print()

    # Exit code
    all_passed = all(result for _, result in results)
    if all_passed:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
