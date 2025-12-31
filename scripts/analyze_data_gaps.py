#!/usr/bin/env python3
"""Analyze data gaps between remote and local TimescaleDB instances.

This script identifies:
1. Missing trading days (entire days with no data)
2. Sparse days (days with partial data coverage)
3. Missing contracts (contracts present in remote but not in local)
4. Time gaps within days (missing minute bars during trading hours)

Usage:
    # Quick overview
    python scripts/analyze_data_gaps.py --quick

    # Detailed analysis for specific date range
    python scripts/analyze_data_gaps.py --since 2025-12-01 --until 2025-12-30

    # Analyze specific ticker
    python scripts/analyze_data_gaps.py --ticker SPX --detailed

    # Generate sync commands for gaps
    python scripts/analyze_data_gaps.py --generate-sync-commands
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone, time
import psycopg2
from psycopg2.extras import execute_batch, RealDictCursor
from dotenv import load_dotenv
from collections import defaultdict
import argparse

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Remote DB config
REMOTE_CONFIG = {
    'host': os.getenv('REMOTE_TIMESCALE_HOST'),
    'port': int(os.getenv('REMOTE_TIMESCALE_PORT', '5432')),
    'database': os.getenv('REMOTE_TIMESCALE_DB', 'options_data'),
    'user': os.getenv('REMOTE_TIMESCALE_USER', 'quantvibe'),
    'password': os.getenv('REMOTE_TIMESCALE_PASSWORD')
}

# Local DB config
LOCAL_CONFIG = {
    'host': os.getenv('TIMESCALE_HOST', 'localhost'),
    'port': int(os.getenv('TIMESCALE_PORT', '5432')),
    'database': os.getenv('TIMESCALE_DB', 'options_data'),
    'user': os.getenv('TIMESCALE_USER', 'quantvibe'),
    'password': os.getenv('TIMESCALE_PASSWORD', 'quantvibe_dev')
}

# Market hours (EST/EDT converted to UTC)
# EST: UTC-5, EDT: UTC-4
# Market: 9:30 AM - 4:00 PM ET
MARKET_OPEN_HOUR_UTC = 14  # 9:30 AM EST = 2:30 PM UTC
MARKET_CLOSE_HOUR_UTC = 21  # 4:00 PM EST = 9:00 PM UTC


def is_market_hours(timestamp):
    """Check if timestamp falls within market hours (9:30 AM - 4:00 PM EST)."""
    hour = timestamp.hour
    minute = timestamp.minute

    # Before market open (9:30 AM EST = 14:30 UTC)
    if hour < MARKET_OPEN_HOUR_UTC:
        return False
    if hour == MARKET_OPEN_HOUR_UTC and minute < 30:
        return False

    # After market close (4:00 PM EST = 21:00 UTC)
    if hour >= MARKET_CLOSE_HOUR_UTC:
        return False

    return True


def get_daily_stats(conn, start_date=None, end_date=None, underlying='SPX'):
    """Get daily statistics: row counts, unique contracts, time coverage."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        where_clause = "WHERE underlying_ticker = %s"
        params = [underlying]

        if start_date:
            where_clause += " AND timestamp >= %s"
            params.append(start_date)
        if end_date:
            where_clause += " AND timestamp < %s"
            params.append(end_date)

        query = f"""
            SELECT
                DATE(timestamp) as trading_date,
                COUNT(*) as bar_count,
                COUNT(DISTINCT option_ticker) as unique_contracts,
                MIN(timestamp) as first_bar,
                MAX(timestamp) as last_bar,
                COUNT(DISTINCT DATE_TRUNC('minute', timestamp)) as unique_minutes
            FROM options_bars
            {where_clause}
            GROUP BY DATE(timestamp)
            ORDER BY trading_date DESC
        """

        cur.execute(query, params)
        return cur.fetchall()


