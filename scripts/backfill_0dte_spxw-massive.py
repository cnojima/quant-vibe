"""Backfill 0-2 DTE SPXW options data from Massive API.

This script fills in the missing 0-2 DTE data for SPXW (PM-settled) contracts.
SPXW expires at 4:00 PM ET, so we can get full trading day data on expiration day.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pandas as pd

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.massive_client import MassiveClient
from quant_vibe.data.timescale_store import TimescaleStore


def get_spxw_expiration_dates(start_date: datetime, end_date: datetime) -> List[datetime]:
    """
    Get SPXW expiration dates in the date range.

    SPXW now has daily expirations (Mon-Fri), excluding market holidays.

    Note: This includes all weekdays. You may want to exclude specific
    market holidays (New Year's, July 4th, Thanksgiving, Christmas, etc.)
    but for backtesting purposes, the API will simply return no data
    for those days.
    """
    expirations = []
    current = start_date

    # Common market holidays (basic set - may not be exhaustive)
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
    """Get SPXW contracts for a specific expiration date."""

    expiration_str = expiration_date.strftime("%Y-%m-%d")

    print(f"\n  Fetching contracts for expiration {expiration_str}...")

    # Get all contracts (both calls and puts) for this expiration
    contracts_df = massive_client.list_options_contracts(
        underlying_ticker="SPX",
        expiration_date=expiration_str,
        strike_price_gte=strike_min,
        strike_price_lte=strike_max,
        expired=True,  # Include expired contracts for historical data
        limit=1000,
    )

    if contracts_df.empty:
        print(f"  ⚠️  No contracts found")
        return []

    # Filter for SPXW only
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
        option_ticker: Option contract ticker (e.g., 'O:SPXW250718C05500000')
        expiration_date: Contract expiration date
        max_dte: Maximum days before expiration to fetch (default: 2)
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
                'option_ticker': option_ticker,
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

    Example: O:SPXW250718C05500000
    - O: prefix for options
    - SPXW: underlying
    - 250718: expiration date (YYMMDD)
    - C/P: call or put
    - 05500000: strike price (8 digits, last 3 are decimals)
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

        return {
            'underlying': underlying,
            'expiration_date': exp_date,
            'contract_type': contract_type.lower(),  # 'call' or 'put'
            'strike_price': strike_price,
        }
    except Exception as e:
        print(f"    ⚠️  Error parsing ticker {ticker}: {e}")
        return None


def main():
    """Backfill 0-2 DTE SPXW data."""

    print("="*70)
    print("BACKFILL 0-2 DTE SPXW OPTIONS DATA")
    print("="*70)
    print()

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    # Date range to backfill
    start_date = datetime(2025, 7, 1)
    end_date = datetime(2025, 12, 12)

    # Strike range (filter to reasonable strikes around SPX price)
    # SPX range in this period: ~5500-6900
    strike_min = 5000.0
    strike_max = 7500.0

    # DTE range to backfill
    max_dte = 2  # Fetch 0, 1, 2 DTE data

    # Batch size for database inserts
    batch_size = 1000

    print(f"Configuration:")
    print(f"  Date Range: {start_date.date()} to {end_date.date()}")
    print(f"  Strike Range: ${strike_min} - ${strike_max}")
    print(f"  DTE Range: 0 - {max_dte} days")
    print(f"  Batch Size: {batch_size}")
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
                strike_min,
                strike_max,
            )

            if not contracts:
                continue

            # Collect bars for each contract
            all_bars = []

            for contract_idx, contract in enumerate(contracts, 1):
                ticker = contract['ticker']

                if (contract_idx % 50) == 0 or contract_idx == len(contracts):
                    print(f"    Processing contract {contract_idx}/{len(contracts)}: {ticker}")

                # Parse contract details
                contract_details = parse_spxw_ticker(ticker)
                if not contract_details:
                    continue

                # Fetch bars for this contract
                bars = collect_bars_for_contract(
                    massive_client,
                    ticker,
                    expiration_date,
                    max_dte=max_dte,
                )

                if not bars:
                    continue

                # Enrich bars with contract details
                for bar in bars:
                    bar['underlying_ticker'] = 'SPX'  # Store as SPX for consistency
                    bar['strike_price'] = contract_details['strike_price']
                    bar['contract_type'] = contract_details['contract_type']
                    bar['expiration_date'] = contract_details['expiration_date']
                    bar['data_source'] = 'massive'

                all_bars.extend(bars)

                # Insert in batches to avoid memory issues
                if len(all_bars) >= batch_size:
                    inserted = ts_store.bulk_insert_option_bars(all_bars, batch_size=batch_size)
                    total_bars_inserted += inserted
                    print(f"    ✅ Inserted {inserted} bars (total so far: {total_bars_inserted:,})")
                    all_bars = []

            # Insert remaining bars for this expiration
            if all_bars:
                inserted = ts_store.bulk_insert_option_bars(all_bars, batch_size=batch_size)
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

    print("="*70)
    print("BACKFILL COMPLETE")
    print("="*70)
    print(f"Expirations Processed: {total_expirations}")
    print(f"Contracts Processed: {total_contracts_processed}")
    print(f"Total Bars Inserted: {total_bars_inserted:,}")
    print("="*70)


if __name__ == "__main__":
    main()
