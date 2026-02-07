#!/usr/bin/env python3
"""Analyze missing Greeks and contract details for streaming data.

*** IMPORTANT: DATABASE UPDATES ARE DISABLED ***
This script is in READ-ONLY mode for analysis purposes only.
No database modifications will be performed.

This script:
1. Finds options_bars records from schwabdev_stream with NULL Greeks
2. Analyzes contract details that would be fetched from API
3. Reports on what updates would be needed (but does NOT apply them)

ANALYSIS MODES:
- --active-only: Analyze only non-expired contracts
- --strikes-only: Analyze strike prices that could be parsed from symbols
- --mark-expired: Analyze expired contracts that should be marked

Note: When professional data service is available in the future,
transactional updates can be re-enabled.

Usage:
    # Backfill all missing data
    python scripts/backfill/backfill_stream_greeks.py

    # RECOMMENDED: Only backfill active (non-expired) contracts with full Greeks
    python scripts/backfill/backfill_stream_greeks.py --active-only

    # Fast: Bulk update strike prices only (no API calls)
    python scripts/backfill/backfill_stream_greeks.py --strikes-only

    # Mark expired contracts so they're excluded from future queries
    python scripts/backfill/backfill_stream_greeks.py --mark-expired

    # Backfill specific date range
    python scripts/backfill/backfill_stream_greeks.py --start 2025-12-10 --end 2025-12-17

    # Dry run (show what would be updated)
    python scripts/backfill/backfill_stream_greeks.py --dry-run

    # Limit number of records
    python scripts/backfill/backfill_stream_greeks.py --limit 1000
"""

