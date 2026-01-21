#!/usr/bin/env python3
"""Run backtests using either the backtest service API or direct execution.

This updated script provides options to run backtests via:
1. The new backtest service API (default) - for production use
2. Direct execution (--direct flag) - for debugging or when service is unavailable

Usage:
    # Run via backtest service (default)
    python scripts/run_backtest.py --strategy bullish_vertical_put

    # Run directly (bypassing service)
    python scripts/run_backtest.py --strategy bullish_vertical_put --direct

    # Check status of a backtest
    python scripts/run_backtest.py --status <backtest_id>

Examples:
    # Run backtest via API service
    python scripts/run_backtest.py --strategy bullish_vertical_put \\
        --start-date 2024-01-01 --end-date 2024-12-31

    # Run directly for debugging
    python scripts/run_backtest.py --strategy bullish_vertical_put \\
        --start-date 2024-01-01 --end-date 2024-12-31 --direct

    # Check backtest status
    python scripts/run_backtest.py --status 123e4567-e89b-12d3-a456-426614174000
"""

import sys
import os
import argparse
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def print_banner(mode: str = "service"):
    """Print startup banner."""
    print("\n" + "=" * 70)
    print(" " * 20 + "BACKTEST RUNNER")
    print("=" * 70)
    print()
    if mode == "service":
        print("  Running backtest via API service")
        print("  Results will be available through the web interface")
    else:
        print("  Running backtest directly (debug mode)")
        print("  Results will be saved to the configured output directory")
    print()
    print("=" * 70)
    print()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Run backtests via service API or directly',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --strategy bullish_vertical_put
    Run backtest via API service (default)

  %(prog)s --strategy bullish_vertical_put --direct
    Run backtest directly for debugging

  %(prog)s --status <backtest_id>
    Check status of a running backtest

  %(prog)s --list
    List all recent backtests

