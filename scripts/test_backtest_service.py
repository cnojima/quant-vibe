#!/usr/bin/env python3
"""Integration test for the new backtest service.

This script tests the complete backtest service flow:
1. Submit a backtest via API
2. Check status
3. Wait for completion
4. Retrieve results

Usage:
    python scripts/test_backtest_service.py

    # Test against a specific service URL
    python scripts/test_backtest_service.py --service-url http://localhost:8001

    # Test with custom parameters
    python scripts/test_backtest_service.py --strategy iron_condor --days 30
"""

import sys
import os
import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Test the backtest service API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--service-url',
        type=str,
        default=os.getenv('BACKTEST_SERVICE_URL', 'http://localhost:8001'),
        help='Backtest service URL (default: http://localhost:8001)'
    )

    parser.add_argument(
        '--strategy',
        type=str,
        default='bullish_vertical_put',
        help='Strategy to test (default: bullish_vertical_put)'
    )

    parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='Number of days to backtest (default: 7)'
    )

    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Maximum time to wait for completion in seconds (default: 300)'
    )

    return parser.parse_args()


async def test_health_check(service_url: str) -> bool:
    """Test the health check endpoint."""
    import httpx

    print("1. Testing health check...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{service_url}/health",
                timeout=5.0,
            )

            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Service is healthy: {data}")
                return True
            else:
                print(f"   ✗ Health check failed: {response.status_code}")
                return False

    except Exception as e:
        print(f"   ✗ Failed to connect: {e}")
        return False


async def test_create_backtest(service_url: str, strategy: str, days: int) -> str:
    """Test creating a new backtest."""
    import httpx

    print("\n2. Creating backtest...")

    # Prepare test data
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    request_data = {
        "strategy_name": strategy,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "initial_capital": 100000.0,
        "params": {
            "min_dte": 0,
            "max_dte": 45,
            "max_trades_daily": 3,
        },
        "ticker": "$SPX",
        "timeframe": "5min",
        "description": f"Integration test backtest for {strategy}",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{service_url}/api/backtests",
                json=request_data,
                timeout=30.0,
            )

            if response.status_code == 200:
                data = response.json()
                backtest_id = data["id"]
                print(f"   ✓ Backtest created: {backtest_id}")
                print(f"     Status: {data['status']}")
                return backtest_id
            else:
                print(f"   ✗ Failed to create backtest: {response.status_code}")
                print(f"     Response: {response.text}")
                return None

    except Exception as e:
        print(f"   ✗ Error creating backtest: {e}")
        return None


