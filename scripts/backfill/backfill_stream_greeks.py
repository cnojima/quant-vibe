#!/usr/bin/env python3
"""Backfill missing Greeks and contract details for streaming data.

This script:
1. Finds options_bars records from schwabdev_stream with NULL Greeks
2. Fetches contract details from Schwab option chain API
3. Updates records with Greeks, strike price, and implied volatility

Safe to run during off-market hours. Idempotent (can run multiple times).

Usage:
    # Backfill all missing data
    python scripts/backfill/backfill_stream_greeks.py

    # Backfill specific date range
    python scripts/backfill/backfill_stream_greeks.py --start 2025-12-10 --end 2025-12-17

    # Dry run (show what would be updated)
    python scripts/backfill/backfill_stream_greeks.py --dry-run

    # Limit number of records
    python scripts/backfill/backfill_stream_greeks.py --limit 1000
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple, Optional
import argparse
import time

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import schwabdev
from dotenv import load_dotenv
from streaming_service.enrich_stream_with_chain import OptionContractEnricher
from quant_vibe.data.timescale_store import TimescaleStore

load_dotenv()


class StreamDataBackfiller:
    """Backfill missing Greeks and contract details in streaming data."""

    def __init__(self, dry_run: bool = False):
        """
        Initialize backfiller.

        Args:
            dry_run: If True, show what would be updated but don't modify database
        """
        self.dry_run = dry_run

        # Initialize clients
        print("\nInitializing clients...")
        tokens_db = "tokens/schwabdev_tokens.db"

        self.schwab_client = schwabdev.Client(
            os.getenv("SCHWAB_API_KEY"),
            os.getenv("SCHWAB_API_SECRET"),
            os.getenv("SCHWAB_CALLBACK_URL"),
            tokens_db=tokens_db,
        )

        self.enricher = OptionContractEnricher(self.schwab_client)
        self.ts_store = TimescaleStore()

        print("✓ Schwab client initialized")
        print("✓ Contract enricher initialized")
        print("✓ TimescaleDB connected")

        if self.dry_run:
            print("\n⚠️  DRY RUN MODE - No changes will be made to database")

    def find_records_needing_enrichment(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Tuple]:
        """
        Find records with missing Greeks/strike/IV.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Optional limit on number of records

        Returns:
            List of (timestamp, option_ticker) tuples
        """
        print("\n" + "="*70)
        print("FINDING RECORDS NEEDING ENRICHMENT")
        print("="*70)

        query = """
            SELECT DISTINCT timestamp, option_ticker
            FROM options_bars
            WHERE (
                strike_price IS NULL
                OR delta IS NULL
                OR gamma IS NULL
                OR theta IS NULL
                OR vega IS NULL
                OR rho IS NULL
                OR implied_volatility IS NULL
            )
        """

        params = []

        if start_date:
            query += " AND timestamp >= %s"
            params.append(start_date)
            print(f"Start date: {start_date}")

        if end_date:
            query += " AND timestamp <= %s"
            params.append(end_date)
            print(f"End date: {end_date}")

        query += " ORDER BY timestamp DESC"

        if limit:
            query += " LIMIT %s"
            params.append(limit)
            print(f"Limit: {limit}")

        print("\nQuerying database...")

        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params if params else None)
                results = cur.fetchall()

        print(f"✓ Found {len(results):,} records needing enrichment")

        if results:
            # Show date range
            earliest = results[-1][0]  # Results ordered DESC
            latest = results[0][0]
            print(f"  Date range: {earliest} to {latest}")

            # Count unique symbols
            unique_symbols = set(r[1] for r in results)
            print(f"  Unique contracts: {len(unique_symbols)}")

        return results

    def get_unique_symbols(self, records: List[Tuple]) -> List[str]:
        """Extract unique option symbols from records."""
        return sorted(set(r[1] for r in records))

    def parse_strike_from_symbol(self, symbol: str) -> Optional[float]:
        """
        Parse strike price from option symbol as fallback.

        Format: "SPXW  251219C06100000"
                         ^ Type
                          ^^^^^^^^ Strike × 1000

        Args:
            symbol: Option symbol

        Returns:
            Strike price or None
        """
        try:
            # Last 8 characters are strike × 1000
            strike_str = symbol.replace(" ", "")[-8:]
            return float(strike_str) / 1000.0
        except (ValueError, IndexError):
            return None

    def update_record(
        self,
        timestamp: datetime,
        option_ticker: str,
        enriched_data: Dict
    ) -> bool:
        """
        Update a single record with enriched data.

        Args:
            timestamp: Record timestamp
            option_ticker: Option symbol
            enriched_data: Dict with contract details

        Returns:
            True if updated successfully
        """
        update_query = """
            UPDATE options_bars
            SET
                strike_price = COALESCE(strike_price, %s),
                implied_volatility = COALESCE(implied_volatility, %s),
                delta = COALESCE(delta, %s),
                gamma = COALESCE(gamma, %s),
                theta = COALESCE(theta, %s),
                vega = COALESCE(vega, %s),
                rho = COALESCE(rho, %s)
            WHERE timestamp = %s
            AND option_ticker = %s
            AND data_source = 'schwabdev_stream'
        """

        params = (
            enriched_data.get('strike_price'),
            enriched_data.get('implied_volatility'),
            enriched_data.get('delta'),
            enriched_data.get('gamma'),
            enriched_data.get('theta'),
            enriched_data.get('vega'),
            enriched_data.get('rho'),
            timestamp,
            option_ticker
        )

        if self.dry_run:
            return True

        try:
            with self.ts_store.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(update_query, params)
                    conn.commit()
            return True
        except Exception as e:
            print(f"  ✗ Error updating {option_ticker}: {e}")
            return False

    def backfill(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        batch_size: int = 100
    ):
        """
        Backfill missing data for streaming records.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Optional limit on number of records
            batch_size: Number of records to process per batch
        """
        start_time = datetime.now()

        print("\n" + "="*70)
        print("BACKFILLING STREAMING DATA WITH GREEKS")
        print("="*70)
        print(f"Started: {start_time}")
        print("="*70)

        # Find records needing enrichment
        records = self.find_records_needing_enrichment(start_date, end_date, limit)

        if not records:
            print("\n✅ No records need enrichment!")
            return

        # Get unique symbols
        symbols = self.get_unique_symbols(records)

        print(f"\n" + "="*70)
        print(f"FETCHING CONTRACT DETAILS FROM SCHWAB")
        print("="*70)

        # Populate enricher cache
        # We'll fetch the chain multiple times if needed to cover all expirations
        print("\nFetching option chain from Schwab API...")
        print("(This may take a moment for large date ranges)")

        # Use a large strike count to get as many contracts as possible
        contracts_cached = self.enricher.refresh_contract_details("$SPX", strike_count=100)

        print(f"✓ Cached {contracts_cached:,} contracts from option chain")

        # Build fallback strike mapping from symbols
        print("\nBuilding fallback strike mapping from symbols...")
        fallback_strikes = {}
        for symbol in symbols:
            strike = self.parse_strike_from_symbol(symbol)
            if strike:
                fallback_strikes[symbol] = strike

        print(f"✓ Parsed strikes for {len(fallback_strikes):,} symbols")

        # Show cache coverage
        symbols_in_cache = sum(1 for s in symbols if self.enricher.get_contract_details(s))
        print(f"\nCache coverage:")
        print(f"  In cache: {symbols_in_cache:,} / {len(symbols):,} ({symbols_in_cache/len(symbols)*100:.1f}%)")
        print(f"  Fallback (strike only): {len(fallback_strikes):,}")

        # Process records
        print(f"\n" + "="*70)
        print(f"UPDATING RECORDS")
        print("="*70)

        updated_count = 0
        skipped_count = 0
        error_count = 0

        for i, (timestamp, option_ticker) in enumerate(records, 1):
            # Get enriched data
            cached_details = self.enricher.get_contract_details(option_ticker)

            if cached_details:
                # Use full cached data
                enriched_data = {
                    'strike_price': cached_details.get('strike_price'),
                    'implied_volatility': cached_details.get('implied_volatility'),
                    'delta': cached_details.get('delta'),
                    'gamma': cached_details.get('gamma'),
                    'theta': cached_details.get('theta'),
                    'vega': cached_details.get('vega'),
                    'rho': cached_details.get('rho'),
                }
            elif option_ticker in fallback_strikes:
                # Use fallback (strike only)
                enriched_data = {
                    'strike_price': fallback_strikes[option_ticker],
                    'implied_volatility': None,
                    'delta': None,
                    'gamma': None,
                    'theta': None,
                    'vega': None,
                    'rho': None,
                }
            else:
                # No data available
                skipped_count += 1
                if i % batch_size == 0:
                    print(f"  Progress: {i:,}/{len(records):,} ({i/len(records)*100:.1f}%) | Updated: {updated_count:,} | Skipped: {skipped_count:,}")
                continue

            # Update record
            success = self.update_record(timestamp, option_ticker, enriched_data)

            if success:
                updated_count += 1
            else:
                error_count += 1

            # Progress update
            if i % batch_size == 0:
                print(f"  Progress: {i:,}/{len(records):,} ({i/len(records)*100:.1f}%) | Updated: {updated_count:,} | Skipped: {skipped_count:,} | Errors: {error_count}")

            # Rate limiting (avoid API throttling if we need to refresh cache)
            if i % 500 == 0:
                time.sleep(0.5)

        # Final progress
        print(f"  Progress: {len(records):,}/{len(records):,} (100.0%) | Updated: {updated_count:,} | Skipped: {skipped_count:,} | Errors: {error_count}")

        # Summary
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"\n" + "="*70)
        print("BACKFILL COMPLETE")
        print("="*70)

        if self.dry_run:
            print("⚠️  DRY RUN - No changes were made")
            print(f"\nWould have updated: {updated_count:,} records")
        else:
            print(f"✅ Updated: {updated_count:,} records")

        print(f"⏭️  Skipped: {skipped_count:,} records (no data available)")
        print(f"❌ Errors: {error_count}")
        print(f"⏱️  Time: {elapsed:.1f}s ({updated_count/elapsed:.1f} records/sec)")

        # Show sample of what was updated
        if updated_count > 0 and not self.dry_run:
            print(f"\nVerifying updates...")
            self._show_sample_updates()

    def _show_sample_updates(self, limit: int = 5):
        """Show sample of updated records to verify."""
        query = """
            SELECT
                timestamp,
                option_ticker,
                strike_price,
                delta,
                gamma,
                theta,
                vega,
                rho,
                implied_volatility
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND strike_price IS NOT NULL
            AND delta IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT %s
        """

        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                results = cur.fetchall()

        if results:
            print(f"\nSample of updated records (showing {len(results)}):")
            print(f"  {'Timestamp':<20} {'Symbol':<25} {'Strike':>8} {'Delta':>7} {'Gamma':>8} {'IV':>6}")
            print(f"  {'-'*20} {'-'*25} {'-'*8} {'-'*7} {'-'*8} {'-'*6}")
            for r in results:
                timestamp = r[0].strftime('%Y-%m-%d %H:%M:%S')
                symbol = r[1]
                strike = f"${r[2]:.0f}" if r[2] else "NULL"
                delta = f"{r[3]:.3f}" if r[3] else "NULL"
                gamma = f"{r[4]:.5f}" if r[4] else "NULL"
                iv = f"{r[8]:.3f}" if r[8] else "NULL"
                print(f"  {timestamp:<20} {symbol:<25} {strike:>8} {delta:>7} {gamma:>8} {iv:>6}")

    def show_statistics(self):
        """Show statistics about streaming data."""
        print("\n" + "="*70)
        print("STREAMING DATA STATISTICS")
        print("="*70)

        # Count total records
        query_total = """
            SELECT COUNT(*) FROM options_bars
            WHERE data_source = 'schwabdev_stream'
        """

        # Count records with NULL fields
        query_nulls = """
            SELECT
                COUNT(*) as total_nulls,
                COUNT(*) FILTER (WHERE strike_price IS NULL) as null_strike,
                COUNT(*) FILTER (WHERE delta IS NULL) as null_delta,
                COUNT(*) FILTER (WHERE gamma IS NULL) as null_gamma,
                COUNT(*) FILTER (WHERE theta IS NULL) as null_theta,
                COUNT(*) FILTER (WHERE vega IS NULL) as null_vega,
                COUNT(*) FILTER (WHERE rho IS NULL) as null_rho,
                COUNT(*) FILTER (WHERE implied_volatility IS NULL) as null_iv
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND (
                strike_price IS NULL
                OR delta IS NULL
                OR gamma IS NULL
                OR theta IS NULL
                OR vega IS NULL
                OR rho IS NULL
                OR implied_volatility IS NULL
            )
        """

        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_total)
                total = cur.fetchone()[0]

                cur.execute(query_nulls)
                nulls = cur.fetchone()

        print(f"\nTotal streaming records: {total:,}")

        if nulls[0] > 0:
            print(f"\nRecords with missing data: {nulls[0]:,} ({nulls[0]/total*100:.1f}%)")
            print(f"  Missing strike_price: {nulls[1]:,}")
            print(f"  Missing delta: {nulls[2]:,}")
            print(f"  Missing gamma: {nulls[3]:,}")
            print(f"  Missing theta: {nulls[4]:,}")
            print(f"  Missing vega: {nulls[5]:,}")
            print(f"  Missing rho: {nulls[6]:,}")
            print(f"  Missing implied_volatility: {nulls[7]:,}")
        else:
            print("\n✅ All records have complete data!")

    def cleanup(self):
        """Clean up resources."""
        self.ts_store.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill missing Greeks and contract details in streaming data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show statistics only
  python scripts/backfill_stream_greeks.py --stats-only

  # Backfill all missing data
  python scripts/backfill_stream_greeks.py

  # Backfill specific date range
  python scripts/backfill_stream_greeks.py --start 2025-12-10 --end 2025-12-17

  # Dry run (show what would be updated)
  python scripts/backfill_stream_greeks.py --dry-run

  # Limit number of records
  python scripts/backfill_stream_greeks.py --limit 1000
        """
    )

    parser.add_argument(
        '--start',
        type=str,
        help='Start date (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--end',
        type=str,
        help='End date (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of records to process'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Batch size for progress updates (default: 100)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making changes'
    )

    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Show statistics only, do not backfill'
    )

    args = parser.parse_args()

    # Parse dates
    start_date = None
    end_date = None

    if args.start:
        parts = args.start.split('-')
        start_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)

    if args.end:
        parts = args.end.split('-')
        end_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), 23, 59, 59, tzinfo=timezone.utc)

    # Initialize backfiller
    backfiller = StreamDataBackfiller(dry_run=args.dry_run)

    try:
        # Show statistics
        if args.stats_only:
            backfiller.show_statistics()
        else:
            # Run backfill
            backfiller.backfill(
                start_date=start_date,
                end_date=end_date,
                limit=args.limit,
                batch_size=args.batch_size
            )

            # Show final statistics
            backfiller.show_statistics()

    finally:
        backfiller.cleanup()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
