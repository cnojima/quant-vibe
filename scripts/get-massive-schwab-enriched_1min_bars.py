"""
Collect 1-minute options bars from Massive and enrich with Schwab quote data.

This script:
1. Fetches 1-minute OHLCV bars from Massive API
2. Optionally enriches with real-time quotes from Schwab (bid/ask/Greeks)
3. Stores data in TimescaleDB for efficient querying

Usage:
    # Collect SPX options data for today
    python scripts/collect_options_1min_data.py --ticker SPX

    # Collect historical data
    python scripts/collect_options_1min_data.py --ticker SPX --from 2025-12-01 --to 2025-12-12

    # Collect with Schwab quotes (requires Schwab API access)
    python scripts/collect_options_1min_data.py --ticker SPX --enrich-schwab
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import time
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data import MassiveClient, TimescaleStore


def convert_numpy_types(obj: Any) -> Any:
    """
    Convert numpy types to Python native types.

    Args:
        obj: Value to convert (can be numpy type, None, or native Python type)

    Returns:
        Native Python type
    """
    if obj is None:
        return None
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    else:
        return obj


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Collect 1-minute options data")

    parser.add_argument(
        "--ticker",
        type=str,
        required=True,
        help="Underlying ticker symbol (e.g., SPX, AAPL)"
    )

    parser.add_argument(
        "--from",
        dest="from_date",
        type=str,
        default=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        help="Start date (YYYY-MM-DD), default: yesterday"
    )

    parser.add_argument(
        "--to",
        dest="to_date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD), default: today"
    )

    parser.add_argument(
        "--expiration",
        type=str,
        help="Specific expiration date to collect (YYYY-MM-DD), default: all upcoming"
    )

    parser.add_argument(
        "--strike-min",
        type=float,
        help="Minimum strike price filter"
    )

    parser.add_argument(
        "--strike-max",
        type=float,
        help="Maximum strike price filter"
    )

    parser.add_argument(
        "--contract-type",
        choices=["call", "put"],
        help="Filter by contract type (call or put)"
    )

    parser.add_argument(
        "--enrich-schwab",
        action="store_true",
        help="Enrich data with Schwab quotes (requires Schwab API)"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for database inserts (default: 1000)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser.parse_args()


def get_options_contracts(
    massive_client: MassiveClient,
    underlying_ticker: str,
    expiration_date: Optional[str] = None,
    strike_min: Optional[float] = None,
    strike_max: Optional[float] = None,
    contract_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get list of options contracts to collect data for.

    Args:
        massive_client: Massive API client
        underlying_ticker: Underlying ticker (e.g., "SPX" or "SPXW")
        expiration_date: Specific expiration (optional)
        strike_min: Min strike filter
        strike_max: Max strike filter
        contract_type: Contract type filter

    Returns:
        List of contract dictionaries

    Note:
        SPXW (weekly) contracts have underlying_ticker="SPX" in Massive API,
        but the ticker itself is "O:SPXW...". This function handles filtering
        for SPXW specifically.
    """
    print(f"Fetching options contracts for {underlying_ticker}...")

    # Handle SPXW -> SPX conversion for API query
    # SPXW contracts have underlying="SPX" but ticker contains "SPXW"
    ticker_filter = None
    api_underlying = underlying_ticker

    if underlying_ticker == "SPXW":
        print("  Note: SPXW uses underlying_ticker='SPX', filtering for weekly contracts")
        api_underlying = "SPX"
        ticker_filter = "SPXW"  # Filter for O:SPXW... tickers
    elif underlying_ticker == "SPX":
        # User wants monthly SPX only, filter out SPXW
        ticker_filter = "SPX"  # Filter for O:SPX... tickers (not SPXW)

    if expiration_date:
        # Get specific expiration
        contracts_df = massive_client.list_options_contracts(
            underlying_ticker=api_underlying,
            expiration_date=expiration_date,
            strike_price_gte=strike_min,
            strike_price_lte=strike_max,
            contract_type=contract_type,
        )
    else:
        # Get all upcoming expirations (next 60 days)
        today = datetime.now().strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")

        contracts_df = massive_client.list_options_contracts(
            underlying_ticker=api_underlying,
            expiration_date_gte=today,
            expiration_date_lte=future,
            strike_price_gte=strike_min,
            strike_price_lte=strike_max,
            contract_type=contract_type,
        )

    # Filter by ticker pattern if needed
    if ticker_filter and not contracts_df.empty:
        before_count = len(contracts_df)
        if ticker_filter == "SPXW":
            # Keep only SPXW contracts
            contracts_df = contracts_df[contracts_df['ticker'].str.contains(':SPXW', na=False)]
        elif ticker_filter == "SPX":
            # Keep only SPX (not SPXW) contracts
            contracts_df = contracts_df[~contracts_df['ticker'].str.contains(':SPXW', na=False)]

        after_count = len(contracts_df)
        print(f"  Filtered {before_count} -> {after_count} contracts (pattern: {ticker_filter})")

    contracts = contracts_df.to_dict("records")
    print(f"Found {len(contracts)} contracts")

    return contracts


