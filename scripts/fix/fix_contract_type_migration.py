#!/usr/bin/env python3
"""
Migrate contract_type values from single letters to full words.

This script standardizes contract_type values:
- 'c' → 'call'
- 'p' → 'put'

Safe to run multiple times (idempotent).
"""

import sys
import os
from pathlib import Path
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from quant_vibe.data.timescale_store import TimescaleStore

load_dotenv()


def show_current_state(ts_store: TimescaleStore):
    """Show current contract_type distribution."""
    query = """
        SELECT
            contract_type,
            COUNT(*) as count,
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM options_bars
        GROUP BY contract_type
        ORDER BY contract_type;
    """

    print("\n" + "="*70)
    print("CURRENT STATE")
    print("="*70)

    with ts_store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            results = cur.fetchall()

            if results:
                print(f"\n{'Contract Type':<15} {'Count':>12} {'Earliest':<20} {'Latest':<20}")
                print("-"*70)
                for row in results:
                    contract_type = row[0] if row[0] else 'NULL'
                    count = f"{row[1]:,}"
                    earliest = row[2].strftime('%Y-%m-%d %H:%M:%S') if row[2] else 'N/A'
                    latest = row[3].strftime('%Y-%m-%d %H:%M:%S') if row[3] else 'N/A'
                    print(f"{contract_type:<15} {count:>12} {earliest:<20} {latest:<20}")
            else:
                print("\nNo data found.")


def migrate_contract_types(ts_store: TimescaleStore, dry_run: bool = False):
    """
    Migrate contract_type values from single letters to full words.

    Args:
        ts_store: TimescaleDB store instance
        dry_run: If True, show what would be changed without applying
    """
    print("\n" + "="*70)
    if dry_run:
        print("MIGRATION PREVIEW (DRY RUN)")
    else:
        print("RUNNING MIGRATION")
    print("="*70)

    # Count records to update
    count_query = """
        SELECT
            COUNT(*) FILTER (WHERE contract_type = 'c') as c_count,
            COUNT(*) FILTER (WHERE contract_type = 'p') as p_count
        FROM options_bars
    """

    with ts_store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_query)
            counts = cur.fetchone()
            c_count = counts[0]
            p_count = counts[1]

    print(f"\nRecords to update:")
    print(f"  'c' → 'call': {c_count:,} records")
    print(f"  'p' → 'put':  {p_count:,} records")
    print(f"  Total:        {c_count + p_count:,} records")

    if c_count == 0 and p_count == 0:
        print("\n✅ No records need migration!")
        return

    if dry_run:
        print("\n🔍 DRY RUN - No changes will be made")
        return

    # Apply migration
    print("\n⚙️  Applying migration...")
    print("  (This may take a moment for large datasets...)")

    update_queries = [
        ("UPDATE options_bars SET contract_type = 'call' WHERE contract_type = 'c'", 'c→call'),
        ("UPDATE options_bars SET contract_type = 'put' WHERE contract_type = 'p'", 'p→put'),
    ]

    total_updated = 0

    with ts_store.get_connection() as conn:
        with conn.cursor() as cur:
            # Temporarily increase decompression limit for this migration
            # (TimescaleDB compresses old data and needs to decompress it for updates)
            print("  ⚙️  Setting unlimited decompression for large update...")
            cur.execute("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0")

            for query, description in update_queries:
                print(f"  ⚙️  Updating {description}...")
                cur.execute(query)
                rows_updated = cur.rowcount
                total_updated += rows_updated
                print(f"  ✅ {description}: {rows_updated:,} rows updated")

            # Commit transaction
            conn.commit()

    print(f"\n✅ Migration complete! Updated {total_updated:,} rows total")


def verify_migration(ts_store: TimescaleStore):
    """Verify that migration was successful."""
    print("\n" + "="*70)
    print("VERIFICATION")
    print("="*70)

    query = """
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE contract_type = 'call') as call_count,
            COUNT(*) FILTER (WHERE contract_type = 'put') as put_count,
            COUNT(*) FILTER (WHERE contract_type NOT IN ('call', 'put')) as invalid_count
        FROM options_bars
    """

    with ts_store.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            result = cur.fetchone()

            total = result[0]
            call_count = result[1]
            put_count = result[2]
            invalid_count = result[3]

    print(f"\nTotal records:           {total:,}")
    print(f"Call contracts:          {call_count:,} ({call_count/total*100:.1f}%)")
    print(f"Put contracts:           {put_count:,} ({put_count/total*100:.1f}%)")
    print(f"Invalid contract_type:   {invalid_count:,}")

    if invalid_count == 0:
        print("\n✅ All contract_type values are valid!")
    else:
        print("\n⚠️  Warning: Some invalid contract_type values remain")

        # Show invalid values
        invalid_query = """
            SELECT DISTINCT contract_type, COUNT(*) as count
            FROM options_bars
            WHERE contract_type NOT IN ('call', 'put')
            GROUP BY contract_type
        """

        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(invalid_query)
                invalid_values = cur.fetchall()

                print("\nInvalid values found:")
                for value, count in invalid_values:
                    print(f"  '{value}': {count:,} records")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate contract_type values from single letters to full words",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without applying'
    )

    parser.add_argument(
        '--db-profile',
        choices=['local', 'remote'],
        help='Database profile to use (local or remote)'
    )

    args = parser.parse_args()

    print("="*70)
    print("CONTRACT_TYPE MIGRATION")
    print("="*70)
    print("\nThis script will standardize contract_type values:")
    print("  'c' → 'call'")
    print("  'p' → 'put'")
    print()

    # Connect to database
    use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"

    if args.db_profile == "remote":
        use_remote = True
    elif args.db_profile == "local":
        use_remote = False

    db_location = "remote" if use_remote else "local"
    print(f"Connecting to {db_location} TimescaleDB...")

    if use_remote:
        ts_store = TimescaleStore(
            host=os.getenv("REMOTE_TIMESCALE_HOST"),
            port=int(os.getenv("REMOTE_TIMESCALE_PORT", "5432")),
            database=os.getenv("REMOTE_TIMESCALE_DB"),
            user=os.getenv("REMOTE_TIMESCALE_USER"),
            password=os.getenv("REMOTE_TIMESCALE_PASSWORD"),
        )
    else:
        ts_store = TimescaleStore()

    print(f"✅ Connected to {db_location} database")

    try:
        # Show current state
        show_current_state(ts_store)

        # Run migration
        migrate_contract_types(ts_store, dry_run=args.dry_run)

        # Verify results
        if not args.dry_run:
            verify_migration(ts_store)

        # Show final state
        if not args.dry_run:
            show_current_state(ts_store)

    finally:
        ts_store.close()

    print("\n" + "="*70)
    print("MIGRATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
