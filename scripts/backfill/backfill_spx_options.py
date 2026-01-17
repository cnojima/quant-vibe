#!/usr/bin/env python3
"""Backfill SPX/SPXW options data from Massive API.

This script:
1. Fetches historical SPX/SPXW options data from Massive API
2. Normalizes contract symbols to canonical format (SPXW... instead of O:SPXW...)
3. Validates data using OptionsBar Pydantic model
4. Stores data in TimescaleDB options_bars table
5. Automatically enriches data with Greeks using backfill_stream_greeks.py

Schema Compliance (Updated 2026-01):
- Uses OptionsBar Pydantic model from quant_vibe.models.market_data
- Field name: 'contract_symbol' (not 'option_ticker' - that's database column name)
- Database column 'option_ticker' is aliased as 'contract_symbol' in queries (see SCHEMA_MAPPING.md)
- Symbol normalization handled by Pydantic validator (removes O: prefix, strips spaces)
- contract_type: 'call' or 'put' (lowercase, validated by Pydantic)
- Timestamps: Always UTC-aware (validated by Pydantic)
- All new fields: bid_size, ask_size, implied_volatility populated as None (not in Massive data)

SPXW Details:
- SPXW = S&P 500 Weekly Index Options (daily expirations Mon-Fri)
- PM-settled (expires at 4:00 PM ET)
- European-style exercise

Usage:
    # Backfill specific date range
    python scripts/backfill/massive_spx_options.py --start 2025-07-01 --end 2025-12-12

    # Backfill with specific DTE range
    python scripts/backfill/massive_spx_options.py --start 2025-07-01 --end 2025-12-12 --max-dte 5

    # Backfill without Greeks enrichment (faster, but incomplete)
    python scripts/backfill/massive_spx_options.py --start 2025-07-01 --end 2025-12-12 --no-greeks
"""

import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
from decimal import Decimal

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from quant_vibe.data.massive_client import MassiveClient
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.models import OptionsBar
from quant_vibe.utils.timestamp_utils import to_utc
from quant_vibe.utils.symbol_utils import normalize_option_ticker
import pandas as pd
import psycopg2


def get_spx_price_for_date(ts_store: TimescaleStore, target_date: datetime) -> float:
    """
    Get SPX closing price for a specific date from underlying_bars.

    Args:
        ts_store: TimescaleStore instance
        target_date: Date to get price for

    Returns:
        SPX closing price, or None if not found
    """
    try:
        conn = ts_store.pool.getconn()
        cur = conn.cursor()

        query = """
        SELECT close
        FROM underlying_bars
        WHERE ticker = 'SPX'
          AND DATE(timestamp) = %s
        ORDER BY timestamp DESC
        LIMIT 1
        """

        cur.execute(query, (target_date.date(),))
        result = cur.fetchone()

        cur.close()
        ts_store.pool.putconn(conn)

        if result:
            return float(result[0])
        else:
            print(f"  ⚠️  No SPX price found for {target_date.date()}")
            return None

    except Exception as e:
        print(f"  ⚠️  Error getting SPX price for {target_date.date()}: {e}")
        return None


def calculate_dynamic_strike_range(
    atm_price: float,
    strike_range_pct: float = 10.0,
    strike_step: int = 25,
) -> tuple:
    """
    Calculate dynamic strike range based on ATM price.

    Args:
        atm_price: Current SPX price
        strike_range_pct: Percentage above/below ATM (default: 10%)
        strike_step: Round strikes to this increment (default: 25)

    Returns:
        (strike_min, strike_max) tuple
    """
    range_multiplier = strike_range_pct / 100.0

    # Calculate raw range
    raw_min = atm_price * (1 - range_multiplier)
    raw_max = atm_price * (1 + range_multiplier)

    # Round to nearest strike_step
    strike_min = round(raw_min / strike_step) * strike_step
    strike_max = round(raw_max / strike_step) * strike_step

    return (strike_min, strike_max)