def collect_option_bars(
    massive_client: MassiveClient,
    option_ticker: str,
    from_date: str,
    to_date: str,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """
    Collect 1-minute bars for a specific option contract.

    Args:
        massive_client: Massive API client
        option_ticker: Option contract ticker
        from_date: Start date
        to_date: End date
        verbose: Enable verbose output

    Returns:
        List of bar dictionaries
    """
    if verbose:
        print(f"  Collecting bars for {option_ticker}...")

    try:
        bars_df = massive_client.get_option_bars(
            option_ticker=option_ticker,
            from_date=from_date,
            to_date=to_date,
            multiplier=1,
            timespan="minute",
        )

        if bars_df.empty:
            if verbose:
                print(f"    No data found")
            return []

        # Convert DataFrame to list of dicts
        bars = []
        for timestamp, row in bars_df.iterrows():
            bars.append({
                "timestamp": timestamp,
                "open": row.get("Open"),
                "high": row.get("High"),
                "low": row.get("Low"),
                "close": row.get("Close"),
                "volume": row.get("Volume"),
                "vwap": row.get("vwap"),
                "transactions": row.get("transactions"),
            })

        if verbose:
            print(f"    Found {len(bars)} bars")

        return bars

    except Exception as e:
        print(f"    Error: {e}")
        return []


def parse_massive_option_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Parse Massive option ticker format to extract components.

    Massive format: O:SPXW251226P02000000
    Components:
    - O: = Options prefix
    - SPXW = Underlying symbol
    - 251226 = Expiration date (YYMMDD)
    - P = Put (C = Call)
    - 02000000 = Strike price * 1000

    Args:
        ticker: Massive option ticker

    Returns:
        Dict with parsed components or None if invalid
    """
    try:
        # Remove 'O:' prefix
        if not ticker.startswith('O:'):
            return None
        ticker = ticker[2:]

        # Find where the date starts (6 digits YYMMDD)
        # Work backwards from the end
        # Format: SYMBOL + YYMMDD + C/P + STRIKE (8 digits)
        if len(ticker) < 15:  # Minimum: 1 char symbol + 6 date + 1 type + 8 strike
            return None

        # Last 8 digits are strike price
        strike_str = ticker[-8:]
        strike_price = float(strike_str) / 1000.0

        # Next character is option type (C/P)
        option_type = ticker[-9]
        if option_type not in ['C', 'P']:
            return None

        # Next 6 characters are expiration date YYMMDD
        exp_date_str = ticker[-15:-9]
        if not exp_date_str.isdigit() or len(exp_date_str) != 6:
            return None

        # Parse expiration date
        year = 2000 + int(exp_date_str[0:2])
        month = int(exp_date_str[2:4])
        day = int(exp_date_str[4:6])
        expiration_date = f"{year:04d}-{month:02d}-{day:02d}"

        # Remaining is the underlying symbol
        underlying = ticker[:-15]

        return {
            'underlying': underlying,
            'expiration_date': expiration_date,
            'option_type': 'call' if option_type == 'C' else 'put',
            'strike_price': strike_price,
        }
    except Exception:
        return None


def convert_to_schwab_ticker(massive_ticker: str) -> Optional[str]:
    """
    Convert Massive option ticker format to Schwab format.

    Massive: O:SPXW251226P02000000
    Schwab:  SPXW  251226P02000 (note: spaces for padding)

    Args:
        massive_ticker: Massive format ticker

    Returns:
        Schwab format ticker or None if conversion fails
    """
    parsed = parse_massive_option_ticker(massive_ticker)
    if not parsed:
        return None

    # Extract components
    underlying = parsed['underlying']
    exp_date = parsed['expiration_date']
    option_type = parsed['option_type']
    strike = parsed['strike_price']

    # Convert expiration date from YYYY-MM-DD to YYMMDD
    year = exp_date[2:4]  # Last 2 digits of year
    month = exp_date[5:7]
    day = exp_date[8:10]
    exp_str = f"{year}{month}{day}"

    # Convert strike to 8-digit format (strike * 1000, padded to 8 digits)
    # Example: 2000.0 -> 02000000, 4500.5 -> 04500500
    strike_str = f"{int(strike * 1000):08d}"

    # Option type: C or P
    type_char = 'C' if option_type == 'call' else 'P'

    # OCC/Schwab format: SYMBOL (padded to 6 chars) + YYMMDD + C/P + STRIKE (8 digits)
    # E.g., "SPXW  251226P02000000"
    symbol_padded = underlying.ljust(6)

    return f"{symbol_padded}{exp_str}{type_char}{strike_str}"


def enrich_with_schwab(
    schwab_client: Optional[Any],
    option_ticker: str,
    bars: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Enrich bars with Schwab quote data (bid/ask/Greeks).

    Fetches current quote from Schwab and applies to all bars.
    Note: This uses the most recent quote for all time periods,
    which is suitable for recent data but not historical enrichment.

    Args:
        schwab_client: Schwab API client
        option_ticker: Massive format option ticker (e.g., 'O:SPXW251226P02000000')
        bars: List of bars to enrich

    Returns:
        Enriched bars with bid/ask/Greeks if available
    """
    if not schwab_client or not bars:
        return bars

    try:
        # Convert Massive ticker to Schwab format
        schwab_ticker = convert_to_schwab_ticker(option_ticker)
        if not schwab_ticker:
            print(f"    ⚠ Could not convert ticker: {option_ticker}")
            return bars

        # Get quote from Schwab
        quote_response = schwab_client.get_quote(schwab_ticker)

        # Extract quote data
        # Schwab response format: {ticker: {quote: {...}, reference: {...}}}
        if not quote_response or schwab_ticker not in quote_response:
            print(f"    ⚠ No quote data for {schwab_ticker}")
            return bars

        quote_data = quote_response[schwab_ticker].get('quote', {})

        # Extract relevant fields
        bid = quote_data.get('bidPrice')
        ask = quote_data.get('askPrice')
        bid_size = quote_data.get('bidSize')
        ask_size = quote_data.get('askSize')

        # Greeks (may not always be available)
        delta = quote_data.get('delta')
        gamma = quote_data.get('gamma')
        theta = quote_data.get('theta')
        vega = quote_data.get('vega')
        rho = quote_data.get('rho')
        implied_vol = quote_data.get('volatility')

        # Enrich all bars with this quote data
        for bar in bars:
            bar['bid'] = bid
            bar['ask'] = ask
            bar['bid_size'] = bid_size
            bar['ask_size'] = ask_size
            bar['delta'] = delta
            bar['gamma'] = gamma
            bar['theta'] = theta
            bar['vega'] = vega
            bar['rho'] = rho
            bar['implied_volatility'] = implied_vol

        print(f"    ✓ Enriched with Schwab quote data (bid: {bid}, ask: {ask})")

    except Exception as e:
        print(f"    ⚠ Schwab enrichment error: {e}")
        # Return bars unchanged on error

    return bars


def main():
    """Main execution function."""
    args = parse_args()

    print("=" * 80)
    print("Options Data Collection (1-minute bars)")
    print("=" * 80)
    print(f"Ticker: {args.ticker}")
    print(f"Date Range: {args.from_date} to {args.to_date}")
    if args.expiration:
        print(f"Expiration: {args.expiration}")
    if args.strike_min or args.strike_max:
        print(f"Strike Range: {args.strike_min or 'any'} to {args.strike_max or 'any'}")
    if args.contract_type:
        print(f"Contract Type: {args.contract_type}")
    print("=" * 80)
    print()

    # Initialize clients
    print("Initializing clients...")
    massive_client = MassiveClient(verbose=args.verbose)
    timescale_store = TimescaleStore()

    schwab_client = None
    if args.enrich_schwab:
        try:
            from quant_vibe.data.schwab_py_client import SchwabPyClient
            schwab_client = SchwabPyClient()
            print("  ✓ Schwab client initialized")
        except ImportError:
            print("  ⚠ Schwab client not available (install with: pip install -e '.[schwab]')")
            print("  Continuing without Schwab enrichment...")
        except Exception as e:
            print(f"  ⚠ Schwab client failed: {e}")
            print("  Continuing without Schwab enrichment...")

    print("  ✓ Massive client initialized")
    print("  ✓ TimescaleDB connection established")
    print()

    # Get contracts
    contracts = get_options_contracts(
        massive_client,
        args.ticker,
        args.expiration,
        args.strike_min,
        args.strike_max,
        args.contract_type,
    )

    if not contracts:
        print("No contracts found. Exiting.")
        return

    print()

    # Collect data for each contract
    total_bars = 0
    for i, contract in enumerate(contracts, 1):
        print(f"[{i}/{len(contracts)}] {contract['ticker']}")
        print(f"  Strike: {contract['strike_price']} | Type: {contract['contract_type']} | Exp: {contract['expiration_date']}")

        # Collect bars
        bars = collect_option_bars(
            massive_client,
            contract["ticker"],
            args.from_date,
            args.to_date,
            args.verbose,
        )

        if not bars:
            continue

        # Enrich with Schwab if enabled
        if schwab_client:
            bars = enrich_with_schwab(schwab_client, contract["ticker"], bars)

        # Prepare for database insertion
        db_bars = []
        for bar in bars:
            # Convert all values from numpy types to Python native types
            db_bar = {
                "timestamp": bar["timestamp"],
                "option_ticker": str(contract["ticker"]),
                "underlying_ticker": str(contract["underlying_ticker"]),
                # OHLCV from Massive
                "open": convert_numpy_types(bar.get("open")),
                "high": convert_numpy_types(bar.get("high")),
                "low": convert_numpy_types(bar.get("low")),
                "close": convert_numpy_types(bar.get("close")),
                "volume": convert_numpy_types(bar.get("volume")),
                "vwap": convert_numpy_types(bar.get("vwap")),
                "transactions": convert_numpy_types(bar.get("transactions")),
                # Contract details
                "strike_price": convert_numpy_types(contract["strike_price"]),
                "contract_type": str(contract["contract_type"]),
                "expiration_date": datetime.strptime(contract["expiration_date"], "%Y-%m-%d"),
                # Quote data from Schwab (if enriched)
                "bid": convert_numpy_types(bar.get("bid")),
                "ask": convert_numpy_types(bar.get("ask")),
                "bid_size": convert_numpy_types(bar.get("bid_size")),
                "ask_size": convert_numpy_types(bar.get("ask_size")),
                # Greeks from Schwab (if enriched)
                "implied_volatility": convert_numpy_types(bar.get("implied_volatility")),
                "delta": convert_numpy_types(bar.get("delta")),
                "gamma": convert_numpy_types(bar.get("gamma")),
                "theta": convert_numpy_types(bar.get("theta")),
                "vega": convert_numpy_types(bar.get("vega")),
                "rho": convert_numpy_types(bar.get("rho")),
                # Data source
                "data_source": "schwab" if schwab_client else "massive",
            }
            db_bars.append(db_bar)

        # Bulk insert
        try:
            inserted = timescale_store.bulk_insert_option_bars(db_bars, batch_size=args.batch_size)
            print(f"  ✓ Inserted {inserted} bars")
            total_bars += inserted
        except Exception as e:
            print(f"  ✗ Database error: {e}")

        # Rate limiting
        time.sleep(0.1)

    print()
    print("=" * 80)
    print(f"Collection Complete: {total_bars} total bars inserted")
    print("=" * 80)

    # Show database stats
    print()
    print("Database Statistics:")
    stats = timescale_store.get_database_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    timescale_store.close()


if __name__ == "__main__":
    main()
