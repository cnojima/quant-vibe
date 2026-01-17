#!/usr/bin/env python3
"""Sync options data from remote TimescaleDB to local instance."""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# Load environment variables from .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Remote DB config (from .env)
REMOTE_CONFIG = {
    'host': os.getenv('REMOTE_TIMESCALE_HOST'),
    'port': int(os.getenv('REMOTE_TIMESCALE_PORT', '5432')),
    'database': os.getenv('REMOTE_TIMESCALE_DB', 'options_data'),
    'user': os.getenv('REMOTE_TIMESCALE_USER', 'quantvibe'),
    'password': os.getenv('REMOTE_TIMESCALE_PASSWORD')
}

# Local DB config (from .env)
LOCAL_CONFIG = {
    'host': os.getenv('TIMESCALE_HOST', 'localhost'),
    'port': int(os.getenv('TIMESCALE_PORT', '5432')),
    'database': os.getenv('TIMESCALE_DB', 'options_data'),
    'user': os.getenv('TIMESCALE_USER', 'quantvibe'),
    'password': os.getenv('TIMESCALE_PASSWORD', 'quantvibe_dev')
}

def validate_config():
    """Validate that required environment variables are set."""
    required_remote = ['REMOTE_TIMESCALE_HOST', 'REMOTE_TIMESCALE_PASSWORD']
    missing = [var for var in required_remote if not os.getenv(var)]

    if missing:
        print(f"\n❌ ERROR: Missing required environment variables in .env:")
        for var in missing:
            print(f"   - {var}")
        print(f"\nPlease add these to {env_path}")
        print("\nExample:")
        print("  REMOTE_TIMESCALE_HOST=your-remote-host.com")
        print("  REMOTE_TIMESCALE_PORT=5432")
        print("  REMOTE_TIMESCALE_DB=options_data")
        print("  REMOTE_TIMESCALE_USER=quantvibe")
        print("  REMOTE_TIMESCALE_PASSWORD=your-remote-password")
        print()
        sys.exit(1)

    print(f"✅ Configuration loaded from {env_path}")
    print(f"   Remote: {REMOTE_CONFIG['user']}@{REMOTE_CONFIG['host']}:{REMOTE_CONFIG['port']}/{REMOTE_CONFIG['database']}")
    print(f"   Local:  {LOCAL_CONFIG['user']}@{LOCAL_CONFIG['host']}:{LOCAL_CONFIG['port']}/{LOCAL_CONFIG['database']}")
    print()

def get_last_sync_time(local_conn, source='remote_sync'):
    """Get timestamp of last successful sync."""
    with local_conn.cursor() as cur:
        cur.execute("""
            SELECT MAX(timestamp) 
            FROM options_bars 
            WHERE data_source LIKE %s
        """, (f'%{source}%',))
        result = cur.fetchone()
        return result[0] if result and result[0] else None

