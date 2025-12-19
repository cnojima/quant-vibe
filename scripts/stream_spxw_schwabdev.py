"""Stream SPXW options data using schwabdev and store in TimescaleDB.

This script:
1. Connects to Schwab streaming using schwabdev library
2. Subscribes to SPXW options contracts (0-45 DTE, ±10% ATM)
3. Aggregates streaming quotes into 1-minute bars
4. Stores in TimescaleDB for backtesting


Schwabdev LEVELONE_OPTIONS field mapping:
0: "Symbol"
1: "Description"
2: "Bid Price"
3: "Ask Price"
4: "Last Price"
5: "High Price"
6: "Low Price"
7: "Close Price"
8: "Total Volume"
9: "Open Interest"
10: "Volatility" (Implied Volatility)
11: "Money Intrinsic Value"
12: "Expiration Year"
13: "Multiplier"
14: "Digits"
15: "Open Price"
16: "Bid Size"
17: "Ask Size"
18: "Last Size"
19: "Net Change"
20: "Strike Price"
21: "Contract Type"
22: "Underlying"
23: "Expiration Month"
24: "Deliverables"
25: "Time Value"
26: "Expiration Day"
27: "Days to Expiration"
28: "Delta"
29: "Gamma"
30: "Theta"
31: "Vega"
32: "Rho"
33: "Security Status"
34: "Theoretical Option Value"
35: "Underlying Price"
36: "UV Expiration Type"
37: "Mark Price"
38: "Quote Time in Long"
39: "Trade Time in Long"

Note: VWAP is NOT directly available in Schwab streaming data.
It is calculated during bar aggregation using: VWAP = Σ(Price × Volume) / Σ(Volume)
where incremental volume is computed from cumulative volume updates.


Usage:
    python scripts/stream_spxw_schwabdev.py

    # With specific DTE range
    python scripts/stream_spxw_schwabdev.py --max-dte 7

    # With wider strike range
    python scripts/stream_spxw_schwabdev.py --strike-range-pct 0.20
"""

import os
import sys
from pathlib import Path
import time as dt_time
import json
import re
from datetime import datetime, timedelta, time
from collections import defaultdict
from typing import Dict, List, Optional
import argparse
import zoneinfo

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import schwabdev
from dotenv import load_dotenv

from quant_vibe.data.timescale_store import TimescaleStore

# Import enricher for option chain details
sys.path.insert(0, str(Path(__file__).parent))
from enrich_stream_with_chain import OptionContractEnricher

load_dotenv()


def parse_expiration_from_ticker(ticker: str) -> Optional[datetime]:
    """
    Parse expiration date from SPXW option ticker.

    SPXW option tickers have the format: SPXW  YYMMDDX########
    Where:
    - YYMM DD = expiration date (year, month, day)
    - X = P (put) or C (call)
    - ######## = strike price

    Example: SPXW  260121P06200000 = Jan 21, 2026 Put at 6200 strike

    Args:
        ticker: Option ticker in format "SPXW  YYMMDDX########"

    Returns:
        Expiration date as datetime.date or None if parse fails
    """
    # Remove extra spaces
    ticker = ticker.strip()

    # Pattern: SPXW followed by 6 digits (YYMMDD), then P or C
    # Example: "SPXW  260121P06200000" or "SPXW260121P06200000"
    pattern = r'SPXW\s*(\d{6})[PC]'
    match = re.search(pattern, ticker)

    if not match:
        return None

    date_str = match.group(1)  # YYMMDD

    try:
        # Parse YYMMDD
        yy = int(date_str[0:2])
        mm = int(date_str[2:4])
        dd = int(date_str[4:6])

        # Convert YY to YYYY (assume 2000+ for 00-99)
        yyyy = 2000 + yy

        # Validate and create date
        exp_date = datetime(yyyy, mm, dd).date()
        return exp_date

    except (ValueError, IndexError):
        return None


