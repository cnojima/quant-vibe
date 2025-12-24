"""
Backfill missing expiration_date values by parsing them from option tickers.

SPXW option tickers have the format: SPXW  YYMMDDX########
Where:
- YYMM DD = expiration date (year, month, day)
- X = P (put) or C (call)
- ######## = strike price

Example: SPXW  260121P06200000 = Jan 21, 2026 Put at 6200 strike
"""

import sys
from pathlib import Path
from datetime import datetime
import re

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.timescale_store import TimescaleStore


def parse_expiration_from_ticker(ticker: str) -> str | None:
    """
    Parse expiration date from SPXW option ticker.

    Args:
        ticker: Option ticker in format "SPXW  YYMMDDX########"

    Returns:
        Expiration date string in format 'YYYY-MM-DD' or None if parse fails
    """
    # Remove extra spaces
    ticker = ticker.strip()

    # Pattern: SPXW followed by 6 digits (YYMMDD), then P or C
    # Example: "SPXW  260121P06200000" or "SPXW260121P06200000"
    pattern = r'SPXW\s*(\d{6})[PC]'
    match = re.search(pattern, ticker)

    if not match:
        return None

    date_str = match.group(1)  # YYMMDD

    try:
        # Parse YYMMDD
        yy = int(date_str[0:2])
        mm = int(date_str[2:4])
        dd = int(date_str[4:6])

        # Convert YY to YYYY (assume 2000+ for 00-99)
        yyyy = 2000 + yy

        # Validate and create date
        exp_date = datetime(yyyy, mm, dd).date()
        return str(exp_date)

    except (ValueError, IndexError):
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Backfill missing expiration_date values from option tickers')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--limit', type=int, help='Limit number of rows to process (for testing)')
    args = parser.parse_args()

    ts_store = TimescaleStore()

    try:
        print("="*70)
        print("BACKFILL EXPIRATION DATES FROM OPTION TICKERS")
        print("="*70)
        print()

        # Step 1: Find contracts with NULL expiration_date
        print("Step 1: Finding contracts with NULL expiration_date...")

        query_count = """
        SELECT COUNT(DISTINCT option_ticker) as count
        FROM options_bars
        WHERE underlying_ticker = 'SPX'
            AND expiration_date IS NULL
        """

        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_count)
                null_count = cur.fetchone()[0]

        print(f"Found {null_count:,} unique contracts with NULL expiration_date")
        print()

        if null_count == 0:
            print("✅ No contracts need backfilling!")
            return

        # Step 2: Get distinct tickers with NULL expiration_date
        print("Step 2: Fetching distinct option tickers...")

        query_tickers = """
        SELECT DISTINCT option_ticker
        FROM options_bars
        WHERE underlying_ticker = 'SPX'
            AND expiration_date IS NULL
        """

        if args.limit:
            query_tickers += f" LIMIT {args.limit}"

        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_tickers)
                tickers = [row[0] for row in cur.fetchall()]

        print(f"Processing {len(tickers):,} tickers...")
        print()

        # Step 3: Parse expiration dates and prepare updates
        print("Step 3: Parsing expiration dates from tickers...")

        updates = []
        parse_errors = []

        for ticker in tickers:
            exp_date = parse_expiration_from_ticker(ticker)

            if exp_date:
                updates.append((exp_date, ticker))
            else:
                parse_errors.append(ticker)

        print(f"✅ Successfully parsed: {len(updates):,} contracts")
        if parse_errors:
            print(f"❌ Failed to parse: {len(parse_errors):,} contracts")
            print("\nSample parse errors:")
            for ticker in parse_errors[:5]:
                print(f"  - {ticker}")
        print()

        if not updates:
            print("No valid updates to apply.")
            return

        # Step 4: Show sample updates
        print("Sample updates:")
        for exp_date, ticker in updates[:10]:
            print(f"  {ticker} -> {exp_date}")
        print()

        # Step 5: Apply updates
        if args.dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
            print(f"Would update {len(updates):,} contracts")
        else:
            print(f"Step 4: Updating {len(updates):,} contracts...")

            update_query = """
            UPDATE options_bars
            SET expiration_date = %s
            WHERE option_ticker = %s
                AND expiration_date IS NULL
            """

            with ts_store.get_connection() as conn:
                with conn.cursor() as cur:
                    # Use executemany for batch update
                    from psycopg2.extras import execute_batch
                    execute_batch(cur, update_query, updates, page_size=1000)
                    rows_updated = cur.rowcount
                conn.commit()

            print(f"✅ Updated {rows_updated:,} rows")

        print()
        print("="*70)
        print("BACKFILL COMPLETE")
        print("="*70)

    finally:
        ts_store.close()


if __name__ == "__main__":
    main()