def sync_options_bars_with_until(since_time=None, until_time=None, batch_size=10000):
    """Sync options_bars from remote to local with date range.

    Args:
        since_time: Only sync data after this timestamp (None = last 24 hours)
        until_time: Only sync data before this timestamp (None = no upper bound)
        batch_size: Number of rows per batch insert
    """
    # Validate configuration first
    validate_config()

    # Default: sync last 24 hours if no since_time
    if since_time is None:
        since_time = datetime.now(timezone.utc) - timedelta(days=1)

    print(f"{'='*70}")
    print(f"SYNCING OPTIONS DATA FROM REMOTE")
    print(f"{'='*70}")
    print(f"Since: {since_time}")
    if until_time:
        print(f"Until: {until_time}")
    print(f"Batch size: {batch_size:,}")
    print()

    # Connect to remote
    print("1. Connecting to remote database...")
    try:
        remote_conn = psycopg2.connect(**REMOTE_CONFIG)
        print(f"   ✅ Connected to {REMOTE_CONFIG['host']}")
    except psycopg2.Error as e:
        print(f"   ❌ Failed to connect to remote database: {e}")
        print(f"   Check your REMOTE_TIMESCALE_* variables in .env")
        sys.exit(1)

    # Connect to local
    print("2. Connecting to local database...")
    try:
        local_conn = psycopg2.connect(**LOCAL_CONFIG)
        print(f"   ✅ Connected to {LOCAL_CONFIG['host']}")
    except psycopg2.Error as e:
        print(f"   ❌ Failed to connect to local database: {e}")
        print(f"   Check your TIMESCALE_* variables in .env")
        remote_conn.close()
        sys.exit(1)

    try:
        # Query remote data
        query_msg = f"\n3. Querying remote data since {since_time}"
        if until_time:
            query_msg += f" until {until_time}"
        print(query_msg + "...")

        with remote_conn.cursor() as cur:
            if until_time:
                cur.execute("""
                    SELECT
                        timestamp, option_ticker, underlying_ticker,
                        open, high, low, close, volume, vwap, transactions,
                        bid, ask, bid_size, ask_size,
                        strike_price, contract_type, expiration_date,
                        implied_volatility, delta, gamma, theta, vega, rho,
                        data_source
                    FROM options_bars
                    WHERE timestamp >= %s AND timestamp < %s
                    ORDER BY timestamp ASC
                """, (since_time, until_time))
            else:
                cur.execute("""
                    SELECT
                        timestamp, option_ticker, underlying_ticker,
                        open, high, low, close, volume, vwap, transactions,
                        bid, ask, bid_size, ask_size,
                        strike_price, contract_type, expiration_date,
                        implied_volatility, delta, gamma, theta, vega, rho,
                        data_source
                    FROM options_bars
                    WHERE timestamp >= %s
                    ORDER BY timestamp ASC
                """, (since_time,))

            rows = cur.fetchall()
            total_rows = len(rows)

        print(f"   ✅ Fetched {total_rows:,} rows from remote")

        if total_rows == 0:
            print("\n   No new data to sync.")
            return

        # Insert into local (with conflict handling)
        print(f"\n4. Inserting into local database...")
        with local_conn.cursor() as cur:
            # Use a temporary table approach for efficient bulk insert without duplicates
            print("   Creating temporary table for bulk import...")

            # Create temp table with same structure
            cur.execute("""
                CREATE TEMP TABLE temp_options_bars (
                    timestamp TIMESTAMPTZ,
                    option_ticker TEXT,
                    underlying_ticker TEXT,
                    open NUMERIC,
                    high NUMERIC,
                    low NUMERIC,
                    close NUMERIC,
                    volume BIGINT,
                    vwap NUMERIC,
                    transactions INTEGER,
                    bid NUMERIC,
                    ask NUMERIC,
                    bid_size INTEGER,
                    ask_size INTEGER,
                    strike_price NUMERIC,
                    contract_type TEXT,
                    expiration_date DATE,
                    implied_volatility NUMERIC,
                    delta NUMERIC,
                    gamma NUMERIC,
                    theta NUMERIC,
                    vega NUMERIC,
                    rho NUMERIC,
                    data_source TEXT
                )
            """)

            # Bulk insert all data into temp table (very fast)
            print(f"   Bulk loading {total_rows:,} rows into temp table...")
            insert_temp_query = """
                INSERT INTO temp_options_bars VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """

            for i in range(0, total_rows, batch_size):
                batch = rows[i:i+batch_size]
                execute_batch(cur, insert_temp_query, batch, page_size=batch_size)
                print(f"   Loading: {min(i+batch_size, total_rows):,}/{total_rows:,} ({min(i+batch_size, total_rows)/total_rows*100:.1f}%)")

            # Now insert only non-duplicate rows from temp to main table
            print("   Merging non-duplicate rows into main table...")
            cur.execute("""
                INSERT INTO options_bars (
                    timestamp, option_ticker, underlying_ticker,
                    open, high, low, close, volume, vwap, transactions,
                    bid, ask, bid_size, ask_size,
                    strike_price, contract_type, expiration_date,
                    implied_volatility, delta, gamma, theta, vega, rho,
                    data_source
                )
                SELECT DISTINCT t.*
                FROM temp_options_bars t
                LEFT JOIN options_bars o
                    ON t.timestamp = o.timestamp
                    AND t.option_ticker = o.option_ticker
                WHERE o.timestamp IS NULL
            """)

            inserted = cur.rowcount
            skipped = total_rows - inserted

            # Drop temp table (happens automatically at end of transaction anyway)
            cur.execute("DROP TABLE temp_options_bars")

            local_conn.commit()

        print(f"\n   ✅ Successfully synced: {inserted:,} rows inserted, {skipped:,} rows skipped (duplicates)")

        # Show date range synced
        first_ts = rows[0][0]
        last_ts = rows[-1][0]
        print(f"\n   Date range: {first_ts} to {last_ts}")

    except psycopg2.Error as e:
        print(f"\n   ❌ Database error during sync: {e}")
        local_conn.rollback()
        raise
    except Exception as e:
        print(f"\n   ❌ Unexpected error during sync: {e}")
        local_conn.rollback()
        raise
    finally:
        remote_conn.close()
        local_conn.close()
        print(f"\n{'='*70}")
        print("SYNC COMPLETE")
        print(f"{'='*70}\n")


