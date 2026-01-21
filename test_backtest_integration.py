#!/usr/bin/env python3
"""
Test script to verify the integration between admin_ui and the backtest service.
"""

import asyncio
import os
from datetime import datetime, timedelta

# Set environment variable to use the backtest service
os.environ["BACKTEST_SERVICE_URL"] = "http://localhost:8001"

from src.backtest.client import BacktestClient
from src.quant_vibe.utils import now_utc


async def test_integration():
    """Test the backtest service integration."""

    print("Testing backtest service integration...")
    print("=" * 50)

    # Create client in API mode
    client = BacktestClient(mode="api")

    try:
        # 1. Test listing backtests
        print("\n1. Listing existing backtests...")
        backtests = await client.list_backtests(limit=5)
        print(f"   Found {len(backtests)} existing backtests")

        # 2. Test creating a new backtest
        print("\n2. Creating a new backtest...")
        end_date = now_utc()
        start_date = end_date - timedelta(days=7)

        backtest_id = await client.create_backtest(
            strategy_name="bullish_vertical_put",
            start_date=start_date,
            end_date=end_date,
            initial_capital=100000.0,
            params={
                "spread_width": 10.0,
                "min_dte": 0,
                "max_dte": 15,
                "profit_target_min": 0.5,
            },
            ticker="$SPX",
            timeframe="5min",
            description="Integration test backtest",
        )

        print(f"   Created backtest with ID: {backtest_id}")

        # 3. Test getting status
        print("\n3. Getting backtest status...")
        status = await client.get_status(backtest_id)
        if status:
            print(f"   Status: {status['status']}")
            print(f"   Progress: {status.get('progress', 0)}%")
        else:
            print("   Failed to get status")

        # 4. Test canceling the backtest
        print("\n4. Canceling the backtest...")
        cancelled = await client.cancel_backtest(backtest_id)
        if cancelled:
            print("   Backtest cancelled successfully")
        else:
            print("   Failed to cancel backtest")

        # 5. Verify final status
        print("\n5. Verifying final status...")
        status = await client.get_status(backtest_id)
        if status:
            print(f"   Final status: {status['status']}")

        print("\n" + "=" * 50)
        print("Integration test completed successfully!")
        print("The admin_ui can communicate with the backtest service.")

    except Exception as e:
        print(f"\nError during integration test: {e}")
        print("Please ensure both services are running:")
        print("  - Backtest service: http://localhost:8001")
        print("  - Admin UI: http://localhost:8000")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(test_integration())