class SPXWOptionsStreamer:
    """Stream and aggregate SPXW options data."""

    def __init__(
        self,
        max_dte: int = 45,
        min_dte: int = 0,
        strike_range_pct: float = 0.10,
        aggregate_interval_seconds: int = 60
    ):
        """
        Initialize SPXW options streamer.

        Args:
            max_dte: Maximum days to expiration
            min_dte: Minimum days to expiration
            strike_range_pct: Strike range as % of underlying (e.g., 0.10 = ±10%)
            aggregate_interval_seconds: Seconds to aggregate data (60 = 1min bars)
        """
        self.max_dte = max_dte
        self.min_dte = min_dte
        self.strike_range_pct = strike_range_pct
        self.aggregate_interval = aggregate_interval_seconds

        # Data storage
        self.quote_buffer: Dict[str, List[Dict]] = defaultdict(list)
        self.last_flush_time = datetime.now()
        self.last_token_refresh = datetime.now()
        self.message_count = 0
        self.contracts_subscribed = []

        # Initialize clients
        print("\nInitializing clients...")
        # Use local token database
        tokens_db = "tokens/schwabdev_tokens.db"

        self.schwab_client = schwabdev.Client(
            os.getenv("SCHWAB_API_KEY"),
            os.getenv("SCHWAB_API_SECRET"),
            os.getenv("SCHWAB_CALLBACK_URL"),
            tokens_db=tokens_db,
        )
        self.streamer = schwabdev.Stream(self.schwab_client)
        self.ts_store = TimescaleStore()

        # Initialize enricher for contract details (Greeks, strike, etc.)
        self.enricher = OptionContractEnricher(self.schwab_client)

        print("✓ Schwabdev client initialized")
        print("✓ TimescaleDB connected")
        print("✓ Contract enricher initialized")

    def get_spxw_contracts(self) -> List[str]:
        """
        Get list of SPXW option contracts to stream.

        Returns:
            List of option symbols in schwabdev format
        """
        print(f"\nFetching SPXW contracts (DTE: {self.min_dte}-{self.max_dte}, Strike range: ±{self.strike_range_pct*100}%)...")

        # Get SPX price to filter strikes
        try:
            response = self.schwab_client.quote("$SPX")

            # Check response status
            if response.status_code != 200:
                print(f"  ⚠️  SPX quote API error: HTTP {response.status_code}")
                print(f"  Response: {response.text[:200]}")
                spx_price = 6000.0
            else:
                spx_data = response.json()

                if "$SPX" in spx_data:
                    spx_price = spx_data["$SPX"]["quote"]["lastPrice"]
                    print(f"  SPX price: ${spx_price:.2f}")
                else:
                    print("  ⚠️  Could not get SPX price, using default")
                    spx_price = 6000.0
        except Exception as e:
            print(f"  ⚠️  Error getting SPX price: {e}")
            if hasattr(e, 'response'):
                print(f"  Response status: {e.response.status_code if hasattr(e.response, 'status_code') else 'unknown'}")
                print(f"  Response text: {e.response.text[:200] if hasattr(e.response, 'text') else 'none'}")
            spx_price = 6000.0

        # Calculate strike range
        strike_min = spx_price * (1 - self.strike_range_pct)
        strike_max = spx_price * (1 + self.strike_range_pct)

        print(f"  Strike range: ${strike_min:.0f} - ${strike_max:.0f}")

        # Get option chain from Schwab
        # For SPXW, we need to get the chain and filter
        contracts = []

        try:
            # Get SPXW option chain
            # Note: This uses REST API to discover contracts
            # schwabdev uses camelCase for parameters
            response = self.schwab_client.option_chains("$SPX", strikeCount=50)

            # Check response status before parsing
            if response.status_code != 200:
                print(f"  ✗ API Error: HTTP {response.status_code}")
                print(f"  Response: {response.text[:500]}")
                return []

            # Try to parse JSON
            try:
                chain_data = response.json()
            except Exception as json_err:
                print(f"  ✗ JSON Parse Error: {json_err}")
                print(f"  Response status: {response.status_code}")
                print(f"  Response text: {response.text[:500]}")
                return []

            # Parse chain to get SPXW contracts
            # schwabdev returns data in different format than schwab-py
            # Extract calls and puts

            today = datetime.now().date()

            for option_type in ['callExpDateMap', 'putExpDateMap']:
                if option_type not in chain_data:
                    continue

                exp_map = chain_data[option_type]

                for exp_date_str, strikes in exp_map.items():
                    # Parse expiration date
                    # Format: "2025-12-20:45" (date:DTE)
                    exp_date = datetime.strptime(exp_date_str.split(':')[0], '%Y-%m-%d').date()
                    dte = (exp_date - today).days

                    # Filter by DTE
                    if dte < self.min_dte or dte > self.max_dte:
                        continue

                    # Check each strike
                    for strike_str, contract_list in strikes.items():
                        strike = float(strike_str)

                        # Filter by strike range
                        if strike < strike_min or strike > strike_max:
                            continue

                        # Get contract symbol
                        for contract in contract_list:
                            symbol = contract.get('symbol', '')

                            # Only include SPXW (weekly)
                            if 'SPXW' in symbol:
                                contracts.append(symbol)

            print(f"  Found {len(contracts)} SPXW contracts")

            # Show sample
            if contracts:
                print(f"  Sample contracts:")
                for contract in contracts[:5]:
                    print(f"    {contract}")
                if len(contracts) > 5:
                    print(f"    ... and {len(contracts) - 5} more")

        except Exception as e:
            print(f"  ✗ Error fetching contracts: {e}")
            import traceback
            traceback.print_exc()

        return contracts

    def handle_message(self, message: str):
        """
        Handle incoming stream message.

        Args:
            message: JSON string from stream
        """
        self.message_count += 1

        try:
            # Parse message
            msg_data = json.loads(message) if isinstance(message, str) else message

            # schwabdev message format: {"data": [{"service": "...", "content": [...]}]}
            # or {"response": [...]} or {"notify": [...]}
            if isinstance(msg_data, dict):
                # Check for data messages
                if 'data' in msg_data:
                    for data_item in msg_data['data']:
                        service = data_item.get('service', '')
                        content = data_item.get('content', [])

                        # Process level one options data
                        if service == 'LEVELONE_OPTIONS' and content:
                            timestamp = datetime.now()

                            for item in content:
                                symbol = item.get('key', '')
                                if not symbol:
                                    continue

                                # Create quote record
                                # Field mappings based on schwabdev LEVELONE_OPTIONS:
                                # 2=Bid, 3=Ask, 4=Last, 5=High, 6=Low, 7=Close, 8=Volume
                                # 10=IV, 12=Exp Year, 15=Open, 16=Bid Size, 17=Ask Size
                                # 20=Strike, 21=Contract Type, 23=Exp Month, 26=Exp Day
                                # 28=Delta, 29=Gamma, 30=Theta, 31=Vega, 32=Rho
                                quote = {
                                    'timestamp': timestamp,
                                    'symbol': symbol,
                                    'bid': item.get('2'),
                                    'ask': item.get('3'),
                                    'last': item.get('4'),
                                    'high': item.get('5'),
                                    'low': item.get('6'),
                                    'close': item.get('7'),
                                    'volume': item.get('8'),
                                    'open': item.get('15'),
                                    'bid_size': item.get('16'),
                                    'ask_size': item.get('17'),
                                    'strike': item.get('20'),
                                    'contract_type': item.get('21'),
                                    'exp_year': item.get('12'),
                                    'exp_month': item.get('23'),
                                    'exp_day': item.get('26'),
                                    'iv': item.get('10'),
                                    'delta': item.get('28'),
                                    'gamma': item.get('29'),
                                    'theta': item.get('30'),
                                    'vega': item.get('31'),
                                    'rho': item.get('32'),
                                }

                                # Debug: Log first few messages to see what fields are actually populated
                                if self.message_count <= 3:
                                    print(f"\n  🔍 DEBUG - Sample message #{self.message_count}")
                                    print(f"     Symbol: {symbol}")
                                    print(f"     Fields received in item: {list(item.keys())}")
                                    print(f"     Strike (field 20): {item.get('20')}")
                                    print(f"     IV (field 10): {item.get('10')}")
                                    print(f"     Delta (field 28): {item.get('28')}")
                                    print(f"     Gamma (field 29): {item.get('29')}")
                                    print(f"     Theta (field 30): {item.get('30')}")
                                    print(f"     Vega (field 31): {item.get('31')}")
                                    print(f"     Rho (field 32): {item.get('32')}")

                                # Enrich quote with contract details from option chain
                                # (fills in Greeks and strike if missing from stream)
                                enriched_quote = self.enricher.enrich_quote(quote)

                                # Add to buffer
                                self.quote_buffer[symbol].append(enriched_quote)

            # Check if we should flush (create 1-min bars)
            elapsed = (datetime.now() - self.last_flush_time).total_seconds()
            if elapsed >= self.aggregate_interval:
                self.flush_to_database()

        except Exception as e:
            print(f"Error handling message: {e}")
            import traceback
            traceback.print_exc()

        # Periodic status update - show every 10 messages for debugging
        if self.message_count % 10 == 0:
            now = datetime.now()
            print(f"  📊 [{now.strftime('%H:%M:%S')}] Messages: {self.message_count} | Buffered symbols: {len(self.quote_buffer)}")

    def refresh_token(self):
        """Refresh Schwab OAuth token."""
        try:
            now = datetime.now()
            print(f"\n🔄 [{now.strftime('%Y-%m-%d %H:%M:%S')}] Refreshing Schwab OAuth token...")

            # Call token refresh
            self.schwab_client.update_tokens_auto()

            self.last_token_refresh = now
            print(f"  ✓ Token refresh successful")
            return True

        except Exception as e:
            print(f"  ✗ Token refresh failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def flush_to_database(self):
        """Aggregate buffered quotes into 1-minute bars and save to database."""

        if not self.quote_buffer:
            self.last_flush_time = datetime.now()
            return

        now = datetime.now()
        print(f"\n  💾 [{now.strftime('%Y-%m-%d %H:%M:%S')}] Flushing {len(self.quote_buffer)} symbols to database...")

        bars_to_insert = []
        flush_timestamp = self.last_flush_time

        for symbol, quotes in self.quote_buffer.items():
            if not quotes:
                continue

            # Aggregate quotes into OHLC bar
            # Extract prices (use last, fallback to mid)
            prices = []
            for q in quotes:
                price = q.get('last')
                if price is None and q.get('bid') and q.get('ask'):
                    price = (q['bid'] + q['ask']) / 2.0
                if price:
                    prices.append(price)

            if not prices:
                continue

            # Calculate OHLC
            # Filter out None values for volume aggregation
            volumes = [q.get('volume', 0) for q in quotes if q.get('volume') is not None]
            max_volume = max(volumes) if volumes else 0

            # Calculate VWAP (Volume Weighted Average Price)
            # VWAP = Σ(Price × Volume) / Σ(Volume)
            vwap = None
            price_volume_sum = 0.0
            total_volume_for_vwap = 0.0

            for i, q in enumerate(quotes):
                price = q.get('last')
                if price is None and q.get('bid') and q.get('ask'):
                    price = (q['bid'] + q['ask']) / 2.0

                volume = q.get('volume', 0)

                # For cumulative volume (quotes contain cumulative volume from market open)
                # We need to calculate the incremental volume for this update
                if i > 0 and volume is not None:
                    prev_volume = quotes[i-1].get('volume', 0)
                    if prev_volume is not None:
                        incremental_volume = volume - prev_volume
                    else:
                        incremental_volume = volume
                else:
                    # First quote or volume is None
                    incremental_volume = volume if volume is not None else 0

                if price and incremental_volume and incremental_volume > 0:
                    price_volume_sum += price * incremental_volume
                    total_volume_for_vwap += incremental_volume

            if total_volume_for_vwap > 0:
                vwap = price_volume_sum / total_volume_for_vwap

            # Get latest quote for contract details
            latest_quote = quotes[-1]

            # Build expiration date from year, month, day fields
            exp_date = None
            try:
                exp_year = latest_quote.get('exp_year')
                exp_month = latest_quote.get('exp_month')
                exp_day = latest_quote.get('exp_day')

                if exp_year and exp_month and exp_day:
                    # Convert to datetime
                    exp_date = datetime(int(exp_year), int(exp_month), int(exp_day)).date()
            except (ValueError, TypeError) as e:
                # If parsing fails, leave as None
                pass

            # Fallback: parse expiration date from ticker symbol if not available from quote data
            if exp_date is None:
                exp_date = parse_expiration_from_ticker(symbol)

            # Get contract type (map Schwab format to our format)
            contract_type_raw = latest_quote.get('contract_type')
            if contract_type_raw:
                # Schwab returns 'C' or 'P' (or 'CALL'/'PUT')
                contract_type = 'call' if str(contract_type_raw).upper().startswith('C') else 'put'
            else:
                # Fallback: parse from symbol
                contract_type = 'call' if 'C' in symbol else 'put'

            bar = {
                'timestamp': flush_timestamp,
                'option_ticker': symbol,
                'underlying_ticker': 'SPX',
                'open': prices[0],
                'high': max(prices),
                'low': min(prices),
                'close': prices[-1],
                'volume': max_volume,
                'vwap': vwap,  # Calculated from price × volume
                'transactions': len(quotes),
                # Latest quote data
                'bid': latest_quote.get('bid'),
                'ask': latest_quote.get('ask'),
                'bid_size': latest_quote.get('bid_size'),
                'ask_size': latest_quote.get('ask_size'),
                # Contract details from stream
                'strike_price': latest_quote.get('strike'),
                'contract_type': contract_type,
                'expiration_date': exp_date,
                # Greeks from stream
                'delta': latest_quote.get('delta'),
                'gamma': latest_quote.get('gamma'),
                'theta': latest_quote.get('theta'),
                'vega': latest_quote.get('vega'),
                'rho': latest_quote.get('rho'),
                'implied_volatility': latest_quote.get('iv'),
                'data_source': 'schwabdev_stream',
            }

            bars_to_insert.append(bar)

        # Insert into database
        if bars_to_insert:
            try:
                inserted = self.ts_store.bulk_insert_option_bars(bars_to_insert)
                print(f"  ✓ Inserted {inserted} bars")
            except Exception as e:
                print(f"  ✗ Database error: {e}")

        # Clear buffer
        self.quote_buffer.clear()
        self.last_flush_time = datetime.now()

    def start(self):
        """Start streaming SPXW options."""

        print("\n" + "="*70)
        print("SPXW OPTIONS STREAMING - schwabdev")
        print("="*70)
        print(f"Started: {datetime.now()}")
        print(f"DTE Range: {self.min_dte} - {self.max_dte} days")
        print(f"Strike Range: ±{self.strike_range_pct*100}%")
        print(f"Aggregate Interval: {self.aggregate_interval}s")
        print("="*70)

        # Refresh token at startup to ensure authentication
        print("\nRefreshing authentication token...")
        if not self.refresh_token():
            print("\n❌ Failed to refresh token at startup!")
            print("Please check your authentication credentials and token database.")
            return

        # Get contracts to stream
        contracts = self.get_spxw_contracts()

        if not contracts:
            print("\n❌ No contracts found to stream!")
            return

        self.contracts_subscribed = contracts

        # Refresh enricher cache with full option chain
        print("\nPopulating contract details cache...")
        self.enricher.refresh_contract_details("$SPX", strike_count=50)
        stats = self.enricher.get_cache_stats()
        print(f"✓ Cached {stats['contracts_cached']} contracts for enrichment")

        # Start stream
        print("\nStarting stream...")
        self.streamer.start_auto(
            self.handle_message,
            start_time=time(9, 29, 0),
            stop_time=time(16, 0, 0),
            on_days=(0,1,2,3,4),
            now_timezone=zoneinfo.ZoneInfo("America/New_York"),
            daemon=True
        )
        print("✓ Stream started")

        # Subscribe to options
        # Note: Schwab has a limit of 500 symbols per subscription
        MAX_PER_SUB = 500

        print(f"\nSubscribing to {len(contracts)} contracts...")

        for i in range(0, len(contracts), MAX_PER_SUB):
            batch = contracts[i:i+MAX_PER_SUB]

            # Convert to comma-separated string
            symbols_str = ",".join(batch)

            # Subscribe to level one options with all required fields
            # Based on schwabdev.stream_fields['LEVELONE_OPTIONS']:
            # 0=Symbol, 2=Bid Price, 3=Ask Price, 4=Last Price
            # 5=High, 6=Low, 7=Close, 8=Total Volume, 9=Open Interest, 10=Volatility (IV)
            # 12=Exp Year, 15=Open, 16=Bid Size, 17=Ask Size, 20=Strike, 21=Contract Type
            # 23=Exp Month, 26=Exp Day, 28=Delta, 29=Gamma, 30=Theta, 31=Vega, 32=Rho
            # 37=Mark Price, 38=Quote Time, 39=Trade Time
            fields = "0,2,3,4,5,6,7,8,9,10,12,15,16,17,20,21,23,26,28,29,30,31,32,37,38,39"

            self.streamer.send(
                self.streamer.level_one_options(symbols_str, fields)
            )

            print(f"  ✓ Subscribed to batch {i//MAX_PER_SUB + 1} ({len(batch)} contracts)")
            dt_time.sleep(0.5)  # Small delay between batches

        print("\n✅ All subscriptions active")
        print("Streaming data... (Press Ctrl+C to stop)")

        # Keep running
        try:
            while True:
                dt_time.sleep(60)

                now = datetime.now()

                # Check if token refresh is needed (every 14 minutes)
                time_since_refresh = (now - self.last_token_refresh).total_seconds() / 60.0
                if time_since_refresh >= 14:
                    self.refresh_token()

                # Status update with timestamp
                enricher_stats = self.enricher.get_cache_stats()
                print(f"\n📊 Status Update [{now.strftime('%Y-%m-%d %H:%M:%S')}]:")
                print(f"   Messages received: {self.message_count}")
                print(f"   Contracts streaming: {len(self.contracts_subscribed)}")
                print(f"   Buffered symbols: {len(self.quote_buffer)}")
                print(f"   Contract cache: {enricher_stats['contracts_cached']} contracts")
                print(f"   Cache age: {enricher_stats['cache_age_minutes']:.1f} minutes")
                print(f"   Token age: {time_since_refresh:.1f} minutes")

        except KeyboardInterrupt:
            print("\n\n⚠️  Stopping stream...")
            self.stop()

    def stop(self):
        """Stop streaming and cleanup."""

        # Flush any remaining data
        print("Flushing remaining data...")
        self.flush_to_database()

        # Stop stream
        print("Stopping stream...")
        self.streamer.stop()

        # Close database
        print("Closing database...")
        self.ts_store.close()

        print("✅ Stopped")


def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(description="Stream SPXW options data")

    parser.add_argument(
        "--max-dte",
        type=int,
        default=45,
        help="Maximum days to expiration (default: 45)"
    )

    parser.add_argument(
        "--min-dte",
        type=int,
        default=0,
        help="Minimum days to expiration (default: 0)"
    )

    parser.add_argument(
        "--strike-range-pct",
        type=float,
        default=0.10,
        help="Strike range as percentage of underlying (default: 0.10 = ±10%%)"
    )

    parser.add_argument(
        "--aggregate-interval",
        type=int,
        default=60,
        help="Seconds to aggregate into bars (default: 60 = 1min bars)"
    )

    args = parser.parse_args()

    # Create and start streamer
    streamer = SPXWOptionsStreamer(
        max_dte=args.max_dte,
        min_dte=args.min_dte,
        strike_range_pct=args.strike_range_pct,
        aggregate_interval_seconds=args.aggregate_interval
    )

    streamer.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✅ Stopped by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