def sync_options_bars(since_time=None, batch_size=10000):
    """Sync options_bars from remote to local (backward compatible).

    Args:
        since_time: Only sync data after this timestamp (None = last 24 hours)
        batch_size: Number of rows per batch insert
    """
    return sync_options_bars_with_until(since_time=since_time, until_time=None, batch_size=batch_size)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Sync options data from remote to local DB')
    parser.add_argument('--since', type=str, help='Sync data since this date (YYYY-MM-DD)')
    parser.add_argument('--until', type=str, help='Sync data until this date (YYYY-MM-DD, exclusive)')
    parser.add_argument('--hours', type=int, help='Sync last N hours')
    parser.add_argument('--days', type=int, help='Sync last N days (default: 1 if no args)')
    parser.add_argument('--auto', action='store_true', help='Auto-detect last sync time')
    parser.add_argument('--batch-days', type=int, default=7, help='Split large ranges into N-day batches (default: 7)')

    args = parser.parse_args()

    # Determine sync start time
    if args.auto:
        print("Auto-detecting last sync time...")
        local_conn = psycopg2.connect(**LOCAL_CONFIG)
        since_time = get_last_sync_time(local_conn)
        local_conn.close()

        if since_time is None:
            since_time = datetime.now(timezone.utc) - timedelta(days=7)
            print(f"No previous sync found. Starting from 7 days ago.")
        until_time = None
    elif args.since and args.until:
        since_parts = args.since.split('-')
        since_time = datetime(int(since_parts[0]), int(since_parts[1]), int(since_parts[2]), tzinfo=timezone.utc)
        until_parts = args.until.split('-')
        until_time = datetime(int(until_parts[0]), int(until_parts[1]), int(until_parts[2]), tzinfo=timezone.utc)
    elif args.since:
        parts = args.since.split('-')
        since_time = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)
        until_time = None
    elif args.hours:
        since_time = datetime.now(timezone.utc) - timedelta(hours=args.hours)
        until_time = None
    elif args.days:
        since_time = datetime.now(timezone.utc) - timedelta(days=args.days)
        until_time = None
    else:
        # Default: last 24 hours
        since_time = datetime.now(timezone.utc) - timedelta(days=1)
        until_time = None

    # If date range is large, split into batches
    if until_time and (until_time - since_time).days > args.batch_days:
        print(f"\n📦 Large date range detected. Splitting into {args.batch_days}-day batches...\n")
        current = since_time
        batch_num = 1

        while current < until_time:
            batch_end = min(current + timedelta(days=args.batch_days), until_time)
            print(f"\n{'='*70}")
            print(f"BATCH {batch_num}: {current.date()} to {batch_end.date()}")
            print(f"{'='*70}\n")

            # Temporarily modify since_time for this batch
            sync_options_bars_with_until(since_time=current, until_time=batch_end)

            current = batch_end
            batch_num += 1
    else:
        # Single sync
        if until_time:
            sync_options_bars_with_until(since_time=since_time, until_time=until_time)
        else:
            sync_options_bars(since_time=since_time)
