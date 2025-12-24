"""Main streaming service orchestrator."""

import os
import sys
import json
import time as dt_time
from pathlib import Path
from datetime import datetime, time
from typing import List, Optional
import zoneinfo

import schwabdev
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from quant_vibe.data.timescale_store import TimescaleStore
from streaming_service.config import StreamingConfig
from streaming_service.token_manager import TokenManager
from streaming_service.aggregator import BarAggregator
from streaming_service.underlying_aggregator import UnderlyingBarAggregator
from streaming_service.enrich_stream_with_chain import OptionContractEnricher


class StreamingService:
    """SPXW Options Streaming Service.

    Orchestrates the full streaming pipeline:
    1. Token management (auto-refresh)
    2. Contract discovery and subscription
    3. Quote streaming and enrichment
    4. Bar aggregation
    5. Database persistence
    """

    def __init__(self, config: Optional[StreamingConfig] = None):
        """Initialize streaming service.

        Args:
            config: Streaming configuration (uses defaults if not provided)
        """
        load_dotenv()

        self.config = config or StreamingConfig()
        self.message_count = 0
        self.contracts_subscribed = []

        print("\nInitializing Streaming Service...")
        print(f"  DTE Range: {self.config.min_dte} - {self.config.max_dte}")
        print(f"  Strike Range: ±{self.config.strike_range_pct*100}%")
        print(f"  Aggregate Interval: {self.config.aggregate_interval_seconds}s")
        print(f"  Token Refresh: Every {self.config.token_refresh_minutes} minutes")

        # Initialize Schwab client
        self.schwab_client = schwabdev.Client(
            os.getenv("SCHWAB_API_KEY"),
            os.getenv("SCHWAB_API_SECRET"),
            os.getenv("SCHWAB_CALLBACK_URL"),
            tokens_db=self.config.tokens_db_path,
        )
        self.streamer = schwabdev.Stream(self.schwab_client)
        print("  ✓ Schwabdev client initialized")

        # Initialize components
        self.token_manager = TokenManager(
            self.schwab_client,
            refresh_interval_minutes=self.config.token_refresh_minutes
        )
        self.aggregator = BarAggregator(
            aggregate_interval_seconds=self.config.aggregate_interval_seconds
        )
        self.underlying_aggregator = UnderlyingBarAggregator(
            aggregate_interval_seconds=self.config.aggregate_interval_seconds
        )
        self.ts_store = TimescaleStore()
        self.enricher = OptionContractEnricher(self.schwab_client)

        print("  ✓ Token manager initialized")
        print("  ✓ Bar aggregator initialized")
        print("  ✓ Underlying bar aggregator initialized")
        print("  ✓ TimescaleDB connected")
        print("  ✓ Contract enricher initialized")

    def get_spxw_contracts(self) -> List[str]:
        """Get list of SPXW option contracts to stream.

        Returns:
            List of option symbols
        """
        print(f"\nFetching SPXW contracts (DTE: {self.config.min_dte}-{self.config.max_dte}, Strike range: ±{self.config.strike_range_pct*100}%)...")

        # Get SPX price to filter strikes
        spx_price = self._get_spx_price()

        # Calculate strike range
        strike_min = spx_price * (1 - self.config.strike_range_pct)
        strike_max = spx_price * (1 + self.config.strike_range_pct)
        print(f"  Strike range: ${strike_min:.0f} - ${strike_max:.0f}")

        # Get option chain
        contracts = []

        try:
            response = self.schwab_client.option_chains("$SPX", strikeCount=50)

            # Check response status
            if response.status_code != 200:
                print(f"  ✗ API Error: HTTP {response.status_code}")
                print(f"  Response: {response.text[:500]}")
                return []

            # Parse JSON
            try:
                chain_data = response.json()
            except Exception as json_err:
                print(f"  ✗ JSON Parse Error: {json_err}")
                print(f"  Response status: {response.status_code}")
                print(f"  Response text: {response.text[:500]}")
                return []

            # Parse chain to get SPXW contracts
            today = datetime.now().date()

            for option_type in ['callExpDateMap', 'putExpDateMap']:
                if option_type not in chain_data:
                    continue

                exp_map = chain_data[option_type]

                for exp_date_str, strikes in exp_map.items():
                    # Parse expiration date (format: "2025-12-20:45")
                    exp_date = datetime.strptime(exp_date_str.split(':')[0], '%Y-%m-%d').date()
                    dte = (exp_date - today).days

                    # Filter by DTE
                    if dte < self.config.min_dte or dte > self.config.max_dte:
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

    def _get_spx_price(self) -> float:
        """Get current SPX price.

        Returns:
            SPX price (or default 6000.0 if fetch fails)
        """
        try:
            response = self.schwab_client.quote("$SPX")

            if response.status_code != 200:
                print(f"  ⚠️  SPX quote API error: HTTP {response.status_code}")
                print(f"  Response: {response.text[:200]}")
                return 6000.0

            spx_data = response.json()

            if "$SPX" in spx_data:
                spx_price = spx_data["$SPX"]["quote"]["lastPrice"]
                print(f"  SPX price: ${spx_price:.2f}")
                return spx_price
            else:
                print("  ⚠️  Could not get SPX price, using default")
                return 6000.0

        except Exception as e:
            print(f"  ⚠️  Error getting SPX price: {e}")
            return 6000.0

    def handle_message(self, message: str):
        """Handle incoming stream message.

        Args:
            message: JSON string from stream
        """
        self.message_count += 1

        try:
            # Parse message
            msg_data = json.loads(message) if isinstance(message, str) else message

            # Process level one options data
            if isinstance(msg_data, dict):
                if 'data' in msg_data:
                    for data_item in msg_data['data']:
                        service = data_item.get('service', '')
                        content = data_item.get('content', [])

                        if service == 'LEVELONE_OPTIONS' and content:
                            timestamp = datetime.now()

                            for item in content:
                                symbol = item.get('key', '')
                                if not symbol:
                                    continue

                                # Create quote record
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

                                # Enrich with contract details if needed
                                enriched_quote = self.enricher.enrich_quote(quote)

                                # Add to aggregator
                                self.aggregator.add_quote(enriched_quote)

                        # Handle underlying asset quotes (SPX, etc.)
                        elif service == 'LEVELONE_EQUITIES' and content:
                            timestamp = datetime.now()

                            for item in content:
                                symbol = item.get('key', '')
                                if not symbol:
                                    continue

                                # Create underlying quote record
                                quote = {
                                    'timestamp': timestamp,
                                    'symbol': symbol,
                                    'bid': item.get('2'),
                                    'ask': item.get('3'),
                                    'last': item.get('4'),
                                    'high': item.get('9'),
                                    'low': item.get('10'),
                                    'close': item.get('50'),
                                    'volume': item.get('8'),
                                    'open': item.get('28'),
                                }

                                # Add to underlying aggregator
                                self.underlying_aggregator.add_quote(quote)

            # Check if we should flush (create 1-min bars)
            if self.aggregator.should_flush():
                self._flush_bars()

            # Also check underlying aggregator
            if self.underlying_aggregator.should_flush():
                self._flush_underlying_bars()

        except Exception as e:
            print(f"Error handling message: {e}")
            import traceback
            traceback.print_exc()

        # Periodic status update
        if self.message_count % 10 == 0:
            now = datetime.now()
            print(f"  📊 [{now.strftime('%H:%M:%S')}] Messages: {self.message_count} | Buffered symbols: {self.aggregator.get_buffered_symbol_count()}")

    def _flush_bars(self):
        """Flush aggregated option bars to database."""
        bars = self.aggregator.flush()

        if bars:
            try:
                inserted = self.ts_store.bulk_insert_option_bars(bars)
                print(f"  ✓ Inserted {inserted} option bars")
            except Exception as e:
                print(f"  ✗ Database error (options): {e}")

    def _flush_underlying_bars(self):
        """Flush aggregated underlying bars to database."""
        bars = self.underlying_aggregator.flush()

        if bars:
            try:
                inserted = self.ts_store.bulk_insert_underlying_bars(bars)
                print(f"  ✓ Inserted {inserted} underlying bars")
            except Exception as e:
                print(f"  ✗ Database error (underlying): {e}")

    def start(self):
        """Start the streaming service."""
        print("\n" + "="*70)
        print("SPXW OPTIONS STREAMING SERVICE")
        print("="*70)
        print(f"Started: {datetime.now()}")
        print(f"DTE Range: {self.config.min_dte} - {self.config.max_dte} days")
        print(f"Strike Range: ±{self.config.strike_range_pct*100}%")
        print(f"Aggregate Interval: {self.config.aggregate_interval_seconds}s")
        print("="*70)

        # Refresh token at startup
        print("\nRefreshing authentication token...")
        if not self.token_manager.refresh():
            print("\n❌ Failed to refresh token at startup!")
            print("Please check your authentication credentials and token database.")
            return

        # Get contracts to stream
        contracts = self.get_spxw_contracts()

        if not contracts:
            print("\n❌ No contracts found to stream!")
            return

        self.contracts_subscribed = contracts

        # Refresh enricher cache
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
            on_days=(0, 1, 2, 3, 4),
            now_timezone=zoneinfo.ZoneInfo("America/New_York"),
            daemon=True
        )
        print("✓ Stream started")

        # Subscribe to options
        self._subscribe_to_contracts(contracts)

        # Subscribe to underlying asset ($SPX)
        self._subscribe_to_underlying()

        print("\n✅ All subscriptions active")
        print("Streaming data... (Press Ctrl+C to stop)")

        # Main loop
        self._run_main_loop()

    def _subscribe_to_contracts(self, contracts: List[str]):
        """Subscribe to option contracts.

        Args:
            contracts: List of contract symbols
        """
        MAX_PER_SUB = self.config.max_symbols_per_subscription

        print(f"\nSubscribing to {len(contracts)} contracts...")

        for i in range(0, len(contracts), MAX_PER_SUB):
            batch = contracts[i:i+MAX_PER_SUB]
            symbols_str = ",".join(batch)

            # Subscribe with all fields
            fields = "0,2,3,4,5,6,7,8,9,10,12,15,16,17,20,21,23,26,28,29,30,31,32,37,38,39"

            self.streamer.send(
                self.streamer.level_one_options(symbols_str, fields)
            )

            print(f"  ✓ Subscribed to batch {i//MAX_PER_SUB + 1} ({len(batch)} contracts)")
            dt_time.sleep(0.5)

    def _subscribe_to_underlying(self):
        """Subscribe to underlying asset quotes ($SPX)."""
        print("\nSubscribing to underlying asset ($SPX)...")

        # Subscribe to $SPX with equity level one data
        # Fields: https://developer.schwabapi.com/products/trader-api--individual/details/documentation/Market-Data
        # 0=Symbol, 2=Bid, 3=Ask, 4=Last, 8=Volume, 9=High, 10=Low, 28=Open, 50=Close
        fields = "0,2,3,4,8,9,10,28,50"

        self.streamer.send(
            self.streamer.level_one_equities("$SPX", fields)
        )

        print("  ✓ Subscribed to $SPX equity quotes")

    def _run_main_loop(self):
        """Run main service loop."""
        try:
            while True:
                dt_time.sleep(60)

                now = datetime.now()

                # Check if token refresh needed
                if self.token_manager.needs_refresh():
                    self.token_manager.refresh()

                # Status update
                enricher_stats = self.enricher.get_cache_stats()
                token_age = self.token_manager.get_token_age_minutes()

                print(f"\n📊 Status Update [{now.strftime('%Y-%m-%d %H:%M:%S')}]:")
                print(f"   Messages received: {self.message_count}")
                print(f"   Contracts streaming: {len(self.contracts_subscribed)}")
                print(f"   Buffered option symbols: {self.aggregator.get_buffered_symbol_count()}")
                print(f"   Buffered underlying symbols: {self.underlying_aggregator.get_buffered_symbol_count()}")
                print(f"   Contract cache: {enricher_stats['contracts_cached']} contracts")
                print(f"   Cache age: {enricher_stats['cache_age_minutes']:.1f} minutes")
                print(f"   Token age: {token_age:.1f} minutes")

        except KeyboardInterrupt:
            print("\n\n⚠️  Stopping service...")
            self.stop()

    def stop(self):
        """Stop the streaming service."""
        print("Flushing remaining data...")
        self._flush_bars()
        self._flush_underlying_bars()

        print("Stopping stream...")
        self.streamer.stop()

        print("Closing database...")
        self.ts_store.close()

        print("✅ Service stopped")