def compare_daily_coverage(remote_stats, local_stats):
    """Compare daily coverage between remote and local."""
    remote_by_date = {row['trading_date']: row for row in remote_stats}
    local_by_date = {row['trading_date']: row for row in local_stats}

    all_dates = sorted(set(remote_by_date.keys()) | set(local_by_date.keys()), reverse=True)

    gaps = {
        'missing_days': [],      # Days with no local data
        'partial_days': [],      # Days with less than 80% coverage
        'sparse_contracts': [],  # Days with significantly fewer contracts
    }

    for date in all_dates:
        remote = remote_by_date.get(date)
        local = local_by_date.get(date)

        if remote and not local:
            gaps['missing_days'].append({
                'date': date,
                'remote_bars': remote['bar_count'],
                'remote_contracts': remote['unique_contracts']
            })
        elif remote and local:
            coverage_pct = (local['bar_count'] / remote['bar_count']) * 100 if remote['bar_count'] > 0 else 0
            contract_pct = (local['unique_contracts'] / remote['unique_contracts']) * 100 if remote['unique_contracts'] > 0 else 0

            if coverage_pct < 80:
                gaps['partial_days'].append({
                    'date': date,
                    'coverage_pct': coverage_pct,
                    'remote_bars': remote['bar_count'],
                    'local_bars': local['bar_count'],
                    'missing_bars': remote['bar_count'] - local['bar_count']
                })

            if contract_pct < 80:
                gaps['sparse_contracts'].append({
                    'date': date,
                    'contract_pct': contract_pct,
                    'remote_contracts': remote['unique_contracts'],
                    'local_contracts': local['unique_contracts'],
                    'missing_contracts': remote['unique_contracts'] - local['unique_contracts']
                })

    return gaps


def get_missing_contracts(remote_conn, local_conn, date, underlying='SPX'):
    """Get list of contracts present in remote but missing in local for a specific date."""
    with remote_conn.cursor() as remote_cur:
        remote_cur.execute("""
            SELECT DISTINCT option_ticker
            FROM options_bars
            WHERE DATE(timestamp) = %s
            AND underlying_ticker = %s
        """, (date, underlying))
        remote_contracts = {row[0] for row in remote_cur.fetchall()}

    with local_conn.cursor() as local_cur:
        local_cur.execute("""
            SELECT DISTINCT option_ticker
            FROM options_bars
            WHERE DATE(timestamp) = %s
            AND underlying_ticker = %s
        """, (date, underlying))
        local_contracts = {row[0] for row in local_cur.fetchall()}

    return remote_contracts - local_contracts


def print_gap_summary(gaps, verbose=False):
    """Print a summary of identified gaps."""
    print("\n" + "="*70)
    print("GAP ANALYSIS SUMMARY")
    print("="*70)

    # Missing days
    if gaps['missing_days']:
        print(f"\n❌ MISSING DAYS: {len(gaps['missing_days'])} days with no local data")
        if verbose:
            for gap in gaps['missing_days'][:10]:  # Show first 10
                print(f"   {gap['date']}: {gap['remote_bars']:,} bars, {gap['remote_contracts']:,} contracts")
            if len(gaps['missing_days']) > 10:
                print(f"   ... and {len(gaps['missing_days']) - 10} more")
        else:
            print(f"   Latest: {gaps['missing_days'][0]['date']}")
            print(f"   Oldest: {gaps['missing_days'][-1]['date']}")
    else:
        print("\n✅ No completely missing days")

    # Partial days
    if gaps['partial_days']:
        print(f"\n⚠️  PARTIAL DAYS: {len(gaps['partial_days'])} days with <80% coverage")
        if verbose:
            for gap in gaps['partial_days'][:10]:
                print(f"   {gap['date']}: {gap['coverage_pct']:.1f}% ({gap['local_bars']:,}/{gap['remote_bars']:,} bars)")
            if len(gaps['partial_days']) > 10:
                print(f"   ... and {len(gaps['partial_days']) - 10} more")
    else:
        print("\n✅ No partial days (<80% coverage)")

    # Sparse contracts
    if gaps['sparse_contracts']:
        print(f"\n⚠️  SPARSE CONTRACTS: {len(gaps['sparse_contracts'])} days with <80% contracts")
        if verbose:
            for gap in gaps['sparse_contracts'][:10]:
                print(f"   {gap['date']}: {gap['contract_pct']:.1f}% ({gap['local_contracts']:,}/{gap['remote_contracts']:,} contracts)")
            if len(gaps['sparse_contracts']) > 10:
                print(f"   ... and {len(gaps['sparse_contracts']) - 10} more")
    else:
        print("\n✅ No sparse contract days")

    print("\n" + "="*70)


