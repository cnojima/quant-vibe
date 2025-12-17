"""Real-time SPXW options data collector using Schwab streaming API.

This module provides real-time streaming of:
- Options quotes (bid/ask)
- Options bars (OHLC aggregation)
- Options Greeks
- Underlying price updates

Data is collected via Schwab websocket streams and stored in TimescaleDB.
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import defaultdict
import json

from schwab import auth
from schwab.streaming import StreamClient
from dotenv import load_dotenv

from .timescale_store import TimescaleStore

load_dotenv()


class RealtimeOptionsCollector:
    """
    Real-time collector for SPXW options data via Schwab streaming API.

    Features:
    - Subscribes to option quotes for active SPXW contracts
    - Aggregates 1-minute bars from quote updates
    - Collects Greeks in real-time
    - Automatically rotates contracts as they expire
    - Stores data in TimescaleDB
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        token_path: Optional[str] = None,
        callback_url: Optional[str] = None,
        max_dte: int = 45,
        min_dte: int = 0,
        strike_range_pct: float = 0.10,  # ±10% from ATM
    ):
        """
        Initialize real-time collector.

        Args:
            api_key: Schwab API key
            app_secret: Schwab app secret
            token_path: Path to token file
            callback_url: OAuth callback URL
            max_dte: Maximum days to expiration to collect
            min_dte: Minimum days to expiration to collect
            strike_range_pct: Strike range as percentage from ATM (0.10 = ±10%)

        Note:
            Contracts are automatically refreshed daily at 5:00 PM ET (1 hour after market close)
            to add new contracts and remove expired ones.
        """
        self.api_key = api_key or os.getenv("SCHWAB_API_KEY")
        self.app_secret = app_secret or os.getenv("SCHWAB_API_SECRET")
        self.token_path = token_path or os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
        self.callback_url = callback_url or os.getenv("SCHWAB_CALLBACK_URL")

        self.max_dte = max_dte
        self.min_dte = min_dte
        self.strike_range_pct = strike_range_pct

        # Initialize Schwab client
        self.client = None
        self.stream_client = None

        # Data storage
        self.ts_store = TimescaleStore()

        # Tracking
        self.subscribed_contracts: Set[str] = set()
        self.current_bars: Dict[str, Dict] = defaultdict(dict)  # In-progress bars
        self.last_bar_time: Dict[str, datetime] = {}  # Last bar close time per contract

        # Contract details cache
        self.contract_details: Dict[str, Dict] = {}

        # Contract rotation tracking
        self.last_contract_refresh: Optional[datetime] = None
        self.contracts_refreshed_today: bool = False

    async def initialize(self):
        """Initialize Schwab client and streaming connection."""
        print("Initializing Schwab streaming client...")

        # Create Schwab client using OAuth
        self.client = auth.client_from_token_file(
            self.token_path,
            self.api_key,
            self.app_secret
        )

        # Create streaming client
        self.stream_client = StreamClient(self.client, account_id=os.getenv("SCHWAB_ACCOUNT_NUMBER"))

        print("✅ Schwab streaming client initialized")

    async def get_active_spxw_contracts(self) -> List[str]:
        """
        Get list of active SPXW contracts to subscribe to.

        Returns contracts within min_dte to max_dte range,
        and within strike_range_pct of ATM.
        """
        print(f"Finding SPXW contracts ({self.min_dte}-{self.max_dte} DTE, ±{self.strike_range_pct*100}% strikes)...")

        # Get current SPX price (from quote)
        quote = self.client.get_quote("$SPX").json()
        spx_price = quote.get("$SPX", {}).get("quote", {}).get("lastPrice", 0)

        if not spx_price:
            print("⚠️  Could not get SPX price, using 6000 as default")
            spx_price = 6000.0

        print(f"Current SPX price: ${spx_price:.2f}")

        # Calculate strike range
        strike_min = spx_price * (1 - self.strike_range_pct)
        strike_max = spx_price * (1 + self.strike_range_pct)

        print(f"Strike range: ${strike_min:.0f} - ${strike_max:.0f}")

        # Get expiration dates
        today = datetime.now()
        min_exp_date = today + timedelta(days=self.min_dte)
        max_exp_date = today + timedelta(days=self.max_dte)

        # Use Schwab API to get option chain
        # Note: This is a simplified version - you may need to call this per expiration
        # or use the existing MassiveClient to list contracts

        print(f"Expiration range: {min_exp_date.date()} to {max_exp_date.date()}")

        # Fetch option chain from Schwab API
        try:
            from schwab.client import Client

            # Try both SPX and SPXW symbols
            # $SPX.X is the proper format for SPX index options in Schwab API
            symbols_to_try = ["$SPX"]

            response = None
            for symbol in symbols_to_try:
                try:
                    # Schwab API might be sensitive to parameters
                    # Try with minimal parameters first
                    response = self.client.get_option_chain(
                        symbol,
                        contract_type=Client.Options.ContractType.ALL,
                        strike_count=50,  # Return 50 strikes above and below ATM
                        include_underlying_quote=True
                    )

                    if response.status_code == 200:
                        print(f"✅ Successfully fetched option chain using symbol: {symbol}")
                        break
                    else:
                        print(f"⚠️  Symbol {symbol} failed with status {response.status_code}: {response.text[:200]}")
                except Exception as e:
                    print(f"⚠️  Symbol {symbol} failed: {e}")
                    continue

            if response is None or response.status_code != 200:
                print(f"⚠️  Failed to fetch option chain from all symbols")
                print(f"   This might be due to API permissions or incorrect symbol format")
                print(f"   Consider using MassiveClient for contract discovery instead")
                return []

            chain_data = response.json()

            # Extract contract symbols from the chain
            contracts = []
            contract_details = {}

            # Process call contracts
            if 'callExpDateMap' in chain_data:
                for exp_date, strikes in chain_data['callExpDateMap'].items():
                    # Parse expiration date from key (format: "2024-12-20:7")
                    exp_date_str = exp_date.split(':')[0]
                    exp_datetime = datetime.strptime(exp_date_str, '%Y-%m-%d')

                    # Filter by DTE range
                    dte = (exp_datetime.date() - today.date()).days
                    if dte < self.min_dte or dte > self.max_dte:
                        continue

                    for strike_price, contracts_list in strikes.items():
                        strike = float(strike_price)

                        # Filter by strike range
                        if strike < strike_min or strike > strike_max:
                            continue

                        for contract in contracts_list:
                            symbol = contract.get('symbol', '')
                            if symbol:
                                contracts.append(symbol)
                                contract_details[symbol] = {
                                    'strike_price': strike,
                                    'expiration_date': exp_datetime,
                                    'option_type': 'C',
                                    'underlying_ticker': 'SPX',
                                    'dte': dte
                                }

            # Process put contracts
            if 'putExpDateMap' in chain_data:
                for exp_date, strikes in chain_data['putExpDateMap'].items():
                    exp_date_str = exp_date.split(':')[0]
                    exp_datetime = datetime.strptime(exp_date_str, '%Y-%m-%d')

                    # Filter by DTE range
                    dte = (exp_datetime.date() - today.date()).days
                    if dte < self.min_dte or dte > self.max_dte:
                        continue

                    for strike_price, contracts_list in strikes.items():
                        strike = float(strike_price)

                        # Filter by strike range
                        if strike < strike_min or strike > strike_max:
                            continue

                        for contract in contracts_list:
                            symbol = contract.get('symbol', '')
                            if symbol:
                                contracts.append(symbol)
                                contract_details[symbol] = {
                                    'strike_price': strike,
                                    'expiration_date': exp_datetime,
                                    'option_type': 'P',
                                    'underlying_ticker': 'SPX',
                                    'dte': dte
                                }

            print(f"✅ Found {len(contracts)} SPXW contracts")

            # Cache contract details for later use
            self.contract_details.update(contract_details)

            return contracts

        except Exception as e:
            print(f"⚠️  Error fetching contracts from Schwab API: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def subscribe_to_contract(self, contract_symbol: str, contract_details: Dict):
        """
        Subscribe to real-time quotes and Greeks for an option contract.

        Args:
            contract_symbol: Option symbol (e.g., 'SPXW  251220C06000000')
            contract_details: Contract metadata (strike, expiration, type)
        """
        if contract_symbol in self.subscribed_contracts:
            return

        # Subscribe to option quotes
        await self.stream_client.options_book_subs([contract_symbol])

        self.subscribed_contracts.add(contract_symbol)
        self.contract_details[contract_symbol] = contract_details

        print(f"📡 Subscribed to {contract_symbol}")

    async def unsubscribe_from_contract(self, contract_symbol: str):
        """
        Unsubscribe from a contract that has expired or is no longer needed.

        Args:
            contract_symbol: Option symbol to unsubscribe from
        """
        if contract_symbol not in self.subscribed_contracts:
            return

        try:
            # Unsubscribe from the stream
            await self.stream_client.options_book_unsubs([contract_symbol])

            # Remove from tracking
            self.subscribed_contracts.remove(contract_symbol)
            if contract_symbol in self.contract_details:
                del self.contract_details[contract_symbol]

            print(f"📡 Unsubscribed from {contract_symbol}")
        except Exception as e:
            print(f"⚠️  Error unsubscribing from {contract_symbol}: {e}")

    async def refresh_contracts(self):
        """
        Refresh contract list to:
        1. Remove expired contracts
        2. Add new contracts that are now within DTE range
        """
        print(f"\n🔄 Refreshing contract list...")

        # Get current active contracts
        new_contracts = await self.get_active_spxw_contracts()
        new_contracts_set = set(new_contracts)

        # Find contracts to remove (expired or out of DTE range)
        contracts_to_remove = self.subscribed_contracts - new_contracts_set

        # Find contracts to add (newly in range)
        contracts_to_add = new_contracts_set - self.subscribed_contracts

        # Unsubscribe from expired/out-of-range contracts
        for contract_symbol in contracts_to_remove:
            await self.unsubscribe_from_contract(contract_symbol)

        # Subscribe to new contracts
        for contract_symbol in contracts_to_add:
            details = self.contract_details.get(contract_symbol, {})
            await self.subscribe_to_contract(contract_symbol, details)

        print(f"✅ Contract refresh complete:")
        print(f"   Removed: {len(contracts_to_remove)}")
        print(f"   Added: {len(contracts_to_add)}")
        print(f"   Total active: {len(self.subscribed_contracts)}")

        self.last_contract_refresh = datetime.now()

    async def handle_option_quote(self, msg: Dict):
        """
        Handle incoming option quote message.

        Quote includes: bid, ask, bid_size, ask_size, last, volume, delta, gamma, etc.
        """
        service = msg.get("service")
        content = msg.get("content", [])

        for quote in content:
            symbol = quote.get("key")
            if not symbol or symbol not in self.subscribed_contracts or symbol == "SPX":
                continue

            # Extract quote data
            timestamp = datetime.fromtimestamp(quote.get("quoteTime", 0) / 1000)
            bid = quote.get("bidPrice")
            ask = quote.get("askPrice")
            bid_size = quote.get("bidSize")
            ask_size = quote.get("askSize")
            last = quote.get("lastPrice")
            volume = quote.get("totalVolume")

            # Greeks
            delta = quote.get("delta")
            gamma = quote.get("gamma")
            theta = quote.get("theta")
            vega = quote.get("vega")
            rho = quote.get("rho")
            implied_vol = quote.get("volatility")

            # Update current bar
            await self.update_bar(
                symbol,
                timestamp,
                last,
                volume,
                bid,
                ask,
                bid_size,
                ask_size,
                delta,
                gamma,
                theta,
                vega,
                rho,
                implied_vol,
            )

    async def update_bar(
        self,
        symbol: str,
        timestamp: datetime,
        price: float,
        volume: int,
        bid: float,
        ask: float,
        bid_size: int,
        ask_size: int,
        delta: float,
        gamma: float,
        theta: float,
        vega: float,
        rho: float,
        implied_vol: float,
    ):
        """
        Update 1-minute bar with new quote data.

        Bars are aggregated from quote updates and closed every minute.
        """
        # Determine current minute
        bar_time = timestamp.replace(second=0, microsecond=0)

        # Check if we need to close the previous bar
        last_time = self.last_bar_time.get(symbol)
        if last_time and bar_time > last_time:
            # Close previous bar
            await self.close_bar(symbol, last_time)

        # Initialize or update current bar
        if symbol not in self.current_bars or bar_time not in self.current_bars[symbol]:
            # Start new bar
            self.current_bars[symbol][bar_time] = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume,
                'bid': bid,
                'ask': ask,
                'bid_size': bid_size,
                'ask_size': ask_size,
                'delta': delta,
                'gamma': gamma,
                'theta': theta,
                'vega': vega,
                'rho': rho,
                'implied_vol': implied_vol,
                'update_count': 1,
            }
        else:
            # Update existing bar
            bar = self.current_bars[symbol][bar_time]
            bar['high'] = max(bar['high'], price)
            bar['low'] = min(bar['low'], price)
            bar['close'] = price
            bar['volume'] = volume
            bar['bid'] = bid
            bar['ask'] = ask
            bar['bid_size'] = bid_size
            bar['ask_size'] = ask_size
            bar['delta'] = delta
            bar['gamma'] = gamma
            bar['theta'] = theta
            bar['vega'] = vega
            bar['rho'] = rho
            bar['implied_vol'] = implied_vol
            bar['update_count'] += 1

        self.last_bar_time[symbol] = bar_time

    async def close_bar(self, symbol: str, bar_time: datetime):
        """
        Close and save a completed 1-minute bar to database.
        """
        if symbol not in self.current_bars or bar_time not in self.current_bars[symbol]:
            return

        bar = self.current_bars[symbol][bar_time]
        details = self.contract_details.get(symbol, {})

        # Insert into TimescaleDB
        try:
            self.ts_store.insert_option_bar(
                timestamp=bar_time,
                option_ticker=symbol,
                underlying_ticker='SPX',
                open_price=bar['open'],
                high=bar['high'],
                low=bar['low'],
                close=bar['close'],
                volume=bar['volume'],
                strike_price=details.get('strike_price'),
                contract_type=details.get('contract_type', 'call'),
                expiration_date=details.get('expiration_date'),
                bid=bar['bid'],
                ask=bar['ask'],
                bid_size=bar['bid_size'],
                ask_size=bar['ask_size'],
                implied_volatility=bar['implied_vol'],
                delta=bar['delta'],
                gamma=bar['gamma'],
                theta=bar['theta'],
                vega=bar['vega'],
                rho=bar['rho'],
                data_source='schwab_realtime',
            )

            print(f"💾 Saved bar: {symbol} @ {bar_time} (updates: {bar['update_count']})")

        except Exception as e:
            print(f"❌ Error saving bar for {symbol}: {e}")

        # Remove closed bar
        del self.current_bars[symbol][bar_time]

    async def start_streaming(self):
        """Start the streaming data collection."""
        print("\n" + "="*70)
        print("STARTING REAL-TIME SPXW OPTIONS DATA COLLECTION")
        print("="*70)

        await self.initialize()

        # Get contracts to subscribe to
        contracts = await self.get_active_spxw_contracts()

        if not contracts:
            print("⚠️  No contracts to subscribe to")
            return

        # Set up message handlers BEFORE logging in
        self.stream_client.add_options_book_handler(self.handle_option_quote)

        # Login to establish the WebSocket connection
        print(f"\n🔌 Logging in to WebSocket...")
        await self.stream_client.login()

        print(f"✅ WebSocket connected")
        print(f"\n📡 Subscribing to {len(contracts)} contracts...")

        # Now subscribe to all contracts (after connection is established)
        for contract_symbol in contracts:
            # Get contract details from cache (populated by get_active_spxw_contracts)
            details = self.contract_details.get(contract_symbol, {})
            await self.subscribe_to_contract(contract_symbol, details)

        # Start streaming
        print(f"\n🚀 Streaming active for {len(contracts)} contracts...")
        print(f"   Contracts will refresh daily at 5:00 PM ET (1 hour after market close)")
        print("Press Ctrl+C to stop\n")

        # Initialize refresh time
        self.last_contract_refresh = datetime.now()

        try:
            # Keep the stream running and check for daily contract refresh
            while True:
                await asyncio.sleep(60)  # Check every minute

                # Get current time in Eastern Time
                import pytz
                et_tz = pytz.timezone('America/New_York')
                now_et = datetime.now(et_tz)
                current_hour = now_et.hour
                current_date = now_et.date()

                # Refresh contracts at 5:00 PM ET (1 hour after market close)
                # Only refresh once per day
                if current_hour >= 17 and not self.contracts_refreshed_today:
                    print(f"\n⏰ Daily contract refresh time (5:00 PM ET)")
                    await self.refresh_contracts()
                    self.contracts_refreshed_today = True

                # Reset the daily flag at midnight
                if current_hour < 17 and self.contracts_refreshed_today:
                    self.contracts_refreshed_today = False

        except KeyboardInterrupt:
            print("\n⚠️  Stopping stream...")
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources."""
        print("Cleaning up...")

        # Close any remaining bars
        for symbol in list(self.current_bars.keys()):
            for bar_time in list(self.current_bars[symbol].keys()):
                await self.close_bar(symbol, bar_time)

        # Close database connection
        if self.ts_store:
            self.ts_store.close()

        print("✅ Cleanup complete")


async def main():
    """Main entry point for real-time collection."""
    collector = RealtimeOptionsCollector(
        max_dte=45,
        min_dte=0,
        strike_range_pct=0.10,  # ±10% from ATM
    )

    await collector.start_streaming()


if __name__ == "__main__":
    asyncio.run(main())
