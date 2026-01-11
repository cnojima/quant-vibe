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


def run_greeks_backfill(start_date: datetime, end_date: datetime, dry_run: bool = False):
    """
    Run the backfill_stream_greeks.py script to enrich data with Greeks.

    Args:
        start_date: Start date for backfill
        end_date: End date for backfill
        dry_run: If True, run in dry-run mode (no changes)
    """
    print("\n" + "="*70)
    print("ENRICHING DATA WITH GREEKS")
    print("="*70)
    print()

    script_path = Path(__file__).parent / "backfill_stream_greeks.py"

    if not script_path.exists():
        print(f"⚠️  Greeks backfill script not found: {script_path}")
        print("   Skipping Greeks enrichment")
        return

    # Build command
    cmd = [
        sys.executable,
        str(script_path),
        "--start", start_date.strftime("%Y-%m-%d"),
        "--end", end_date.strftime("%Y-%m-%d"),
    ]

    if dry_run:
        cmd.append("--dry-run")

    print(f"Running: {' '.join(cmd)}")
    print()

    try:
        # Run the script
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,  # Show output in real-time
        )

        if result.returncode == 0:
            print("\n✅ Greeks enrichment completed successfully")
        else:
            print(f"\n⚠️  Greeks enrichment finished with code {result.returncode}")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error running Greeks backfill: {e}")
        print("   Data was inserted but Greeks may be incomplete")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("   Data was inserted but Greeks may be incomplete")


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

  # Backfill without Greeks enrichment
  python scripts/backfill/massive_spx_options.py --start 2025-07-01 --end 2025-12-12 --no-greeks
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
        default=5000.0,
        help='Minimum strike price (default: 5000.0)'
    )

    parser.add_argument(
        '--strike-max',
        type=float,
        default=7500.0,
        help='Maximum strike price (default: 7500.0)'
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

    parser.add_argument(
        '--no-greeks',
        action='store_true',
        help='Skip Greeks enrichment (faster, but incomplete data)'
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
    print(f"  Strike Range: ${args.strike_min} - ${args.strike_max}")
    print(f"  DTE Range: 0 - {args.max_dte} days")
    print(f"  Batch Size: {args.batch_size}")
    print(f"  Greeks Enrichment: {'Disabled' if args.no_greeks else 'Enabled'}")
    print()

    # ========================================================================
    # GET EXPIRATION DATES
    # ========================================================================

    print("Finding SPXW expiration dates (daily Mon-Fri, excluding holidays)...")
    expirations = get_spxw_expiration_dates(start_date, end_date)
    print(f"✅ Found {len(expirations)} expiration dates")
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

            # Get contracts for this expiration
            contracts = get_contracts_for_expiration(
                massive_client,
                expiration_date,
                args.strike_min,
                args.strike_max,
            )

            if not contracts:
                continue

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
    # ENRICH WITH GREEKS
    # ========================================================================

    if not args.no_greeks and total_bars_inserted > 0:
        run_greeks_backfill(start_date, end_date, dry_run=False)

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
