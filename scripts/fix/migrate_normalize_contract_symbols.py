#!/usr/bin/env python3
"""
Migrate existing options_bars data to use normalized contract symbols.

This script:
1. Finds duplicate contracts with different naming conventions
2. Merges them into the canonical format (removes "O:" prefix and spaces)
3. Updates or consolidates rows to use the normalized ticker

Usage:
    python scripts/migrate_normalize_contract_symbols.py --dry-run  # Preview changes
    python scripts/migrate_normalize_contract_symbols.py           # Execute migration
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
from quant_vibe.data.timescale_store import TimescaleStore
from datetime import datetime


def analyze_duplicates(ts_store: TimescaleStore) -> dict:
    """
    Analyze contracts with multiple naming formats.

    Returns:
        dict: {normalized_symbol: [raw_symbol1, raw_symbol2, ...]}
    """
    query = """
    SELECT
        option_ticker,
        COUNT(DISTINCT timestamp) as timestamps,
        MIN(timestamp) as first_seen,
        MAX(timestamp) as last_seen,
        COUNT(*) as total_bars
    FROM options_bars
    GROUP BY option_ticker
    ORDER BY option_ticker;
    """

    with ts_store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    # Group by normalized symbol
    duplicates = {}
    for ticker, timestamps, first_seen, last_seen, total_bars in rows:
        normalized = TimescaleStore.normalize_contract_symbol(ticker)

        if normalized not in duplicates:
            duplicates[normalized] = []

        duplicates[normalized].append({
            'raw': ticker,
            'timestamps': timestamps,
            'first_seen': first_seen,
            'last_seen': last_seen,
            'total_bars': total_bars
        })

    # Filter to only symbols with multiple formats
    duplicates = {k: v for k, v in duplicates.items() if len(v) > 1}

    return duplicates


def migrate_contract_symbols(ts_store: TimescaleStore, dry_run: bool = True):
    """
    Migrate all contract symbols to normalized format.

    Args:
        ts_store: TimescaleStore instance
        dry_run: If True, only preview changes without executing
    """
    print("=" * 80)
    print("CONTRACT SYMBOL NORMALIZATION MIGRATION")
    print("=" * 80)
    print()

    # Analyze duplicates
    print("Step 1: Analyzing contract symbol duplicates...")
    duplicates = analyze_duplicates(ts_store)

    if not duplicates:
        print("✅ No duplicate contract symbols found!")
        return

    print(f"Found {len(duplicates)} contracts with multiple naming formats:")
    print()

    for normalized, variants in list(duplicates.items())[:10]:
        print(f"Normalized: {normalized}")
        for v in variants:
            print(f"  - {v['raw']:<30} {v['timestamps']:>6} timestamps, {v['total_bars']:>8} bars")
        print()

    if len(duplicates) > 10:
        print(f"... and {len(duplicates) - 10} more")
        print()

    # Count total affected rows
    total_rows = sum(v['total_bars'] for variants in duplicates.values() for v in variants)
    print(f"Total rows affected: {total_rows:,}")
    print()

    if dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made")
        print("    Run without --dry-run to execute migration")
        return

    # Execute migration
    print("Step 2: Executing migration...")
    print("Strategy: Merge duplicate rows, keeping normalized symbol")
    print()

    migrated = 0
    errors = 0
    merged = 0

    with ts_store.get_connection() as conn:
        with conn.cursor() as cur:
            # Process each contract with duplicates
            for normalized, variants in duplicates.items():
                # Sort variants: normalized first, then others
                variants_sorted = sorted(variants, key=lambda v: v['raw'] != normalized)

                # Keep track of non-normalized tickers to merge
                to_merge = [v['raw'] for v in variants_sorted if v['raw'] != normalized]

                if not to_merge:
                    continue  # Already normalized

                try:
                    # Strategy: For each timestamp, merge data from duplicates into normalized row
                    # Then delete the duplicate row

                    for old_ticker in to_merge:
                        # Step 1: Insert/Update from old ticker to normalized ticker
                        merge_query = """
                        INSERT INTO options_bars (
                            timestamp, option_ticker, underlying_ticker,
                            open, high, low, close, volume, vwap, transactions,
                            bid, ask, bid_size, ask_size,
                            strike_price, contract_type, expiration_date,
                            implied_volatility, delta, gamma, theta, vega, rho,
                            data_source
                        )
                        SELECT
                            timestamp, %s as option_ticker, underlying_ticker,
                            open, high, low, close, volume, vwap, transactions,
                            bid, ask, bid_size, ask_size,
                            strike_price, contract_type, expiration_date,
                            implied_volatility, delta, gamma, theta, vega, rho,
                            data_source
                        FROM options_bars
                        WHERE option_ticker = %s
                        ON CONFLICT (timestamp, option_ticker) DO UPDATE SET
                            -- Merge: keep non-null values, prefer existing normalized data
                            open = COALESCE(options_bars.open, EXCLUDED.open),
                            high = GREATEST(COALESCE(options_bars.high, 0), COALESCE(EXCLUDED.high, 0)),
                            low = CASE
                                WHEN COALESCE(options_bars.low, 999999) < COALESCE(EXCLUDED.low, 999999)
                                THEN options_bars.low
                                ELSE EXCLUDED.low
                            END,
                            close = COALESCE(options_bars.close, EXCLUDED.close),
                            volume = GREATEST(COALESCE(options_bars.volume, 0), COALESCE(EXCLUDED.volume, 0)),
                            vwap = COALESCE(options_bars.vwap, EXCLUDED.vwap),
                            transactions = COALESCE(options_bars.transactions, EXCLUDED.transactions),
                            bid = COALESCE(options_bars.bid, EXCLUDED.bid),
                            ask = COALESCE(options_bars.ask, EXCLUDED.ask),
                            bid_size = COALESCE(options_bars.bid_size, EXCLUDED.bid_size),
                            ask_size = COALESCE(options_bars.ask_size, EXCLUDED.ask_size),
                            implied_volatility = COALESCE(options_bars.implied_volatility, EXCLUDED.implied_volatility),
                            delta = COALESCE(options_bars.delta, EXCLUDED.delta),
                            gamma = COALESCE(options_bars.gamma, EXCLUDED.gamma),
                            theta = COALESCE(options_bars.theta, EXCLUDED.theta),
                            vega = COALESCE(options_bars.vega, EXCLUDED.vega),
                            rho = COALESCE(options_bars.rho, EXCLUDED.rho),
                            data_source = CASE
                                WHEN options_bars.data_source = EXCLUDED.data_source
                                THEN options_bars.data_source
                                ELSE 'merged'
                            END;
                        """

                        cur.execute(merge_query, (normalized, old_ticker))
                        rows_affected = cur.rowcount

                        # Step 2: Delete the old ticker rows
                        delete_query = "DELETE FROM options_bars WHERE option_ticker = %s;"
                        cur.execute(delete_query, (old_ticker,))
                        rows_deleted = cur.rowcount

                        migrated += rows_affected
                        merged += rows_deleted

                        print(f"  ✅ {old_ticker} → {normalized}")
                        print(f"     Merged {rows_affected:,} rows, deleted {rows_deleted:,} duplicates")

                except Exception as e:
                    errors += 1
                    print(f"  ❌ Error migrating {normalized}: {e}")
                    # Continue with next contract instead of aborting
                    import traceback
                    traceback.print_exc()

            if errors == 0:
                conn.commit()
                print()
                print(f"✅ Migration complete!")
                print(f"   Merged/updated: {migrated:,} rows")
                print(f"   Deleted duplicates: {merged:,} rows")
            else:
                conn.rollback()
                print()
                print(f"⚠️  Migration completed with {errors} errors - rolled back")
                print(f"   Some contracts may not have been migrated")


def main():
    parser = argparse.ArgumentParser(
        description="Normalize contract symbols in TimescaleDB"
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
        migrate_contract_symbols(ts_store, dry_run=args.dry_run)
    finally:
        ts_store.close()


if __name__ == "__main__":
    main()