import sys
import os
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone, date
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
            timeout=30,
        )

        self.enricher = OptionContractEnricher(self.schwab_client)
        self.ts_store = TimescaleStore()

        print("✓ Schwab client initialized")
        print("✓ Contract enricher initialized")
        print("✓ TimescaleDB connected")

        print("\n" + "="*70)
        print("⚠️  READ-ONLY MODE - DATABASE UPDATES ARE DISABLED")
        print("This script will analyze data but NOT perform any updates")
        print("="*70)

        if self.dry_run:
            print("\n⚠️  DRY RUN MODE - Analysis only (updates already disabled)")

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
                bid IS NULL
                OR ask IS NULL
                OR strike_price IS NULL
                OR delta IS NULL
                OR gamma IS NULL
                OR theta IS NULL
                OR vega IS NULL
                OR rho IS NULL
                OR implied_volatility IS NULL
            ) AND expired IS NOT TRUE
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

    def find_active_contracts_needing_enrichment(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Tuple]:
        """
        Find records with missing column values for NON-EXPIRED contracts only.

        This is much more efficient because:
        1. We only query contracts that can actually be enriched via API
        2. Expired contracts cannot get Greeks from Schwab API

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Optional limit on number of records

        Returns:
            List of (timestamp, option_ticker) tuples for active contracts
        """
        print("\n" + "="*70)
        print("FINDING ACTIVE CONTRACTS NEEDING ENRICHMENT")
        print("="*70)

        today = date.today()
        print(f"Today: {today}")
        print("Filtering to contracts expiring today or later...")

        # First, get distinct option_tickers that need enrichment
        query = """
            SELECT DISTINCT option_ticker
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND (
                bid IS NULL
                OR ask IS NULL
                OR strike_price IS NULL
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

        print("\nQuerying for distinct contracts...")

        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params if params else None)
                all_tickers = [r[0] for r in cur.fetchall()]

        print(f"✓ Found {len(all_tickers):,} unique contracts with missing Greeks")

        # Filter to active (non-expired) contracts
        active_tickers = []
        expired_count = 0
        for ticker in all_tickers:
            exp_date = self.parse_expiration_from_symbol(ticker)
            if exp_date and exp_date >= today:
                active_tickers.append(ticker)
            else:
                expired_count += 1

        print(f"  Active (non-expired): {len(active_tickers):,}")
        print(f"  Expired (skipped): {expired_count:,}")

        if not active_tickers:
            print("\n⚠️  No active contracts need enrichment")
            return []

        # Now get actual records for active tickers only
        ticker_placeholders = ','.join(['%s'] * len(active_tickers))
        records_query = f"""
            SELECT DISTINCT timestamp, option_ticker
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND option_ticker IN ({ticker_placeholders})
            AND (
                bid IS NULL
                OR ask IS NULL
                OR strike_price IS NULL
                OR delta IS NULL
                OR gamma IS NULL
                OR theta IS NULL
                OR vega IS NULL
                OR rho IS NULL
                OR implied_volatility IS NULL
            )
            ORDER BY timestamp DESC
        """

        record_params = list(active_tickers)

        if limit:
            records_query = records_query.replace(
                "ORDER BY timestamp DESC",
                f"ORDER BY timestamp DESC LIMIT {limit}"
            )
            print(f"Limit: {limit}")

        print("\nQuerying for records of active contracts...")

        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(records_query, record_params)
                results = cur.fetchall()

        print(f"✓ Found {len(results):,} records for active contracts")

        return results

    def bulk_update_strikes_only(
        self,
        limit: Optional[int] = None
    ) -> int:
        """
        Analyze strike prices that could be bulk updated.

        *** UPDATES DISABLED - READ-ONLY MODE ***
        This method now only analyzes what could be updated.

        Returns:
            Number of records that would be updated
        """
        print("\n" + "="*70)
        print("ANALYZING STRIKE PRICES (READ-ONLY)")
        print("="*70)

        print("\n⚠️  READ-ONLY MODE - No database changes will be made")

        # Count records needing strike price
        count_query = """
            SELECT COUNT(*)
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND strike_price IS NULL
        """

        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_query)
                total_null = cur.fetchone()[0]

        print(f"\nRecords with NULL strike_price: {total_null:,}")

        if total_null == 0:
            print("✅ All records already have strike prices!")
            return 0

        # SQL to extract strike from symbol
        # Symbol format: "SPXW  251219C06100000" -> last 8 chars / 1000
        # REPLACE removes spaces, RIGHT gets last 8, CAST converts to numeric
        update_query = """
            UPDATE options_bars
            SET strike_price = CAST(RIGHT(REPLACE(option_ticker, ' ', ''), 8) AS NUMERIC) / 1000.0
            WHERE data_source = 'schwabdev_stream'
            AND strike_price IS NULL
        """

        if limit:
            # For limited updates, we need a subquery
            update_query = f"""
                UPDATE options_bars
                SET strike_price = CAST(RIGHT(REPLACE(option_ticker, ' ', ''), 8) AS NUMERIC) / 1000.0
                WHERE ctid IN (
                    SELECT ctid FROM options_bars
                    WHERE data_source = 'schwabdev_stream'
                    AND strike_price IS NULL
                    LIMIT {limit}
                )
            """
            print(f"Limit: {limit}")

        # Always run in analysis mode (no actual updates)
        print(f"\nWould update up to {limit or total_null:,} records (READ-ONLY MODE)")

        # Database updates are disabled - commented out for future re-enablement
        # if self.dry_run:
        #     print(f"\nWould update up to {limit or total_null:,} records")
        #     return min(limit, total_null) if limit else total_null
        #
        # print("\nExecuting bulk UPDATE...")
        # print("(Setting TimescaleDB decompression limit for large updates)")
        # start_time = datetime.now()
        #
        # with self.ts_store.get_connection() as conn:
        #     with conn.cursor() as cur:
        #         # Increase decompression limit for this transaction
        #         cur.execute("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0;")
        #         cur.execute(update_query)
        #         updated = cur.rowcount
        #         conn.commit()
        #
        # elapsed = (datetime.now() - start_time).total_seconds()
        # print(f"✅ Updated {updated:,} records in {elapsed:.1f}s ({updated/elapsed:.0f} records/sec)")

        return min(limit, total_null) if limit else total_null

    def mark_expired_contracts(
        self,
        sentinel_value: float = -9.0  # Deprecated parameter, kept for backwards compatibility
    ) -> int:
        """
        Analyze expired contracts that could be marked.

        *** UPDATES DISABLED - READ-ONLY MODE ***
        This method now only analyzes what contracts would be marked.

        Returns:
            Number of records that would be marked
        """
        print("\n" + "="*70)
        print("ANALYZING EXPIRED CONTRACTS (READ-ONLY)")
        print("="*70)

        print("\n⚠️  READ-ONLY MODE - No database changes will be made")

        today = date.today()
        print(f"Today: {today}")
        print(f"Using 'expired' column (boolean flag)")

        # First, find expired contracts with NULL Greeks
        query = """
            SELECT DISTINCT option_ticker
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND delta IS NULL
        """

        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                all_tickers = [r[0] for r in cur.fetchall()]

        print(f"\nContracts with NULL delta: {len(all_tickers):,}")

        # Filter to expired contracts
        expired_tickers = []
        for ticker in all_tickers:
            exp_date = self.parse_expiration_from_symbol(ticker)
            if exp_date and exp_date < today:
                expired_tickers.append(ticker)

        print(f"Expired contracts: {len(expired_tickers):,}")

        if not expired_tickers:
            print("✅ No expired contracts to analyze!")
            return 0

        # Always analyze mode (no actual updates)
        print(f"\nWould mark records for {len(expired_tickers):,} expired contracts (READ-ONLY MODE)")

        # Count affected records for analysis
        ticker_placeholders = ','.join(['%s'] * len(expired_tickers))
        count_query = f"""
            SELECT COUNT(*)
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND option_ticker IN ({ticker_placeholders})
            AND delta IS NULL
        """
        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_query, expired_tickers)
                count = cur.fetchone()[0]
        print(f"Would mark {count:,} records as expired")

        # Database updates are disabled - commented out for future re-enablement
        # # Update in batches to avoid memory issues
        # # Use smaller batches for TimescaleDB compressed hypertables
        # batch_size = 50  # Smaller batch to avoid decompression limits
        # total_updated = 0
        # start_time = datetime.now()
        #
        # print(f"\nMarking expired contracts in batches of {batch_size}...")
        # print("(Setting TimescaleDB decompression limit for large updates)")
        #
        # for i in range(0, len(expired_tickers), batch_size):
        #     batch = expired_tickers[i:i + batch_size]
        #     ticker_placeholders = ','.join(['%s'] * len(batch))
        #
        #     update_query = f"""
        #         UPDATE options_bars
        #         SET expired = true
        #         WHERE data_source = 'schwabdev_stream'
        #         AND option_ticker IN ({ticker_placeholders})
        #         AND COALESCE(expired, false) = false
        #     """
        #
        #     params = batch
        #
        #     with self.ts_store.get_connection() as conn:
        #         with conn.cursor() as cur:
        #             # Increase decompression limit for this transaction
        #             cur.execute("SET timescaledb.max_tuples_decompressed_per_dml_transaction = 0;")
        #             cur.execute(update_query, params)
        #             total_updated += cur.rowcount
        #             conn.commit()
        #
        #     progress = min(i + batch_size, len(expired_tickers))
        #     print(f"  Progress: {progress:,}/{len(expired_tickers):,} contracts | {total_updated:,} records updated")
        #
        # elapsed = (datetime.now() - start_time).total_seconds()
        # print(f"\n✅ Marked {total_updated:,} records in {elapsed:.1f}s")

        return count

    def parse_expiration_from_symbol(self, symbol: str) -> Optional[date]:
        """
        Parse expiration date from option symbol.

        Format: "SPXW  251219C06100000"
                      ^^^^^^ Expiration YYMMDD
                            ^ Type (C/P)
                             ^^^^^^^^ Strike × 1000

        Args:
            symbol: Option symbol

        Returns:
            Expiration date or None
        """
        try:
            # Remove spaces and find the 6-digit date before C/P
            clean = symbol.replace(" ", "")
            # Match pattern: root + YYMMDD + C/P + strike
            match = re.search(r'(\d{6})[CP]\d{8}$', clean)
            if match:
                date_str = match.group(1)
                year = 2000 + int(date_str[0:2])
                month = int(date_str[2:4])
                day = int(date_str[4:6])
                return date(year, month, day)
            return None
        except (ValueError, IndexError):
            return None

    def parse_strike_from_symbol(self, symbol: str) -> Optional[float]:
        """
        Parse strike price from option symbol as fallback.

        Format: "SPXW  251219C06100000"
                      ^^^^^^ Expiration YYMMDD
                            ^ Type (C/P)
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
        Simulate updating a single record with enriched data.

        *** UPDATES DISABLED - READ-ONLY MODE ***
        This method now only simulates updates for analysis.

        Args:
            timestamp: Record timestamp
            option_ticker: Option symbol
            enriched_data: Dict with contract details

        Returns:
            True (simulated success)
        """
        # Database updates are disabled - only simulate
        # Original update code commented out for future re-enablement

        # update_query = """
        #     UPDATE options_bars
        #     SET
        #         bid = COALESCE(bid, %s),
        #         ask = COALESCE(ask, %s),
        #         strike_price = COALESCE(strike_price, %s),
        #         implied_volatility = COALESCE(implied_volatility, %s),
        #         delta = COALESCE(delta, %s),
        #         gamma = COALESCE(gamma, %s),
        #         theta = COALESCE(theta, %s),
        #         vega = COALESCE(vega, %s),
        #         rho = COALESCE(rho, %s)
        #     WHERE timestamp = %s
        #     AND option_ticker = %s
        #     AND data_source = 'schwabdev_stream'
        # """
        #
        # params = (
        #     enriched_data.get('bid'),
        #     enriched_data.get('ask'),
        #     enriched_data.get('strike_price'),
        #     enriched_data.get('implied_volatility'),
        #     enriched_data.get('delta'),
        #     enriched_data.get('gamma'),
        #     enriched_data.get('theta'),
        #     enriched_data.get('vega'),
        #     enriched_data.get('rho'),
        #     timestamp,
        #     option_ticker
        # )
        #
        # if self.dry_run:
        #     return True
        #
        # try:
        #     with self.ts_store.get_connection() as conn:
        #         with conn.cursor() as cur:
        #             cur.execute(update_query, params)
        #             conn.commit()
        #     return True
        # except Exception as e:
        #     print(f"  ✗ Error updating {option_ticker}: {e}")
        #     return False

        # Always return True in read-only mode (simulated success)
        return True

    def backfill(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
        batch_size: int = 100,
        active_only: bool = False
    ):
        """
        Backfill missing data for streaming records.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Optional limit on number of records
            batch_size: Number of records to process per batch
            active_only: If True, only process non-expired contracts (much faster)
        """
        start_time = datetime.now()

        print("\n" + "="*70)
        print("ANALYZING STREAMING DATA FOR MISSING GREEKS (READ-ONLY)")
        print("="*70)
        print(f"Started: {start_time}")
        print(f"Date range: {start_date} to {end_date}")
        if active_only:
            print("Mode: ACTIVE CONTRACTS ONLY (non-expired)")
        else:
            print("Mode: ALL CONTRACTS (may include expired)")
        print("⚠️  DATABASE UPDATES DISABLED - Analysis only")
        print("="*70)

        # Find records needing enrichment
        print("\nSearching for records needing enrichment...")
        if active_only:
            records = self.find_active_contracts_needing_enrichment(start_date, end_date, limit)
        else:
            records = self.find_records_needing_enrichment(start_date, end_date, limit)

        if not records:
            print("\n✅ No records need enrichment!")
            print("Script will now exit.")
            return

        print(f"\nWill process {len(records)} records")

        # Get unique symbols
        symbols = self.get_unique_symbols(records)

        print(f"\n" + "="*70)
        print(f"FETCHING CONTRACT DETAILS FROM SCHWAB")
        print("="*70)

        # Populate enricher cache
        # We'll fetch the chain multiple times if needed to cover all expirations
        print("\nFetching option chain from Schwab API...")
        print("(This may take a moment for large date ranges)")

        # Use a moderate strike count to avoid API buffer overflow
        # Schwab API returns 502 with "Body buffer overflow" if too many strikes requested
        MAX_STRIKES = 30  # Reduced from 100 to avoid API gateway buffer overflow

        print(f"  Requesting up to {MAX_STRIKES} strikes to avoid API overflow...")
        contracts_cached = self.enricher.refresh_contract_details("$SPX", strike_count=MAX_STRIKES)

        print(f"✓ Cached {contracts_cached:,} contracts from option chain")

        # If we got 0 contracts, try with even fewer strikes
        if contracts_cached == 0:
            print("\n⚠️  No contracts cached. Retrying with fewer strikes...")
            for strike_count in [20, 10, 5]:
                print(f"  Retrying with {strike_count} strikes...")
                contracts_cached = self.enricher.refresh_contract_details("$SPX", strike_count=strike_count)
                if contracts_cached > 0:
                    print(f"✓ Successfully cached {contracts_cached:,} contracts with {strike_count} strikes")
                    break
            else:
                print("❌ Failed to cache any contracts from API. Will use fallback strike parsing only.")

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
                    'bid': cached_details.get('bid'),
                    'ask': cached_details.get('ask'),
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
                    'bid': None,
                    'ask': None,
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
        print("ANALYSIS COMPLETE (READ-ONLY)")
        print("="*70)

        print("⚠️  READ-ONLY MODE - No database changes were made")
        print(f"\nWould have updated: {updated_count:,} records")
        print(f"⏭️  Skipped: {skipped_count:,} records (no data available)")
        print(f"❌ Errors: {error_count}")
        print(f"⏱️  Time: {elapsed:.1f}s ({updated_count/elapsed:.1f} records/sec)")

        # Skip verification since no actual updates were made
        print("\nNote: Verification skipped (no actual updates performed)")

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
                COUNT(*) FILTER (WHERE bid IS NULL) as null_bid,
                COUNT(*) FILTER (WHERE ask IS NULL) as null_ask,
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
                bid IS NULL
                OR ask IS NULL
                OR strike_price IS NULL
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
            print(f"  Missing bid: {nulls[1]:,}")
            print(f"  Missing ask: {nulls[2]:,}")
            print(f"  Missing strike_price: {nulls[3]:,}")
            print(f"  Missing delta: {nulls[4]:,}")
            print(f"  Missing gamma: {nulls[5]:,}")
            print(f"  Missing theta: {nulls[6]:,}")
            print(f"  Missing vega: {nulls[7]:,}")
            print(f"  Missing rho: {nulls[8]:,}")
            print(f"  Missing implied_volatility: {nulls[9]:,}")

            # Show expired vs active breakdown for records needing Greeks
            self._show_expiration_breakdown()
        else:
            print("\n✅ All records have complete data!")

    def _show_expiration_breakdown(self):
        """Show breakdown of expired vs active contracts needing enrichment."""
        print("\n" + "-"*50)
        print("CONTRACT EXPIRATION BREAKDOWN")
        print("-"*50)

        # Get distinct contracts with missing Greeks
        query = """
            SELECT DISTINCT option_ticker
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND delta IS NULL
        """

        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                tickers = [r[0] for r in cur.fetchall()]

        today = date.today()
        active_count = 0
        expired_count = 0
        unknown_count = 0

        for ticker in tickers:
            exp_date = self.parse_expiration_from_symbol(ticker)
            if exp_date is None:
                unknown_count += 1
            elif exp_date >= today:
                active_count += 1
            else:
                expired_count += 1

        total_contracts = len(tickers)
        print(f"\nContracts needing Greeks: {total_contracts:,}")
        print(f"  Active (can enrich via API):  {active_count:,} ({active_count/total_contracts*100:.1f}%)")
        print(f"  Expired (cannot get Greeks):  {expired_count:,} ({expired_count/total_contracts*100:.1f}%)")
        if unknown_count > 0:
            print(f"  Unknown expiration:           {unknown_count:,}")

        # Count marked vs unmarked expired
        query_marked = """
            SELECT COUNT(DISTINCT option_ticker)
            FROM options_bars
            WHERE data_source = 'schwabdev_stream'
            AND expired = true
        """
        with self.ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_marked)
                marked_count = cur.fetchone()[0]

        if marked_count > 0:
            print(f"\n  Already marked as unenrichable: {marked_count:,}")

        print("\n💡 RECOMMENDATIONS:")
        if active_count > 0:
            print(f"   • Run with --active-only to enrich {active_count:,} active contracts")
        if expired_count > 0:
            print(f"   • Run with --mark-expired to exclude {expired_count:,} expired contracts from future queries")
        print("   • Run with --strikes-only to quickly fill strike prices (no API needed)")

    def cleanup(self):
        """Clean up resources."""
        self.ts_store.close()


