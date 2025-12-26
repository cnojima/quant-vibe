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
from quant_vibe.config.logging_config import setup_normalized_logging
from quant_vibe.messaging import RedisMessageBroker, Topic
from quant_vibe.utils.retry import retry_with_backoff
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
        self.redis_publish_count = 0  # Track Redis publishes

        # Setup normalized logging
        self.logger = setup_normalized_logging(
            app_name="streaming",
            log_level="INFO",
            log_dir="logs/streaming",
        )

        self.logger.info("Initializing Streaming Service...")
        self.logger.info(f"  DTE Range: {self.config.min_dte} - {self.config.max_dte}")
        self.logger.info(f"  Strike Range: ±{self.config.strike_range_pct*100}%")
        self.logger.info(f"  Aggregate Interval: {self.config.aggregate_interval_seconds}s")
        self.logger.info(f"  Token Refresh: Every {self.config.token_refresh_minutes} minutes")

        # Initialize Schwab client
        self.schwab_client = schwabdev.Client(
            os.getenv("SCHWAB_API_KEY"),
            os.getenv("SCHWAB_API_SECRET"),
            os.getenv("SCHWAB_CALLBACK_URL"),
            tokens_db=self.config.tokens_db_path,
        )
        self.streamer = schwabdev.Stream(self.schwab_client)
        self.logger.info("  ✓ Schwabdev client initialized")

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

        # Initialize message broker (Redis) if enabled
        self.message_broker: Optional[RedisMessageBroker] = None
        if self.config.enable_redis:
            try:
                self.message_broker = RedisMessageBroker(
                    host=self.config.redis_host,
                    port=self.config.redis_port,
                    db=self.config.redis_db,
                )
                self.logger.info("  ✓ Redis message broker connected")
            except Exception as e:
                self.logger.warning(f"  ⚠️  Redis connection failed: {e}")
                self.logger.warning("  ⚠️  Continuing without Redis pub/sub")
                self.message_broker = None

        self.logger.info("  ✓ Token manager initialized")
        self.logger.info("  ✓ Bar aggregator initialized")
        self.logger.info("  ✓ Underlying bar aggregator initialized")
        self.logger.info("  ✓ TimescaleDB connected")
        self.logger.info("  ✓ Contract enricher initialized")

    def get_spxw_contracts(self) -> List[str]:
        """Get list of SPXW option contracts to stream.

        Returns:
            List of option symbols
        """
        self.logger.info(f"Fetching SPXW contracts (DTE: {self.config.min_dte}-{self.config.max_dte}, Strike range: ±{self.config.strike_range_pct*100}%)...")

        # Get SPX price to filter strikes
        spx_price = self._get_spx_price()

        # Calculate strike range
        strike_min = spx_price * (1 - self.config.strike_range_pct)
        strike_max = spx_price * (1 + self.config.strike_range_pct)
        self.logger.info(f"  Strike range: ${strike_min:.0f} - ${strike_max:.0f}")

        # Get option chain
        contracts = []

        try:
            response = self.schwab_client.option_chains("$SPX", strikeCount=50)

            # Check response status
            if response.status_code != 200:
                self.logger.error(f"  ✗ API Error: HTTP {response.status_code}")
                self.logger.error(f"  Response: {response.text[:500]}")
                return []

            # Parse JSON
            try:
                chain_data = response.json()
            except Exception as json_err:
                self.logger.error(f"  ✗ JSON Parse Error: {json_err}")
                self.logger.error(f"  Response status: {response.status_code}")
                self.logger.error(f"  Response text: {response.text[:500]}")
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

            self.logger.info(f"  Found {len(contracts)} SPXW contracts")

            # Show sample
            if contracts:
                self.logger.info("  Sample contracts:")
                for contract in contracts[:5]:
                    self.logger.info(f"    {contract}")
                if len(contracts) > 5:
                    self.logger.info(f"    ... and {len(contracts) - 5} more")

        except Exception as e:
            self.logger.error(f"  ✗ Error fetching contracts: {e}", exc_info=True)
            import traceback
            traceback.print_exc()

        return contracts

    @retry_with_backoff(max_retries=3, backoff_base=2.0, exceptions=(Exception,))
    def _get_spx_price(self) -> float:
        """Get current SPX price with retry logic.

        Returns:
            SPX price (or default 6000.0 if fetch fails)
        """
        try:
            response = self.schwab_client.quote("$SPX")

            if response.status_code != 200:
                self.logger.warning(f"  ⚠️  SPX quote API error: HTTP {response.status_code}")
                self.logger.warning(f"  Response: {response.text[:200]}")
                return 6000.0

            spx_data = response.json()

            if "$SPX" in spx_data:
                spx_price = spx_data["$SPX"]["quote"]["lastPrice"]
                self.logger.info(f"  SPX price: ${spx_price:.2f}")
                return spx_price
            else:
                self.logger.warning("  ⚠️  Could not get SPX price, using default")
                return 6000.0

        except Exception as e:
            self.logger.warning(f"  ⚠️  Error getting SPX price: {e}")
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

                                # Publish to Redis immediately for real-time consumers
                                if self.message_broker:
                                    # Convert quote to bar format for compatibility
                                    # Ensure timestamp is serializable
                                    ts = enriched_quote['timestamp']
                                    timestamp_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)

                                    quote_as_bar = {
                                        'timestamp': timestamp_str,
                                        'option_ticker': enriched_quote['symbol'],
                                        'underlying_ticker': 'SPX',
                                        'bid': enriched_quote.get('bid'),
                                        'ask': enriched_quote.get('ask'),
                                        'last': enriched_quote.get('last'),
                                        'high': enriched_quote.get('high'),
                                        'low': enriched_quote.get('low'),
                                        'close': enriched_quote.get('close'),
                                        'volume': enriched_quote.get('volume'),
                                        'open': enriched_quote.get('open'),
                                        'bid_size': enriched_quote.get('bid_size'),
                                        'ask_size': enriched_quote.get('ask_size'),
                                        'strike_price': enriched_quote.get('strike'),
                                        'contract_type': enriched_quote.get('contract_type'),
                                        'implied_volatility': enriched_quote.get('iv'),
                                        'delta': enriched_quote.get('delta'),
                                        'gamma': enriched_quote.get('gamma'),
                                        'theta': enriched_quote.get('theta'),
                                        'vega': enriched_quote.get('vega'),
                                        'rho': enriched_quote.get('rho'),
                                    }
                                    success = self.message_broker.publish(Topic.OPTIONS_BARS, quote_as_bar)
                                    if success:
                                        self.redis_publish_count += 1
                                    else:
                                        self.logger.warning(f"Failed to publish option quote to Redis")

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

                                # Publish to Redis immediately for real-time consumers
                                if self.message_broker:
                                    # Convert quote to bar format for compatibility
                                    # Ensure timestamp is serializable
                                    ts = quote['timestamp']
                                    timestamp_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)

                                    quote_as_bar = {
                                        'timestamp': timestamp_str,
                                        'underlying_ticker': quote['symbol'],
                                        'bid': quote.get('bid'),
                                        'ask': quote.get('ask'),
                                        'last': quote.get('last'),
                                        'high': quote.get('high'),
                                        'low': quote.get('low'),
                                        'close': quote.get('close'),
                                        'volume': quote.get('volume'),
                                        'open': quote.get('open'),
                                    }
                                    success = self.message_broker.publish(Topic.UNDERLYING_BARS, quote_as_bar)
                                    if success:
                                        self.redis_publish_count += 1
                                    else:
                                        self.logger.warning(f"Failed to publish underlying quote to Redis")

            # Check if we should flush (create 1-min bars)
            if self.aggregator.should_flush():
                self.logger.info(f"  ⏰ Options aggregator triggered flush (60s elapsed)")
                self._flush_bars()

            # Also check underlying aggregator
            if self.underlying_aggregator.should_flush():
                self.logger.info(f"  ⏰ Underlying aggregator triggered flush (60s elapsed)")
                self._flush_underlying_bars()

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)
            import traceback
            traceback.print_exc()

        # Periodic status update
        if self.message_count % 10 == 0:
            now = datetime.now()
            self.logger.info(f"  📊 [{now.strftime('%H:%M:%S')}] Messages: {self.message_count} | Redis publishes: {self.redis_publish_count} | Buffered symbols: {self.aggregator.get_buffered_symbol_count()}")

    def _flush_bars(self):
        """Flush aggregated option bars to database and publish to Redis."""
        bars = self.aggregator.flush()

        self.logger.info(f"  🔄 _flush_bars() called, got {len(bars)} bars from aggregator")

        if bars:
            try:
                # Save to TimescaleDB
                inserted = self.ts_store.bulk_insert_option_bars(bars)
                self.logger.info(f"  ✓ Inserted {inserted} option bars to TimescaleDB")

                # Publish to Redis for real-time consumers
                if self.message_broker:
                    published_count = 0
                    for bar in bars:
                        success = self.message_broker.publish(Topic.OPTIONS_BARS, bar)
                        if success:
                            published_count += 1
                    self.logger.info(f"  📤 Published {published_count}/{len(bars)} option bars to Redis topic: {Topic.OPTIONS_BARS}")
                else:
                    self.logger.warning(f"  ⚠️  No message broker available, skipping Redis publish")

            except Exception as e:
                self.logger.error(f"  ✗ Database error (options): {e}", exc_info=True)
        else:
            self.logger.info(f"  ℹ️  No bars to flush (buffer was empty)")

    def _flush_underlying_bars(self):
        """Flush aggregated underlying bars to database and publish to Redis."""
        bars = self.underlying_aggregator.flush()

        self.logger.info(f"  🔄 _flush_underlying_bars() called, got {len(bars)} bars from aggregator")

        if bars:
            try:
                # Save to TimescaleDB
                inserted = self.ts_store.bulk_insert_underlying_bars(bars)
                self.logger.info(f"  ✓ Inserted {inserted} underlying bars to TimescaleDB")

                # Publish to Redis for real-time consumers
                if self.message_broker:
                    published_count = 0
                    for bar in bars:
                        success = self.message_broker.publish(Topic.UNDERLYING_BARS, bar)
                        if success:
                            published_count += 1
                    self.logger.info(f"  📤 Published {published_count}/{len(bars)} underlying bars to Redis topic: {Topic.UNDERLYING_BARS}")
                else:
                    self.logger.warning(f"  ⚠️  No message broker available, skipping Redis publish")

            except Exception as e:
                self.logger.error(f"  ✗ Database error (underlying): {e}", exc_info=True)
        else:
            self.logger.info(f"  ℹ️  No underlying bars to flush (buffer was empty)")

    def start(self):
        """Start the streaming service."""
        self.logger.info("="*70)
        self.logger.info("SPXW OPTIONS STREAMING SERVICE")
        self.logger.info("="*70)
        self.logger.info(f"Started: {datetime.now()}")
        self.logger.info(f"DTE Range: {self.config.min_dte} - {self.config.max_dte} days")
        self.logger.info(f"Strike Range: ±{self.config.strike_range_pct*100}%")
        self.logger.info(f"Aggregate Interval: {self.config.aggregate_interval_seconds}s")
        self.logger.info("="*70)

        # Refresh token at startup
        self.logger.info("Refreshing authentication token...")
        if not self.token_manager.refresh():
            self.logger.error("❌ Failed to refresh token at startup!")
            self.logger.error("Please check your authentication credentials and token database.")
            return

        # Get contracts to stream
        contracts = self.get_spxw_contracts()

        if not contracts:
            self.logger.error("❌ No contracts found to stream!")
            return

        self.contracts_subscribed = contracts

        # Refresh enricher cache
        self.logger.info("Populating contract details cache...")
        self.enricher.refresh_contract_details("$SPX", strike_count=50)
        stats = self.enricher.get_cache_stats()
        self.logger.info(f"✓ Cached {stats['contracts_cached']} contracts for enrichment")

        # Start stream
        self.logger.info("Starting stream...")
        self.streamer.start_auto(
            self.handle_message,
            start_time=time(9, 29, 0),
            stop_time=time(16, 0, 0),
            on_days=(0, 1, 2, 3, 4),
            now_timezone=zoneinfo.ZoneInfo("America/New_York"),
            daemon=True
        )
        self.logger.info("✓ Stream started")

        # Subscribe to options
        self._subscribe_to_contracts(contracts)

        # Subscribe to underlying asset ($SPX)
        self._subscribe_to_underlying()

        self.logger.info("✅ All subscriptions active")
        self.logger.info("Streaming data... (Press Ctrl+C to stop)")

        # Main loop
        self._run_main_loop()

    def _subscribe_to_contracts(self, contracts: List[str]):
        """Subscribe to option contracts.

        Args:
            contracts: List of contract symbols
        """
        MAX_PER_SUB = self.config.max_symbols_per_subscription

        self.logger.info(f"Subscribing to {len(contracts)} contracts...")

        for i in range(0, len(contracts), MAX_PER_SUB):
            batch = contracts[i:i+MAX_PER_SUB]
            symbols_str = ",".join(batch)

            # Subscribe with all fields
            fields = "0,2,3,4,5,6,7,8,9,10,12,15,16,17,20,21,23,26,28,29,30,31,32,37,38,39"

            self.streamer.send(
                self.streamer.level_one_options(symbols_str, fields)
            )

            self.logger.info(f"  ✓ Subscribed to batch {i//MAX_PER_SUB + 1} ({len(batch)} contracts)")
            dt_time.sleep(0.5)

    def _subscribe_to_underlying(self):
        """Subscribe to underlying asset quotes ($SPX)."""
        self.logger.info("Subscribing to underlying asset ($SPX)...")

        # Subscribe to $SPX with equity level one data
        # Fields: https://developer.schwabapi.com/products/trader-api--individual/details/documentation/Market-Data
        # 0=Symbol, 2=Bid, 3=Ask, 4=Last, 8=Volume, 9=High, 10=Low, 28=Open, 50=Close
        fields = "0,2,3,4,8,9,10,28,50"

        self.streamer.send(
            self.streamer.level_one_equities("$SPX", fields)
        )

        self.logger.info("  ✓ Subscribed to $SPX equity quotes")

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

                self.logger.info(f"📊 Status Update [{now.strftime('%Y-%m-%d %H:%M:%S')}]:")
                self.logger.info(f"   Messages received: {self.message_count}")
                self.logger.info(f"   Redis publishes: {self.redis_publish_count}")
                self.logger.info(f"   Contracts streaming: {len(self.contracts_subscribed)}")
                self.logger.info(f"   Buffered option symbols: {self.aggregator.get_buffered_symbol_count()}")
                self.logger.info(f"   Buffered underlying symbols: {self.underlying_aggregator.get_buffered_symbol_count()}")
                self.logger.info(f"   Contract cache: {enricher_stats['contracts_cached']} contracts")
                self.logger.info(f"   Cache age: {enricher_stats['cache_age_minutes']:.1f} minutes")
                self.logger.info(f"   Token age: {token_age:.1f} minutes")

        except KeyboardInterrupt:
            self.logger.info("\n⚠️  Stopping service...")
            self.stop()

    def stop(self):
        """Stop the streaming service."""
        self.logger.info("Flushing remaining data...")
        self._flush_bars()
        self._flush_underlying_bars()

        self.logger.info("Stopping stream...")
        self.streamer.stop()

        self.logger.info("Closing database...")
        self.ts_store.close()

        if self.message_broker:
            self.logger.info("Closing message broker...")
            self.message_broker.close()

        self.logger.info("✅ Service stopped")