def generate_sync_commands(gaps, output_file=None):
    """Generate shell commands to sync identified gaps."""
    commands = []

    # Sync missing days
    if gaps['missing_days']:
        # Group consecutive days for batch syncing
        day_groups = []
        current_group = [gaps['missing_days'][0]['date']]

        for i in range(1, len(gaps['missing_days'])):
            prev_date = gaps['missing_days'][i-1]['date']
            curr_date = gaps['missing_days'][i]['date']

            # Check if consecutive
            if (prev_date - curr_date).days == 1:
                current_group.append(curr_date)
            else:
                day_groups.append(current_group)
                current_group = [curr_date]

        day_groups.append(current_group)

        # Generate commands for each group
        for group in day_groups:
            start = min(group)
            end = max(group) + timedelta(days=1)  # Include end day
            commands.append(
                f"python scripts/sync_moirae.py --since {start.strftime('%Y-%m-%d')} "
                f"--until {end.strftime('%Y-%m-%d')}  # {len(group)} days"
            )

    # Sync partial days
    if gaps['partial_days']:
        for gap in gaps['partial_days']:
            date = gap['date']
            end_date = date + timedelta(days=1)
            commands.append(
                f"python scripts/sync_moirae.py --since {date.strftime('%Y-%m-%d')} "
                f"--until {end_date.strftime('%Y-%m-%d')}  # {gap['coverage_pct']:.1f}% coverage"
            )

    if output_file:
        with open(output_file, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write("# Auto-generated sync commands\n")
            f.write(f"# Generated: {datetime.now()}\n\n")
            for cmd in commands:
                f.write(cmd + "\n")
        print(f"\n✅ Sync commands saved to: {output_file}")
        print(f"   Run: chmod +x {output_file} && ./{output_file}")
    else:
        print("\n" + "="*70)
        print("SUGGESTED SYNC COMMANDS")
        print("="*70)
        for cmd in commands:
            print(cmd)
        print("="*70)


def main():
    parser = argparse.ArgumentParser(description='Analyze data gaps between remote and local DB')
    parser.add_argument('--since', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--until', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--ticker', type=str, default='SPX', help='Underlying ticker (default: SPX)')
    parser.add_argument('--quick', action='store_true', help='Quick overview (last 30 days)')
    parser.add_argument('--detailed', action='store_true', help='Show detailed gap information')
    parser.add_argument('--generate-sync-commands', action='store_true', help='Generate sync commands')
    parser.add_argument('--output', type=str, help='Output file for sync commands')

    args = parser.parse_args()

    # Determine date range
    if args.quick:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
    elif args.since and args.until:
        start_date = datetime.strptime(args.since, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(args.until, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    elif args.since:
        start_date = datetime.strptime(args.since, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.now(timezone.utc)
    else:
        # Default: last 7 days
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)

    print("="*70)
    print("DATA GAP ANALYSIS")
    print("="*70)
    print(f"Underlying: {args.ticker}")
    print(f"Date Range: {start_date.date()} to {end_date.date()}")
    print(f"Remote: {REMOTE_CONFIG['host']}")
    print(f"Local:  {LOCAL_CONFIG['host']}")
    print()

    # Connect to databases
    print("Connecting to databases...")
    try:
        remote_conn = psycopg2.connect(**REMOTE_CONFIG)
        local_conn = psycopg2.connect(**LOCAL_CONFIG)
        print("✅ Connected\n")
    except psycopg2.Error as e:
        print(f"❌ Connection failed: {e}")
        sys.exit(1)

    try:
        # Get daily statistics
        print("Analyzing remote data...")
        remote_stats = get_daily_stats(remote_conn, start_date, end_date, args.ticker)
        print(f"✅ Found {len(remote_stats)} days in remote\n")

        print("Analyzing local data...")
        local_stats = get_daily_stats(local_conn, start_date, end_date, args.ticker)
        print(f"✅ Found {len(local_stats)} days in local\n")

        # Compare coverage
        print("Comparing coverage...")
        gaps = compare_daily_coverage(remote_stats, local_stats)

        # Print summary
        print_gap_summary(gaps, verbose=args.detailed)

        # Generate sync commands if requested
        if args.generate_sync_commands or args.output:
            generate_sync_commands(gaps, args.output)

    finally:
        remote_conn.close()
        local_conn.close()


if __name__ == '__main__':
    main()