def main():
    """Main entry point."""
    print("\n" + "="*70)
    print("STREAM GREEKS ANALYSIS SCRIPT (READ-ONLY)")
    print("*** DATABASE UPDATES ARE DISABLED ***")
    print(f"Time: {datetime.now()}")
    print(f"PID: {os.getpid()}")
    print("="*70)

    parser = argparse.ArgumentParser(
        description="Analyze missing Greeks and contract details in streaming data (READ-ONLY MODE - No database updates)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show statistics and recommendations
  python scripts/backfill/backfill_stream_greeks.py --stats-only

  # RECOMMENDED: Backfill only active (non-expired) contracts
  python scripts/backfill/backfill_stream_greeks.py --active-only

  # Fast: Bulk update strike prices only (no API calls)
  python scripts/backfill/backfill_stream_greeks.py --strikes-only

  # Mark expired contracts so they're excluded from future queries
  python scripts/backfill/backfill_stream_greeks.py --mark-expired

  # Backfill all contracts (may be slow for large datasets)
  python scripts/backfill/backfill_stream_greeks.py

  # Backfill specific date range
  python scripts/backfill/backfill_stream_greeks.py --start 2025-12-10 --end 2025-12-17

  # Dry run (show what would be updated)
  python scripts/backfill/backfill_stream_greeks.py --dry-run

  # Limit number of records
  python scripts/backfill/backfill_stream_greeks.py --limit 1000

Recommended workflow for large datasets:
  1. Run --stats-only to see breakdown of active vs expired contracts
  2. Run --strikes-only to quickly fill all strike prices
  3. Run --active-only to get full Greeks for non-expired contracts
  4. Run --mark-expired to exclude expired contracts from future queries
        """
    )

    parser.add_argument(
        '--start',
        type=str,
        help='Start date/time. Formats: YYYY-MM-DD, "YYYY-MM-DD HH:MM:SS", YYYY-MM-DDTHH:MM:SS+00'
    )

    parser.add_argument(
        '--end',
        type=str,
        help='End date/time. Formats: YYYY-MM-DD, "YYYY-MM-DD HH:MM:SS", YYYY-MM-DDTHH:MM:SS+00'
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

    parser.add_argument(
        '--active-only',
        action='store_true',
        help='Only process non-expired contracts (much faster, can get full Greeks)'
    )

    parser.add_argument(
        '--strikes-only',
        action='store_true',
        help='Only update strike prices using SQL (fastest, no API calls)'
    )

    parser.add_argument(
        '--mark-expired',
        action='store_true',
        help='Mark expired contracts with sentinel values to exclude from future queries'
    )

    args = parser.parse_args()

    # Validate mutually exclusive options
    mode_count = sum([args.stats_only, args.strikes_only, args.mark_expired, args.active_only])
    if mode_count > 1 and not (args.active_only and not args.stats_only and not args.strikes_only and not args.mark_expired):
        # Allow active_only with regular backfill, but not with other modes
        exclusive_modes = [m for m in ['--stats-only', '--strikes-only', '--mark-expired'] 
                          if getattr(args, m.replace('--', '').replace('-', '_'))]
        if len(exclusive_modes) > 1:
            parser.error(f"Cannot use multiple modes together: {', '.join(exclusive_modes)}")

    # Parse dates - support both YYYY-MM-DD and full datetime strings
    start_date = None
    end_date = None

    if args.start:
        try:
            # Try parsing as full datetime first
            if 'T' in args.start or ' ' in args.start or ':' in args.start:
                # Replace T with space for parsing
                datetime_str = args.start.replace('T', ' ')
                # Handle timezone
                if '+' in datetime_str or 'Z' in datetime_str:
                    # Parse with timezone
                    from dateutil import parser
                    start_date = parser.parse(datetime_str)
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=timezone.utc)
                else:
                    # Parse without timezone, assume UTC
                    if ' ' in datetime_str:
                        date_part, time_part = datetime_str.split(' ')
                        date_parts = date_part.split('-')
                        time_parts = time_part.split(':')
                        start_date = datetime(
                            int(date_parts[0]), int(date_parts[1]), int(date_parts[2]),
                            int(time_parts[0]), int(time_parts[1]),
                            int(float(time_parts[2])) if len(time_parts) > 2 else 0,
                            tzinfo=timezone.utc
                        )
                    else:
                        # Just date
                        parts = datetime_str.split('-')
                        start_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)
            else:
                # Simple date format YYYY-MM-DD
                parts = args.start.split('-')
                start_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc)
        except Exception as e:
            parser.error(f"Invalid start date format: {args.start}. Use YYYY-MM-DD or 'YYYY-MM-DD HH:MM:SS'")

    if args.end:
        try:
            # Try parsing as full datetime first
            if 'T' in args.end or ' ' in args.end or ':' in args.end:
                # Replace T with space for parsing
                datetime_str = args.end.replace('T', ' ')
                # Handle timezone
                if '+' in datetime_str or 'Z' in datetime_str:
                    # Parse with timezone
                    from dateutil import parser
                    end_date = parser.parse(datetime_str)
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=timezone.utc)
                else:
                    # Parse without timezone, assume UTC
                    if ' ' in datetime_str:
                        date_part, time_part = datetime_str.split(' ')
                        date_parts = date_part.split('-')
                        time_parts = time_part.split(':')
                        end_date = datetime(
                            int(date_parts[0]), int(date_parts[1]), int(date_parts[2]),
                            int(time_parts[0]), int(time_parts[1]),
                            int(float(time_parts[2])) if len(time_parts) > 2 else 0,
                            tzinfo=timezone.utc
                        )
                    else:
                        # Just date
                        parts = datetime_str.split('-')
                        end_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), 23, 59, 59, tzinfo=timezone.utc)
            else:
                # Simple date format YYYY-MM-DD - use end of day
                parts = args.end.split('-')
                end_date = datetime(int(parts[0]), int(parts[1]), int(parts[2]), 23, 59, 59, tzinfo=timezone.utc)
        except Exception as e:
            parser.error(f"Invalid end date format: {args.end}. Use YYYY-MM-DD or 'YYYY-MM-DD HH:MM:SS'")

    # Initialize backfiller
    backfiller = StreamDataBackfiller(dry_run=args.dry_run)

    try:
        if args.stats_only:
            # Show statistics only
            backfiller.show_statistics()

        elif args.strikes_only:
            # Fast bulk update of strike prices
            backfiller.bulk_update_strikes_only(limit=args.limit)
            backfiller.show_statistics()

        elif args.mark_expired:
            # Mark expired contracts
            backfiller.mark_expired_contracts()
            backfiller.show_statistics()

        else:
            # Run backfill (with optional active_only filter)
            backfiller.backfill(
                start_date=start_date,
                end_date=end_date,
                limit=args.limit,
                batch_size=args.batch_size,
                active_only=args.active_only
            )

            # Show final statistics
            backfiller.show_statistics()

    finally:
        backfiller.cleanup()
        print("\n" + "="*70)
        print("STREAM GREEKS ANALYSIS COMPLETED (READ-ONLY)")
        print("*** NO DATABASE CHANGES WERE MADE ***")
        print(f"Time: {datetime.now()}")
        print(f"PID: {os.getpid()}")
        print("="*70)
        print("\nExiting normally...")
        sys.exit(0)  # Explicit exit


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except SystemExit as e:
        # Normal exit, re-raise it
        raise
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
