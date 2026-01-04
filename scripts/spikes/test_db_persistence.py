#!/usr/bin/env python3
"""
Quick test script to verify backtest database persistence.

This script runs a minimal backtest and verifies results are saved to PostgreSQL.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime
from quant_vibe.data.timescale_store import TimescaleStore

def main():
    print("=" * 70)
    print("BACKTEST DATABASE PERSISTENCE TEST")
    print("=" * 70)

    # Check database connection
    print("\n1. Testing database connection...")
    try:
        ts_store = TimescaleStore()
        print("✅ Connected to TimescaleDB")

        # Check if backtest tables exist
        with ts_store.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name LIKE 'backtest%'
                    ORDER BY table_name
                """)
                tables = cursor.fetchall()

        print(f"✅ Found {len(tables)} backtest tables:")
        for table in tables:
            print(f"   - {table[0]}")

        ts_store.close()

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return 1

    # Run a simple backtest using the orchestrator
    print("\n2. Running test backtest...")
    print("   Strategy: bullish_vertical_put")
    print("   Date range: 2025-12-23 to 2025-12-23 (1 day)")

    try:
        from backtest import BacktestOrchestrator

        # Create orchestrator
        orchestrator = BacktestOrchestrator(
            config_path="config/backtest.yaml",
            strategy_filter="bullish_vertical_put"
        )

        # Run with specific date range (1 day for quick test)
        start_date = datetime(2025, 12, 23, 14, 30)  # Market open in UTC
        end_date = datetime(2025, 12, 23, 21, 0)     # Market close in UTC

        results = orchestrator.run(
            start_date=start_date,
            end_date=end_date,
            min_dte=0,
            max_dte=0
        )

        print(f"✅ Backtest completed: {len(results)} strategy run(s)")

    except Exception as e:
        print(f"❌ Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Verify data was saved to database
    print("\n3. Verifying database persistence...")
    try:
        ts_store = TimescaleStore()

        # Get recent backtest runs
        history = ts_store.get_backtest_history(limit=5)

        if not history:
            print("⚠️  No backtests found in database")
            print("   Results may have been saved to CSV only")
            ts_store.close()
            return 1

        latest = history[0]
        backtest_id = latest['backtest_id']

        print(f"✅ Found backtest in database: {backtest_id}")
        print(f"   Strategy: {latest['strategy_name']}")
        print(f"   Status: {latest['status']}")
        print(f"   Started: {latest.get('started_at', 'N/A')}")

        # Handle None values safely
        total_return = latest.get('total_return_pct')
        win_rate = latest.get('win_rate')
        num_trades = latest.get('num_trades')

        print(f"   Total Return: {total_return:.2f}%" if total_return is not None else "   Total Return: N/A")
        print(f"   Win Rate: {win_rate:.2f}%" if win_rate is not None else "   Win Rate: N/A")
        print(f"   Trades: {num_trades}" if num_trades is not None else "   Trades: 0")

        # Get trades
        trades_df = ts_store.get_backtest_trades(backtest_id)
        print(f"\n✅ Retrieved {len(trades_df)} trades from database")

        # Get equity curve
        equity_df = ts_store.get_backtest_equity_curve(backtest_id)
        print(f"✅ Retrieved {len(equity_df)} equity curve points from database")

        ts_store.close()

    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("\n" + "=" * 70)
    print("✅ ALL TESTS PASSED - DATABASE PERSISTENCE WORKING!")
    print("=" * 70)

    return 0

if __name__ == "__main__":
    sys.exit(main())