def get_spxw_expiration_dates(start_date: datetime, end_date: datetime) -> List[datetime]:
    """
    Get SPXW expiration dates in the date range.

    SPXW now has daily expirations (Mon-Fri), excluding market holidays.

    Args:
        start_date: Start of date range
        end_date: End of date range

    Returns:
        List of expiration dates (trading days only)
    """
    expirations = []
    current = start_date

    # Common market holidays (2025)
    market_holidays = {
        datetime(2025, 1, 1).date(),   # New Year's Day
        datetime(2025, 1, 20).date(),  # MLK Day
        datetime(2025, 2, 17).date(),  # Presidents Day
        datetime(2025, 4, 18).date(),  # Good Friday
        datetime(2025, 5, 26).date(),  # Memorial Day
        datetime(2025, 6, 19).date(),  # Juneteenth
        datetime(2025, 7, 4).date(),   # Independence Day
        datetime(2025, 9, 1).date(),   # Labor Day
        datetime(2025, 11, 27).date(), # Thanksgiving
        datetime(2025, 12, 25).date(), # Christmas
    }

    while current <= end_date:
        # Include all weekdays (Mon-Fri) excluding holidays
        if current.weekday() < 5 and current.date() not in market_holidays:
            expirations.append(current)
        current += timedelta(days=1)

    return expirations


def get_contracts_for_expiration(
    massive_client: MassiveClient,
    expiration_date: datetime,
    strike_min: float,
    strike_max: float,
) -> List[Dict[str, Any]]:
    """Get SPXW contracts for a specific expiration date.

    Args:
        massive_client: Massive API client
        expiration_date: Expiration date
        strike_min: Minimum strike price
        strike_max: Maximum strike price

    Returns:
        List of contract dictionaries
    """
    expiration_str = expiration_date.strftime("%Y-%m-%d")

    print(f"\n  Fetching contracts for expiration {expiration_str}...")

    # Get all contracts (both calls and puts) for this expiration
    contracts_df = massive_client.list_options_contracts(
        underlying_ticker="SPX",  # SPXW uses SPX as underlying_ticker
        expiration_date=expiration_str,
        strike_price_gte=strike_min,
        strike_price_lte=strike_max,
        expired=True,  # Include expired contracts for historical data
        limit=1000,
    )

    if contracts_df.empty:
        print(f"  ⚠️  No contracts found")
        return []

    # Filter for SPXW only (weekly options)
    spxw_contracts = contracts_df[contracts_df['ticker'].str.contains('SPXW', na=False)]

    if spxw_contracts.empty:
        print(f"  ⚠️  No SPXW contracts found (found {len(contracts_df)} SPX contracts)")
        return []

    print(f"  ✅ Found {len(spxw_contracts)} SPXW contracts")

    return spxw_contracts.to_dict('records')


def estimate_bid_ask_spread(price: float, dte: int) -> float:
    """
    Estimate bid/ask spread based on option price and DTE.

    Rules of thumb:
    - 0 DTE: wider spreads (more volatile)
    - Lower prices: wider percentage spreads
    - Higher prices: narrower percentage spreads

    Args:
        price: Option price (close/mark)
        dte: Days to expiration

    Returns:
        Estimated half-spread (spread/2)
    """
    if price <= 0:
        return 0.0

    # Base spread percentage
    if dte == 0:
        # 0 DTE: wider spreads due to volatility
        if price < 1.0:
            spread_pct = 0.10  # 10% for very cheap options
        elif price < 5.0:
            spread_pct = 0.05  # 5% for low-priced
        elif price < 50.0:
            spread_pct = 0.02  # 2% for mid-priced
        else:
            spread_pct = 0.01  # 1% for expensive options
    elif dte == 1:
        # 1 DTE: moderate spreads
        if price < 1.0:
            spread_pct = 0.08
        elif price < 5.0:
            spread_pct = 0.04
        elif price < 50.0:
            spread_pct = 0.015
        else:
            spread_pct = 0.008
    else:
        # 2+ DTE: tighter spreads
        if price < 1.0:
            spread_pct = 0.05
        elif price < 5.0:
            spread_pct = 0.03
        elif price < 50.0:
            spread_pct = 0.01
        else:
            spread_pct = 0.005

    # Calculate half-spread (we'll add/subtract this from close)
    half_spread = price * spread_pct / 2.0

    # Minimum spread of $0.05 (typical for SPX options)
    return max(half_spread, 0.025)


