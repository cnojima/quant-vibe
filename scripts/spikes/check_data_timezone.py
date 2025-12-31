#!/usr/bin/env python3
"""Check timezone handling in options data."""

import sys
from pathlib import Path
from datetime import datetime, timezone
import pytz

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.timescale_store import TimescaleStore

print("\n" + "="*70)
print("CHECKING DATA TIMEZONE ISSUES")
print("="*70)

# Initialize store
ts = TimescaleStore()

# Check current system time
print("\n1. System Time Information:")
now_local = datetime.now()
now_utc = datetime.now(timezone.utc)
now_et = datetime.now(pytz.timezone('US/Eastern'))

print(f"   Local time:   {now_local} (timezone: {now_local.astimezone().tzinfo})")
print(f"   UTC time:     {now_utc}")
print(f"   Eastern time: {now_et}")

# Check available data
print("\n2. Checking SPX options data availability...")
query = """
    SELECT
        MIN(timestamp) as earliest,
        MAX(timestamp) as latest,
        COUNT(*) as total_bars,
        COUNT(DISTINCT DATE(timestamp)) as unique_days
    FROM options_bars
    WHERE underlying_ticker = 'SPX'
"""

try:
    with ts.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            result = cursor.fetchone()

            if result:
                print(f"   ✅ Data found:")
                print(f"      - Earliest: {result[0]} (UTC)")
                print(f"      - Latest:   {result[1]} (UTC)")
                print(f"      - Total bars: {result[2]:,}")
                print(f"      - Unique days: {result[3]}")

                # Convert to local time
                if result[0]:
                    earliest_local = result[0].astimezone()
                    latest_local = result[1].astimezone()
                    print(f"\n      In local time:")
                    print(f"      - Earliest: {earliest_local}")
                    print(f"      - Latest:   {latest_local}")
            else:
                print("   ❌ No data found")

except Exception as e:
    print(f"   ❌ Query failed: {e}")

# Check today's data specifically
print("\n3. Checking data for today...")

# Try with UTC
query_utc = """
    SELECT
        MIN(timestamp) as earliest,
        MAX(timestamp) as latest,
        COUNT(*) as count
    FROM options_bars
    WHERE underlying_ticker = 'SPX'
    AND timestamp >= DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')
    AND timestamp < DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC') + INTERVAL '1 day'
"""

try:
    with ts.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query_utc)
            result = cursor.fetchone()

            if result and result[2] > 0:
                print(f"   ✅ Found {result[2]} bars for today (UTC)")
                print(f"      - Earliest: {result[0]}")
                print(f"      - Latest:   {result[1]}")
            else:
                print("   ❌ No data for today (UTC)")
except Exception as e:
    print(f"   ❌ Query failed: {e}")

# Check recent dates
print("\n4. Checking recent dates with data...")
query_recent = """
    SELECT
        DATE(timestamp) as date,
        COUNT(*) as bars,
        MIN(timestamp) as first_bar,
        MAX(timestamp) as last_bar
    FROM options_bars
    WHERE underlying_ticker = 'SPX'
    AND timestamp >= NOW() - INTERVAL '7 days'
    GROUP BY DATE(timestamp)
    ORDER BY date DESC
    LIMIT 10
"""

try:
    with ts.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query_recent)
            results = cursor.fetchall()

            if results:
                print(f"   ✅ Recent dates with data:")
                print(f"      {'Date':<12} {'Bars':>8} {'First Bar':<28} {'Last Bar':<28}")
                print(f"      {'-'*12} {'-'*8} {'-'*28} {'-'*28}")
                for row in results:
                    print(f"      {row[0]} {row[1]:>8,} {row[2]} {row[3]}")
            else:
                print("   ❌ No recent data found")

except Exception as e:
    print(f"   ❌ Query failed: {e}")

# Test backtest date conversion
print("\n5. Testing backtest date conversion...")

from datetime import date

backtest_date = date(2025, 12, 17)
print(f"   Backtest date (date object): {backtest_date}")

# Convert to datetime (start of day)
start_naive = datetime.combine(backtest_date, datetime.min.time())
print(f"   As naive datetime: {start_naive}")

# Make timezone-aware (assume local)
start_local = start_naive.replace(tzinfo=pytz.timezone('US/Eastern'))
print(f"   As Eastern time: {start_local}")

# Convert to UTC
start_utc = start_local.astimezone(timezone.utc)
print(f"   As UTC: {start_utc}")

print("\n   Issue: If backtest uses naive datetime, it might not match UTC data!")

# Check what data exists around that time
print("\n6. Looking for data around backtest date...")

query_around = """
    SELECT
        DATE(timestamp) as date,
        COUNT(*) as bars
    FROM options_bars
    WHERE underlying_ticker = 'SPX'
    AND timestamp >= %s::date - INTERVAL '3 days'
    AND timestamp <= %s::date + INTERVAL '3 days'
    GROUP BY DATE(timestamp)
    ORDER BY date DESC
"""

try:
    with ts.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query_around, (backtest_date, backtest_date))
            results = cursor.fetchall()

            if results:
                print(f"   Data around {backtest_date}:")
                for row in results:
                    marker = " <-- Backtest date" if row[0] == backtest_date else ""
                    print(f"      {row[0]}: {row[1]:,} bars{marker}")
            else:
                print(f"   No data found around {backtest_date}")

except Exception as e:
    print(f"   ❌ Query failed: {e}")

print("\n" + "="*70)
print("DIAGNOSIS & RECOMMENDATIONS")
print("="*70)

print("\nPossible Issues:")
print("  1. Database stores timestamps in UTC")
print("  2. Backtest queries using naive datetime (no timezone)")
print("  3. Date mismatches due to timezone conversion")
print("  4. Data might exist but query doesn't find it")

print("\nSolution:")
print("  - Ensure backtest converts dates to UTC before querying")
print("  - Use timezone-aware datetimes throughout")
print("  - Check TimescaleStore.get_options_for_backtest() timezone handling")

print()
