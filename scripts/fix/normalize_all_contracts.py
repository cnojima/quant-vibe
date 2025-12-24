#!/usr/bin/env python3
"""
Normalize ALL contract symbols in options_bars table.

This script updates all rows to use the normalized format:
- Removes "O:" prefix
- Removes extra spaces

Usage:
    python scripts/normalize_all_contracts.py --dry-run  # Preview
    python scripts/normalize_all_contracts.py            # Execute
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
from quant_vibe.data.timescale_store import TimescaleStore


def normalize_all_contracts(ts_store: TimescaleStore, dry_run: bool = True):
    """
    Normalize all contract symbols using SQL REPLACE.

    Args:
        ts_store: TimescaleStore instance
        dry_run: If True, only preview changes
        batch_size: Process in batches to show progress
    """
    print("=" * 80)
    print("NORMALIZE ALL CONTRACT SYMBOLS")
    print("=" * 80)
    print()

    with ts_store.get_connection() as conn:
        with conn.cursor() as cur:
            # Count rows needing normalization
            cur.execute("""
                SELECT COUNT(*)
                FROM options_bars
                WHERE option_ticker LIKE 'O:%' OR option_ticker LIKE '%  %'
            """)
            rows_to_update = cur.fetchone()[0]

            if rows_to_update == 0:
                print("✅ All contract symbols are already normalized!")
                return

            print(f"Found {rows_to_update:,} rows to normalize")
            print()

            if dry_run:
                print("⚠️  DRY RUN MODE - showing sample changes:")
                print()

                # Show examples
                cur.execute("""
                    SELECT DISTINCT option_ticker
                    FROM options_bars
                    WHERE option_ticker LIKE 'O:%' OR option_ticker LIKE '%  %'
                    LIMIT 10
                """)

                for (ticker,) in cur.fetchall():
                    normalized = TimescaleStore.normalize_contract_symbol(ticker)
                    print(f"  {ticker:<35} → {normalized}")

                print()
                print("Run without --dry-run to execute normalization")
                return

            # Execute normalization using SQL REPLACE
            print("Executing normalization...")
            print("This may take a few minutes for large datasets...")
            print()

            # Increase TimescaleDB decompression limit for large updates
            cur.execute("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0;")
            print("  ℹ️  Increased TimescaleDB decompression limit to unlimited")
            print()

            # Step 1: Remove "O:" prefix
            cur.execute("""
                UPDATE options_bars
                SET option_ticker = SUBSTRING(option_ticker FROM 3)
                WHERE option_ticker LIKE 'O:%'
            """)
            rows_updated_prefix = cur.rowcount
            print(f"  ✅ Removed 'O:' prefix from {rows_updated_prefix:,} rows")

            # Step 2: Remove spaces
            cur.execute("""
                UPDATE options_bars
                SET option_ticker = REPLACE(option_ticker, ' ', '')
                WHERE option_ticker LIKE '%  %'
            """)
            rows_updated_spaces = cur.rowcount
            print(f"  ✅ Removed spaces from {rows_updated_spaces:,} rows")

            # Commit transaction
            conn.commit()

            print()
            print(f"✅ Migration complete!")
            print(f"   Total rows updated: {rows_updated_prefix + rows_updated_spaces:,}")
            print()

            # Verify
            cur.execute("""
                SELECT COUNT(*)
                FROM options_bars
                WHERE option_ticker LIKE 'O:%' OR option_ticker LIKE '%  %'
            """)
            remaining = cur.fetchone()[0]

            if remaining == 0:
                print("✅ Verification: All symbols normalized!")
            else:
                print(f"⚠️  Warning: {remaining:,} rows still need normalization")


def main():
    parser = argparse.ArgumentParser(
        description="Normalize all contract symbols in TimescaleDB"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing",
    )
    parser.add_argument(
        "--db-profile",
        choices=["local", "remote"],
        help="Database profile (local or remote)",
    )

    args = parser.parse_args()

    # Connect to database
    if args.db_profile == "remote":
        import os
        ts_store = TimescaleStore(
            host=os.getenv("REMOTE_TIMESCALE_HOST"),
            port=int(os.getenv("REMOTE_TIMESCALE_PORT", "5432")),
            database=os.getenv("REMOTE_TIMESCALE_DB"),
            user=os.getenv("REMOTE_TIMESCALE_USER"),
            password=os.getenv("REMOTE_TIMESCALE_PASSWORD"),
        )
    else:
        ts_store = TimescaleStore()

    try:
        normalize_all_contracts(ts_store, dry_run=args.dry_run)
    finally:
        ts_store.close()


if __name__ == "__main__":
    main()