def collect_bars_for_contract(
    massive_client: MassiveClient,
    option_ticker: str,
    expiration_date: datetime,
    max_dte: int = 2,
) -> List[Dict[str, Any]]:
    """
    Collect 1-minute bars for 0-max_dte days before expiration.

    Args:
        massive_client: Massive API client
        option_ticker: Option contract ticker (e.g., 'O:SPXW251224P06900000')
        expiration_date: Contract expiration date
        max_dte: Maximum days before expiration to fetch (default: 2)

    Returns:
        List of bar dictionaries
    """
    # Fetch from (max_dte days before) to (expiration day)
    from_date = expiration_date - timedelta(days=max_dte)
    to_date = expiration_date

    from_str = from_date.strftime("%Y-%m-%d")
    to_str = to_date.strftime("%Y-%m-%d")

    try:
        bars_df = massive_client.get_option_bars(
            option_ticker=option_ticker,
            multiplier=1,
            timespan="minute",
            from_date=from_str,
            to_date=to_str,
            limit=5000,
        )

        if bars_df.empty:
            return []

        # Convert to list of dicts for database insertion
        bars = []
        for timestamp, row in bars_df.iterrows():
            close_price = float(row['Close']) if pd.notna(row.get('Close')) else None

            # Calculate DTE for this bar
            bar_date = timestamp.date() if hasattr(timestamp, 'date') else timestamp
            dte = (expiration_date.date() - bar_date).days

            # Estimate bid/ask from close price
            bid = None
            ask = None
            if close_price and close_price > 0:
                half_spread = estimate_bid_ask_spread(close_price, dte)
                bid = round(close_price - half_spread, 2)
                ask = round(close_price + half_spread, 2)

                # Ensure bid is not negative
                bid = max(bid, 0.05)

            bar = {
                'timestamp': timestamp.to_pydatetime() if hasattr(timestamp, 'to_pydatetime') else timestamp,
                'option_ticker': option_ticker,  # Keep original format for now
                'open': float(row['Open']) if pd.notna(row.get('Open')) else None,
                'high': float(row['High']) if pd.notna(row.get('High')) else None,
                'low': float(row['Low']) if pd.notna(row.get('Low')) else None,
                'close': close_price,
                'volume': int(row['Volume']) if pd.notna(row.get('Volume')) else None,
                'vwap': float(row['vwap']) if pd.notna(row.get('vwap')) else None,
                'transactions': int(row['transactions']) if pd.notna(row.get('transactions')) else None,
                'bid': bid,
                'ask': ask,
            }
            bars.append(bar)

        return bars

    except Exception as e:
        print(f"    ⚠️  Error fetching bars for {option_ticker}: {e}")
        return []


def parse_spxw_ticker(ticker: str) -> Dict[str, Any]:
    """
    Parse SPXW option ticker to extract contract details.

    Handles Massive API format: O:SPXW251224P06900000
    - O: prefix for options
    - SPXW: underlying
    - 251224: expiration date (YYMMDD)
    - P/C: put or call
    - 06900000: strike price (8 digits, last 3 are decimals)

    Args:
        ticker: Option ticker in Massive format

    Returns:
        Dictionary with parsed components or None if parsing fails
    """
    try:
        # Remove 'O:' prefix
        if ticker.startswith('O:'):
            ticker = ticker[2:]

        # Extract components
        underlying = ticker[:4]  # SPXW
        exp_str = ticker[4:10]  # YYMMDD
        contract_type = ticker[10]  # C or P
        strike_str = ticker[11:]  # 8 digits

        # Parse expiration date
        exp_date = datetime.strptime('20' + exp_str, '%Y%m%d').date()

        # Parse strike price (last 3 digits are decimals)
        strike_price = float(strike_str) / 1000.0

        # Convert single letter to full word (lowercase)
        contract_type_full = 'call' if contract_type.upper() == 'C' else 'put'

        return {
            'underlying': underlying,
            'expiration_date': exp_date,
            'contract_type': contract_type_full,  # 'call' or 'put' (lowercase)
            'strike_price': strike_price,
        }
    except Exception as e:
        print(f"    ⚠️  Error parsing ticker {ticker}: {e}")
        return None