For more information, see the documentation.
        """
    )

    # Mode selection
    parser.add_argument(
        '--direct',
        action='store_true',
        help='Run backtest directly instead of via service API'
    )

    parser.add_argument(
        '--service-url',
        type=str,
        default=os.getenv('BACKTEST_SERVICE_URL', 'http://localhost:8001'),
        help='Backtest service URL (default: http://localhost:8001)'
    )

    # Status checking
    parser.add_argument(
        '--status',
        type=str,
        help='Check status of a backtest by ID'
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='List all recent backtests'
    )

    # Backtest configuration
    parser.add_argument(
        '--config',
        type=str,
        default='config/backtest.yaml',
        help='Path to backtest configuration file (for direct mode)'
    )

    parser.add_argument(
        '--strategy',
        type=str,
        help='Strategy to backtest (required unless checking status)'
    )

    parser.add_argument(
        '--start-date',
        type=str,
        help='Start date for backtest (YYYY-MM-DD format)'
    )

    parser.add_argument(
        '--end-date',
        type=str,
        help='End date for backtest (YYYY-MM-DD format)'
    )

    parser.add_argument(
        '--initial-capital',
        type=float,
        default=100000.0,
        help='Initial capital amount (default: 100000)'
    )

    parser.add_argument(
        '--ticker',
        type=str,
        default='$SPX',
        help='Ticker symbol (default: $SPX)'
    )

    parser.add_argument(
        '--timeframe',
        type=str,
        default='5min',
        choices=['1min', '5min', '15min', '1hour', 'daily'],
        help='Data timeframe (default: 5min)'
    )

    # Strategy parameters
    parser.add_argument(
        '--min-dte',
        type=int,
        help='Minimum days to expiration'
    )

    parser.add_argument(
        '--max-dte',
        type=int,
        help='Maximum days to expiration'
    )

    parser.add_argument(
        '--max-trades-daily',
        type=int,
        help='Maximum trades per day'
    )

    parser.add_argument(
        '--params',
        type=str,
        help='Strategy parameters as JSON string'
    )

    parser.add_argument(
        '--backtest-id',
        type=str,
        help='Specific backtest ID to use (auto-generated if not provided)'
    )

    parser.add_argument(
        '--description',
        type=str,
        help='Description for this backtest run'
    )

    parser.add_argument(
        '--wait',
        action='store_true',
        help='Wait for backtest to complete and show results'
    )

    return parser.parse_args()


async def run_via_service(args) -> str:
    """Run backtest via the API service."""
    import httpx

    # Prepare request data
    request_data = {
        "strategy_name": args.strategy,
        "initial_capital": args.initial_capital,
        "ticker": args.ticker,
        "timeframe": args.timeframe,
    }

    # Add dates if provided
    if args.start_date and args.end_date:
        # Parse dates
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
        request_data["start_date"] = start_date.isoformat()
        request_data["end_date"] = end_date.isoformat()
    else:
        # Use default date range (last year)
        from datetime import datetime, timedelta
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=365)
        request_data["start_date"] = start_date.isoformat()
        request_data["end_date"] = end_date.isoformat()

    # Build parameters dict
    params = {}
    if args.min_dte is not None:
        params["min_dte"] = args.min_dte
    if args.max_dte is not None:
        params["max_dte"] = args.max_dte
    if args.max_trades_daily is not None:
        params["max_trades_daily"] = args.max_trades_daily

    # Add custom parameters from JSON if provided
    if args.params:
        try:
            custom_params = json.loads(args.params)
            params.update(custom_params)
        except json.JSONDecodeError as e:
            print(f"Error parsing --params JSON: {e}")
            sys.exit(1)

    if params:
        request_data["params"] = params

    if args.description:
        request_data["description"] = args.description

    # Make request to backtest service
    async with httpx.AsyncClient() as client:
        try:
            print(f"Submitting backtest to service at {args.service_url}...")
            response = await client.post(
                f"{args.service_url}/api/backtests",
                json=request_data,
                timeout=30.0,
            )

            if response.status_code != 200:
                print(f"Error: Service returned {response.status_code}")
                print(response.text)
                sys.exit(1)

            result = response.json()
            backtest_id = result["id"]
            print(f"\n✓ Backtest submitted successfully!")
            print(f"  ID: {backtest_id}")
            print(f"  Status: {result['status']}")

            if args.wait:
                print("\nWaiting for completion...")
                await wait_for_completion(client, args.service_url, backtest_id)

            return backtest_id

        except httpx.RequestError as e:
            print(f"Error: Failed to connect to backtest service at {args.service_url}")
            print(f"  {e}")
            print("\nMake sure the backtest service is running:")
            print("  docker-compose up backtest backtest-worker")
            sys.exit(1)


async def wait_for_completion(client: httpx.AsyncClient, service_url: str, backtest_id: str):
    """Wait for backtest to complete and show progress."""
    import time

    last_progress = -1
    while True:
        try:
            response = await client.get(
                f"{service_url}/api/backtests/{backtest_id}",
                timeout=10.0,
            )

            if response.status_code != 200:
                print(f"Error checking status: {response.status_code}")
                break

            status_data = response.json()
            status = status_data["status"]
            progress = status_data.get("progress", 0)

            # Show progress bar
            if progress != last_progress:
                progress_bar = "█" * int(progress / 2) + "░" * (50 - int(progress / 2))
                print(f"\r  [{progress_bar}] {progress:.1f}% - {status}", end="", flush=True)
                last_progress = progress

            if status == "completed":
                print(f"\n\n✓ Backtest completed successfully!")
                await show_results(client, service_url, backtest_id)
                break
            elif status == "failed":
                print(f"\n\n✗ Backtest failed!")
                print(f"  Error: {status_data.get('error', 'Unknown error')}")
                sys.exit(1)
            elif status == "cancelled":
                print(f"\n\n⚠ Backtest was cancelled")
                break

            await asyncio.sleep(1)

        except Exception as e:
            print(f"\nError checking status: {e}")
            break


async def show_results(client: httpx.AsyncClient, service_url: str, backtest_id: str):
    """Display backtest results."""
    try:
        response = await client.get(
            f"{service_url}/api/backtests/{backtest_id}/results",
            timeout=10.0,
        )

        if response.status_code != 200:
            print(f"Error getting results: {response.status_code}")
            return

        results = response.json()

        print("\nResults:")
        print(f"  Strategy: {results.get('strategy_name')}")
        print(f"  Date Range: {results.get('start_date')} to {results.get('end_date')}")
        print(f"  Initial Capital: ${results.get('initial_capital', 0):,.2f}")
        print(f"  Final Capital: ${results.get('final_capital', 0):,.2f}")
        print(f"  Total Return: {results.get('total_return', 0):.2f}%")
        print(f"  Sharpe Ratio: {results.get('sharpe_ratio', 'N/A')}")
        print(f"  Max Drawdown: {results.get('max_drawdown', 0):.2f}%")
        print(f"  Win Rate: {results.get('win_rate', 0):.2f}%")
        print(f"  Total Trades: {results.get('total_trades', 0)}")

    except Exception as e:
        print(f"Error getting results: {e}")


async def check_status(args):
    """Check status of a backtest."""
    import httpx

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{args.service_url}/api/backtests/{args.status}",
                timeout=10.0,
            )

            if response.status_code == 404:
                print(f"Backtest {args.status} not found")
                sys.exit(1)
            elif response.status_code != 200:
                print(f"Error: Service returned {response.status_code}")
                print(response.text)
                sys.exit(1)

            status_data = response.json()

            print(f"\nBacktest Status:")
            print(f"  ID: {status_data['id']}")
            print(f"  Status: {status_data['status']}")
            print(f"  Progress: {status_data.get('progress', 0):.1f}%")
            print(f"  Strategy: {status_data.get('strategy_name')}")

            if status_data.get('started_at'):
                print(f"  Started: {status_data['started_at']}")
            if status_data.get('completed_at'):
                print(f"  Completed: {status_data['completed_at']}")
            if status_data.get('error'):
                print(f"  Error: {status_data['error']}")

        except httpx.RequestError as e:
            print(f"Error: Failed to connect to backtest service")
            print(f"  {e}")
            sys.exit(1)


async def list_backtests(args):
    """List recent backtests."""
    import httpx

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{args.service_url}/api/backtests",
                params={"limit": 20},
                timeout=10.0,
            )

            if response.status_code != 200:
                print(f"Error: Service returned {response.status_code}")
                print(response.text)
                sys.exit(1)

            data = response.json()
            backtests = data.get("backtests", [])

            if not backtests:
                print("No backtests found")
                return

            print("\nRecent Backtests:")
            print("-" * 80)
            print(f"{'ID':36} {'Status':12} {'Progress':10} {'Strategy':20}")
            print("-" * 80)

            for bt in backtests:
                print(f"{bt['id'][:36]} {bt['status']:12} {bt.get('progress', 0):8.1f}% {bt.get('strategy_name', 'N/A')[:20]}")

        except httpx.RequestError as e:
            print(f"Error: Failed to connect to backtest service")
            print(f"  {e}")
            sys.exit(1)


def run_directly(args):
    """Run backtest directly (bypassing service)."""
    from backtest import BacktestOrchestrator
    from quant_vibe.utils.datetime_utils import trading_day_to_utc

    # Parse dates if provided
    start_date = None
    end_date = None
    if args.start_date and args.end_date:
        # Parse YYYY-MM-DD format
        start_parts = args.start_date.split('-')
        end_parts = args.end_date.split('-')

        # Convert to market hours in UTC
        start_date, _ = trading_day_to_utc(
            int(start_parts[0]), int(start_parts[1]), int(start_parts[2])
        )
        _, end_date = trading_day_to_utc(
            int(end_parts[0]), int(end_parts[1]), int(end_parts[2])
        )

    # Initialize orchestrator
    orchestrator = BacktestOrchestrator(
        config_path=args.config,
        strategy_filter=args.strategy,
    )

    # Run backtests
    results = orchestrator.run(
        start_date=start_date,
        end_date=end_date,
        min_dte=args.min_dte,
        max_dte=args.max_dte,
        max_trades_daily=args.max_trades_daily,
        initial_capital=args.initial_capital,
        backtest_id=args.backtest_id,
        timeframe=args.timeframe,
    )

    print("\n✓ Backtest completed successfully")


async def main_async():
    """Async main entry point."""
    args = parse_args()

    # Handle status check
    if args.status:
        await check_status(args)
        return

    # Handle list
    if args.list:
        await list_backtests(args)
        return

    # Require strategy for running backtest
    if not args.strategy:
        print("Error: --strategy is required to run a backtest")
        print("Use --status <id> to check status or --list to see all backtests")
        sys.exit(1)

    # Print banner
    mode = "direct" if args.direct else "service"
    print_banner(mode)

    # Run backtest
    if args.direct:
        # Run directly (synchronous)
        run_directly(args)
    else:
        # Run via service (async)
        await run_via_service(args)


def main():
    """Main entry point."""
    try:
        asyncio.run(main_async())
        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user (Ctrl+C)")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()