async def test_get_status(service_url: str, backtest_id: str) -> dict:
    """Test getting backtest status."""
    import httpx

    print("\n3. Checking status...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{service_url}/api/backtests/{backtest_id}",
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Status retrieved: {data['status']}")
                print(f"     Progress: {data.get('progress', 0):.1f}%")
                return data
            else:
                print(f"   ✗ Failed to get status: {response.status_code}")
                return None

    except Exception as e:
        print(f"   ✗ Error getting status: {e}")
        return None


async def test_wait_for_completion(service_url: str, backtest_id: str, timeout: int) -> bool:
    """Test waiting for backtest completion."""
    import httpx
    import time

    print("\n4. Waiting for completion...")

    start_time = time.time()
    last_progress = -1

    try:
        async with httpx.AsyncClient() as client:
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    print(f"\n   ✗ Timeout after {timeout} seconds")
                    return False

                response = await client.get(
                    f"{service_url}/api/backtests/{backtest_id}",
                    timeout=10.0,
                )

                if response.status_code != 200:
                    print(f"\n   ✗ Error checking status: {response.status_code}")
                    return False

                data = response.json()
                status = data["status"]
                progress = data.get("progress", 0)

                # Show progress
                if progress != last_progress:
                    print(f"\r   Progress: {progress:.1f}% - {status}", end="", flush=True)
                    last_progress = progress

                if status == "completed":
                    print(f"\n   ✓ Backtest completed in {elapsed:.1f} seconds")
                    return True
                elif status == "failed":
                    print(f"\n   ✗ Backtest failed: {data.get('error', 'Unknown error')}")
                    return False
                elif status == "cancelled":
                    print(f"\n   ⚠ Backtest was cancelled")
                    return False

                await asyncio.sleep(1)

    except Exception as e:
        print(f"\n   ✗ Error waiting for completion: {e}")
        return False


async def test_get_results(service_url: str, backtest_id: str) -> bool:
    """Test getting backtest results."""
    import httpx

    print("\n5. Getting results...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{service_url}/api/backtests/{backtest_id}/results",
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Results retrieved:")
                print(f"     Strategy: {data.get('strategy_name')}")
                print(f"     Total Return: {data.get('total_return', 0):.2f}%")
                print(f"     Sharpe Ratio: {data.get('sharpe_ratio', 'N/A')}")
                print(f"     Max Drawdown: {data.get('max_drawdown', 0):.2f}%")
                print(f"     Win Rate: {data.get('win_rate', 0):.2f}%")
                print(f"     Total Trades: {data.get('total_trades', 0)}")
                return True
            else:
                print(f"   ✗ Failed to get results: {response.status_code}")
                return False

    except Exception as e:
        print(f"   ✗ Error getting results: {e}")
        return False


async def test_list_backtests(service_url: str) -> bool:
    """Test listing backtests."""
    import httpx

    print("\n6. Listing backtests...")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{service_url}/api/backtests",
                params={"limit": 5},
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                backtests = data.get("backtests", [])
                print(f"   ✓ Found {len(backtests)} recent backtests")
                for bt in backtests[:3]:  # Show first 3
                    print(f"     - {bt['id'][:8]}... {bt['status']:10} {bt.get('strategy_name', 'N/A')}")
                return True
            else:
                print(f"   ✗ Failed to list backtests: {response.status_code}")
                return False

    except Exception as e:
        print(f"   ✗ Error listing backtests: {e}")
        return False


async def run_tests(args):
    """Run all integration tests."""
    print("=" * 70)
    print(" " * 20 + "BACKTEST SERVICE INTEGRATION TEST")
    print("=" * 70)
    print(f"\nTesting service at: {args.service_url}")
    print(f"Strategy: {args.strategy}")
    print(f"Days to backtest: {args.days}")
    print("-" * 70)

    results = []

    # Test 1: Health check
    health_ok = await test_health_check(args.service_url)
    results.append(("Health Check", health_ok))

    if not health_ok:
        print("\n✗ Service is not healthy, cannot continue tests")
        return False

    # Test 2: Create backtest
    backtest_id = await test_create_backtest(args.service_url, args.strategy, args.days)
    results.append(("Create Backtest", backtest_id is not None))

    if not backtest_id:
        print("\n✗ Failed to create backtest, cannot continue tests")
        return False

    # Test 3: Get status
    status = await test_get_status(args.service_url, backtest_id)
    results.append(("Get Status", status is not None))

    # Test 4: Wait for completion
    completed = await test_wait_for_completion(args.service_url, backtest_id, args.timeout)
    results.append(("Wait for Completion", completed))

    # Test 5: Get results (only if completed)
    if completed:
        results_ok = await test_get_results(args.service_url, backtest_id)
        results.append(("Get Results", results_ok))
    else:
        results.append(("Get Results", False))

    # Test 6: List backtests
    list_ok = await test_list_backtests(args.service_url)
    results.append(("List Backtests", list_ok))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("-" * 70)

    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)

    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {test_name:25} {status}")

    print("-" * 70)
    print(f"Results: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n✓ All tests passed! Backtest service is working correctly.")
        return True
    else:
        print(f"\n✗ {total_tests - passed_tests} test(s) failed.")
        return False


async def main():
    """Main entry point."""
    args = parse_args()

    try:
        success = await run_tests(args)
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())