def main():
    """Backfill SPX/SPXW options data."""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Backfill SPX/SPXW options data from Massive API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backfill recent data (last 30 days)
  python scripts/backfill/massive_spx_options.py --start 2025-11-24 --end 2025-12-24

  # Backfill with specific DTE range
  python scripts/backfill/massive_spx_options.py --start 2025-07-01 --end 2025-12-12 --max-dte 5
        """
    )

    parser.add_argument(
        '--start',
        type=str,
        required=True,
        help='Start date (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--end',
        type=str,
        required=True,
        help='End date (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--strike-min',
        type=float,
        default=None,
        help='Minimum strike price (overrides --strike-mode if set)'
    )

    parser.add_argument(
        '--strike-max',
        type=float,
        default=None,
        help='Maximum strike price (overrides --strike-mode if set)'
    )

    parser.add_argument(
        '--strike-mode',
        type=str,
        choices=['fixed', 'dynamic'],
        default='dynamic',
        help='Strike selection mode: "fixed" uses --strike-min/max, "dynamic" uses ATM ± N%% (default: dynamic)'
    )

    parser.add_argument(
        '--strike-range-pct',
        type=float,
        default=5.0,
        help='For dynamic mode: percentage above/below ATM (default: 5.0)'
    )

    parser.add_argument(
        '--strike-step',
        type=int,
        default=5,
        help='Only include strikes divisible by this value (default: 50)'
    )

    parser.add_argument(
        '--sample-days',
        type=int,
        default=1,
        help='Process every N days (1 = all days, 7 = weekly, 30 = monthly). Default: 1'
    )

    parser.add_argument(
        '--sample-weekday',
        type=str,
        choices=['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
        default=None,
        help='Only process specific weekday (overrides --sample-days if set)'
    )

    parser.add_argument(
        '--max-dte',
        type=int,
        default=2,
        help='Maximum days to expiration (default: 2, for 0-2 DTE data)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Batch size for database inserts (default: 1000)'
    )

    args = parser.parse_args()

    # Parse dates
    start_date = datetime.strptime(args.start, '%Y-%m-%d')
    end_date = datetime.strptime(args.end, '%Y-%m-%d')

    print("="*70)
    print("BACKFILL SPX/SPXW OPTIONS DATA")
    print("="*70)
    print()

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    print(f"Configuration:")
    print(f"  Date Range: {start_date.date()} to {end_date.date()}")

    # Determine strike mode
    if args.strike_min is not None and args.strike_max is not None:
        strike_mode = 'fixed (explicit)'
        print(f"  Strike Mode: {strike_mode}")
        print(f"  Strike Range: ${args.strike_min} - ${args.strike_max}")
    elif args.strike_mode == 'dynamic':
        print(f"  Strike Mode: dynamic (ATM ± {args.strike_range_pct}%)")
        print(f"  Strike Step: {args.strike_step} points")
    else:
        print(f"  Strike Mode: {args.strike_mode}")
        print(f"  Strike Range: ${args.strike_min} - ${args.strike_max}")

    print(f"  DTE Range: 0 - {args.max_dte} days")

    # Sampling info
    if args.sample_weekday:
        print(f"  Sampling: Every {args.sample_weekday.capitalize()}")
    elif args.sample_days > 1:
        print(f"  Sampling: Every {args.sample_days} days")
    else:
        print(f"  Sampling: All days")

    print(f"  Batch Size: {args.batch_size}")
    print(f"  Greeks Enrichment: {'Disabled' if args.no_greeks else 'Enabled'}")
    print()

    # ========================================================================
    # GET EXPIRATION DATES
    # ========================================================================

    print("Finding SPXW expiration dates (daily Mon-Fri, excluding holidays)...")
    all_expirations = get_spxw_expiration_dates(start_date, end_date)
    print(f"✅ Found {len(all_expirations)} expiration dates")

    # Apply sampling filter
    if args.sample_weekday:
        weekday_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2,
            'thursday': 3, 'friday': 4
        }
        target_weekday = weekday_map[args.sample_weekday]
        expirations = [exp for exp in all_expirations if exp.weekday() == target_weekday]
        print(f"   Filtered to {len(expirations)} {args.sample_weekday.capitalize()}s")
    elif args.sample_days > 1:
        expirations = all_expirations[::args.sample_days]
        print(f"   Sampled every {args.sample_days} days: {len(expirations)} dates")
    else:
        expirations = all_expirations
        print(f"   Processing all {len(expirations)} dates")

    if expirations:
        print(f"   First: {expirations[0].date()} ({expirations[0].strftime('%A')})")
        print(f"   Last: {expirations[-1].date()} ({expirations[-1].strftime('%A')})")
    print()

    # ========================================================================
    # INITIALIZE CLIENTS
    # ========================================================================

    print("Connecting to APIs...")
    massive_client = MassiveClient()
    ts_store = TimescaleStore()
    print("✅ Connected!")
    print()

    # ========================================================================
    # BACKFILL DATA
    # ========================================================================

    total_expirations = len(expirations)
    total_contracts_processed = 0
    total_bars_inserted = 0

    try:
        for exp_idx, expiration_date in enumerate(expirations, 1):
            print(f"[{exp_idx}/{total_expirations}] Processing {expiration_date.date()} ({expiration_date.strftime('%A')})...")

            # Determine strike range for this expiration
            if args.strike_min is not None and args.strike_max is not None:
                # Use explicit fixed range
                strike_min = args.strike_min
                strike_max = args.strike_max
                print(f"  Using fixed strike range: ${strike_min} - ${strike_max}")
            elif args.strike_mode == 'dynamic':
                # Get SPX price for this expiration date
                spx_price = get_spx_price_for_date(ts_store, expiration_date)
                if spx_price is None:
                    print(f"  ⚠️  Skipping {expiration_date.date()} - no SPX price available")
                    continue

                # Calculate dynamic strike range
                strike_min, strike_max = calculate_dynamic_strike_range(
                    spx_price,
                    args.strike_range_pct,
                    args.strike_step,
                )
                print(f"  SPX @ ${spx_price:.2f} → Strikes ${strike_min:.0f} - ${strike_max:.0f}")
            else:
                # Default to wide range if nothing specified
                strike_min = 5000.0
                strike_max = 7500.0
                print(f"  Using default strike range: ${strike_min} - ${strike_max}")

            # Get contracts for this expiration
            contracts = get_contracts_for_expiration(
                massive_client,
                expiration_date,
                strike_min,
                strike_max,
            )

            if not contracts:
                continue

            # Filter contracts by strike step (only strikes divisible by strike_step)
            if args.strike_step > 1:
                original_count = len(contracts)
                contracts = [
                    c for c in contracts
                    if c['strike_price'] % args.strike_step == 0
                ]
                if len(contracts) < original_count:
                    print(f"  Filtered to {len(contracts)}/{original_count} contracts (strike step: {args.strike_step})")

            # Collect bars for each contract
            all_bars = []

            for contract_idx, contract in enumerate(contracts, 1):
                ticker = contract['ticker']  # Massive format: O:SPXW...

                if (contract_idx % 50) == 0 or contract_idx == len(contracts):
                    print(f"    Processing contract {contract_idx}/{len(contracts)}: {ticker}")

                # Parse contract details
                contract_details = parse_spxw_ticker(ticker)
                if not contract_details:
                    continue

                # Fetch bars for this contract
                bars = collect_bars_for_contract(
                    massive_client,
                    ticker,  # Massive format
                    expiration_date,
                    max_dte=args.max_dte,
                )

                if not bars:
                    continue

                # Convert dicts to Pydantic models
                for bar_dict in bars:
                    try:
                        # Normalize contract symbol (remove O: prefix)
                        # The OptionsBar model has a validator that will normalize it automatically
                        normalized_symbol = normalize_option_ticker(bar_dict['option_ticker'])

                        # Calculate mark from bid/ask if available
                        bid = bar_dict.get('bid')
                        ask = bar_dict.get('ask')
                        mark = None
                        if bid is not None and ask is not None:
                            mark = (bid + ask) / 2.0

                        # Create OptionsBar Pydantic model with ALL required fields
                        # Note: OptionsBar uses 'contract_symbol' (not 'option_ticker')
                        options_bar = OptionsBar(
                            timestamp=to_utc(bar_dict['timestamp']),
                            contract_symbol=normalized_symbol,  # This will be validated/normalized by Pydantic
                            underlying_ticker='SPX',
                            strike_price=Decimal(str(contract_details['strike_price'])),
                            contract_type=contract_details['contract_type'],  # Already lowercase 'call'/'put'
                            expiration_date=contract_details['expiration_date'],
                            # OHLCV data
                            open=Decimal(str(bar_dict['open'])) if bar_dict.get('open') is not None else Decimal('0'),
                            high=Decimal(str(bar_dict['high'])) if bar_dict.get('high') is not None else Decimal('0'),
                            low=Decimal(str(bar_dict['low'])) if bar_dict.get('low') is not None else Decimal('0'),
                            close=Decimal(str(bar_dict['close'])) if bar_dict.get('close') is not None else Decimal('0'),
                            volume=bar_dict.get('volume', 0),
                            # Quote data
                            bid=Decimal(str(bid)) if bid is not None else None,
                            ask=Decimal(str(ask)) if ask is not None else None,
                            mark=Decimal(str(mark)) if mark is not None else None,
                            bid_size=None,  # Not available from Massive API
                            ask_size=None,  # Not available from Massive API
                            # Additional metrics
                            vwap=Decimal(str(bar_dict['vwap'])) if bar_dict.get('vwap') is not None else None,
                            transactions=bar_dict.get('transactions'),
                            # Greeks (will be filled by backfill_stream_greeks.py)
                            delta=None,
                            gamma=None,
                            theta=None,
                            vega=None,
                            rho=None,
                            implied_volatility=None,
                            # Metadata
                            data_source='massive',
                        )
                        all_bars.append(options_bar)
                    except Exception as e:
                        print(f"    ⚠️  Error creating OptionsBar model: {e}, skipping bar")
                        continue

                # Insert in batches to avoid memory issues
                if len(all_bars) >= args.batch_size:
                    inserted = ts_store.bulk_insert_option_bars(all_bars, batch_size=args.batch_size)
                    total_bars_inserted += inserted
                    print(f"    ✅ Inserted {inserted} bars (total so far: {total_bars_inserted:,})")
                    all_bars = []

            # Insert remaining bars for this expiration
            if all_bars:
                inserted = ts_store.bulk_insert_option_bars(all_bars, batch_size=args.batch_size)
                total_bars_inserted += inserted
                print(f"  ✅ Inserted {inserted} bars for {expiration_date.date()}")

            total_contracts_processed += len(contracts)
            print(f"  Completed {expiration_date.date()} - Total bars: {total_bars_inserted:,}")
            print()

    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        ts_store.close()

    # ========================================================================
    # SUMMARY
    # ========================================================================

    print()
    print("="*70)
    print("BACKFILL COMPLETE")
    print("="*70)
    print(f"Expirations Processed: {total_expirations}")
    print(f"Contracts Processed: {total_contracts_processed}")
    print(f"Total Bars Inserted: {total_bars_inserted:,}")
    if args.no_greeks:
        print()
        print("⚠️  Greeks enrichment was skipped (--no-greeks)")
        print("   Run backfill_stream_greeks.py manually to add Greeks")
    print("="*70)


if __name__ == "__main__":
    main()
