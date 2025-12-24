"""Backfill missing December 2025 data gaps from Massive API.

This script backfills specific December days that were missed during
real-time collection:
- Dec 16 (Tuesday): Missing market hours data
- Dec 18 (Thursday): Data collection started late

Fetches 0-2 DTE SPXW options data with estimated bid/ask spreads.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from quant_vibe.data.massive_client import MassiveClient
from quant_vibe.data.timescale_store import TimescaleStore

# Load environment variables
load_dotenv()


def estimate_bid_ask_spread(price: float, dte: int) -> float:
    """
    Estimate bid/ask spread based on option price and DTE.

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

    # Calculate half-spread
    half_spread = price * spread_pct / 2.0

    # Minimum spread of $0.05 (typical for SPX options)
    return max(half_spread, 0.025)


def parse_spxw_ticker(ticker: str) -> Dict[str, Any]:
    """
    Parse SPXW option ticker to extract contract details.

    Example: O:SPXW251218C06700000
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

        # Convert single letter to full word
        contract_type_full = 'call' if contract_type.upper() == 'C' else 'put'

        return {
            'underlying': underlying,
            'expiration_date': exp_date,
            'contract_type': contract_type_full,
            'strike_price': strike_price,
        }
    except Exception as e:
        print(f"    ⚠️  Error parsing ticker {ticker}: {e}")
        return None


def collect_bars_for_contract(
    massive_client: MassiveClient,
    option_ticker: str,
    expiration_date: datetime,
    from_date: str,
    to_date: str,
) -> List[Dict[str, Any]]:
    """
    Collect 1-minute bars for a specific date range.

    Args:
        massive_client: Massive API client
        option_ticker: Option contract ticker
        expiration_date: Contract expiration date
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
    """
    try:
        bars_df = massive_client.get_option_bars(
            option_ticker=option_ticker,
            multiplier=1,
            timespan="minute",
            from_date=from_date,
            to_date=to_date,
            limit=5000,
        )

        if bars_df.empty:
            return []

        # Convert to list of dicts
        bars = []
        for timestamp, row in bars_df.iterrows():
            close_price = float(row['Close']) if row.get('Close') is not None else None

            # Calculate DTE
            bar_date = timestamp.date() if hasattr(timestamp, 'date') else timestamp
            dte = (expiration_date.date() - bar_date).days

            # Estimate bid/ask from close
            bid = None
            ask = None
            if close_price and close_price > 0:
                half_spread = estimate_bid_ask_spread(close_price, dte)
                bid = round(close_price - half_spread, 2)
                ask = round(close_price + half_spread, 2)
                bid = max(bid, 0.05)

            bar = {
                'timestamp': timestamp.to_pydatetime() if hasattr(timestamp, 'to_pydatetime') else timestamp,
                'option_ticker': option_ticker,
                'open': float(row['Open']) if row.get('Open') is not None else None,
                'high': float(row['High']) if row.get('High') is not None else None,
                'low': float(row['Low']) if row.get('Low') is not None else None,
                'close': close_price,
                'volume': int(row['Volume']) if row.get('Volume') is not None else None,
                'vwap': float(row['vwap']) if row.get('vwap') is not None else None,
                'transactions': int(row['transactions']) if row.get('transactions') is not None else None,
                'bid': bid,
                'ask': ask,
            }
            bars.append(bar)

        return bars

    except Exception as e:
        print(f"    ⚠️  Error fetching bars for {option_ticker}: {e}")
        return []


def main():
    """Backfill December 2025 data gaps."""

    print("="*70)
    print("BACKFILL DECEMBER 2025 DATA GAPS")
    print("="*70)
    print()

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    # Days to backfill (market was open but data collection failed/incomplete)
    backfill_dates = [
        datetime(2025, 12, 16),  # Tuesday - missing market hours
        datetime(2025, 12, 17),  # Wednesday - missing 0 DTE contracts
        datetime(2025, 12, 18),  # Thursday - started late
        datetime(2025, 12, 19),  # Friday - missing some 0 DTE contracts
        datetime(2025, 12, 23),  # Monday - missing some 0 DTE contracts
    ]

    # Strike range (based on Dec SPX levels ~6700-6900)
    strike_min = 6500.0
    strike_max = 7000.0

    # DTE range (0-2 DTE for intraday trading)
    max_dte = 2

    # Batch size
    batch_size = 1000

    print(f"Configuration:")
    print(f"  Days to backfill: {[d.strftime('%Y-%m-%d (%A)') for d in backfill_dates]}")
    print(f"  Strike Range: ${strike_min} - ${strike_max}")
    print(f"  DTE Range: 0 - {max_dte} days")
    print(f"  Batch Size: {batch_size}")
    print()

    # ========================================================================
    # INITIALIZE CLIENTS
    # ========================================================================

    print("Connecting to APIs...")
    massive_client = MassiveClient()

    # Connect to remote or local database based on env var
    use_remote = os.getenv("USE_REMOTE_TIMESCALE", "false").lower() == "true"
    db_location = "remote" if use_remote else "local"

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

    print(f"✅ Connected to {db_location} TimescaleDB!")
    print()

    # ========================================================================
    # BACKFILL DATA
    # ========================================================================

    total_bars_inserted = 0
    total_contracts_processed = 0

    try:
        for date_idx, backfill_date in enumerate(backfill_dates, 1):
            print(f"[{date_idx}/{len(backfill_dates)}] Processing {backfill_date.strftime('%Y-%m-%d (%A)')}")
            print("-"*70)

            # Get expirations to collect (0, 1, 2 DTE from this day)
            expirations_to_collect = []
            for dte_offset in range(max_dte + 1):
                exp_date = backfill_date + timedelta(days=dte_offset)
                # Skip weekends
                if exp_date.weekday() < 5:
                    expirations_to_collect.append(exp_date)

            print(f"  Collecting data for expirations: {[e.strftime('%Y-%m-%d') for e in expirations_to_collect]}")
            print()

            all_bars = []

            for exp_date in expirations_to_collect:
                exp_str = exp_date.strftime("%Y-%m-%d")
                print(f"  📅 Expiration: {exp_str}")

                # Get contracts for this expiration
                try:
                    contracts_df = massive_client.list_options_contracts(
                        underlying_ticker="SPX",
                        expiration_date=exp_str,
                        strike_price_gte=strike_min,
                        strike_price_lte=strike_max,
                        expired=True,
                        limit=1000,
                    )

                    if contracts_df.empty:
                        print(f"     ⚠️  No contracts found")
                        continue

                    # Filter for SPXW only
                    spxw_contracts = contracts_df[contracts_df['ticker'].str.contains('SPXW', na=False)]

                    if spxw_contracts.empty:
                        print(f"     ⚠️  No SPXW contracts")
                        continue

                    print(f"     ✅ Found {len(spxw_contracts)} SPXW contracts")

                    # Collect bars for each contract (only for the backfill_date)
                    from_date_str = backfill_date.strftime("%Y-%m-%d")
                    to_date_str = backfill_date.strftime("%Y-%m-%d")

                    for contract_idx, (_, contract) in enumerate(spxw_contracts.iterrows(), 1):
                        ticker = contract['ticker']

                        if (contract_idx % 25) == 0 or contract_idx == len(spxw_contracts):
                            print(f"     Processing {contract_idx}/{len(spxw_contracts)}: {ticker}")

                        # Parse contract details
                        contract_details = parse_spxw_ticker(ticker)
                        if not contract_details:
                            continue

                        # Fetch bars
                        bars = collect_bars_for_contract(
                            massive_client,
                            ticker,
                            exp_date,
                            from_date_str,
                            to_date_str,
                        )

                        if not bars:
                            continue

                        # Enrich with contract details
                        for bar in bars:
                            bar['underlying_ticker'] = 'SPX'
                            bar['strike_price'] = contract_details['strike_price']
                            bar['contract_type'] = contract_details['contract_type']
                            bar['expiration_date'] = contract_details['expiration_date']
                            bar['data_source'] = 'massive'

                        all_bars.extend(bars)
                        total_contracts_processed += 1

                        # Insert in batches
                        if len(all_bars) >= batch_size:
                            inserted = ts_store.bulk_insert_option_bars(all_bars, batch_size=batch_size)
                            total_bars_inserted += inserted
                            print(f"     ✅ Inserted {inserted} bars (total: {total_bars_inserted:,})")
                            all_bars = []

                except Exception as e:
                    print(f"     ❌ Error: {e}")
                    continue

                print()

            # Insert remaining bars
            if all_bars:
                inserted = ts_store.bulk_insert_option_bars(all_bars, batch_size=batch_size)
                total_bars_inserted += inserted
                print(f"  ✅ Inserted {inserted} bars for {backfill_date.strftime('%Y-%m-%d')}")

            print(f"  Completed {backfill_date.strftime('%Y-%m-%d')} - Total bars: {total_bars_inserted:,}")
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
    print(f"Days Processed: {len(backfill_dates)}")
    print(f"Contracts Processed: {total_contracts_processed}")
    print(f"Total Bars Inserted: {total_bars_inserted:,}")
    print("="*70)


if __name__ == "__main__":
    main()
