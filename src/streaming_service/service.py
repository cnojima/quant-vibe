"""Main streaming service orchestrator."""

import json
import os
import sys
import time as dt_time
import traceback
import zoneinfo
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

import schwabdev
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.logging import setup_normalized_logging
from quant_vibe.messaging import RedisMessageBroker, Topic
from quant_vibe.models import OptionsBar, UnderlyingBar
from quant_vibe.utils import calculate_mark_price, normalize_option_ticker, now_utc, safe_decimal
from quant_vibe.utils.retry import retry_with_backoff
from streaming_service.aggregator import BarAggregator
from streaming_service.config import StreamingConfig
from streaming_service.enrich_stream_with_chain import OptionContractEnricher
from streaming_service.underlying_aggregator import UnderlyingBarAggregator

try:
    from token_service.client import (
        TokenExpiredError,
        TokenLockoutError,
        TokenNotFoundError,
        TokenServiceClient,
    )
    TOKEN_SERVICE_AVAILABLE = True
except ImportError:
    TOKEN_SERVICE_AVAILABLE = False
    TokenServiceClient = None
    TokenNotFoundError = None
    TokenExpiredError = None
    TokenLockoutError = None


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
        self.redis_publish_count = 0
        self.start_time = None
        self.last_heartbeat_time = None

        self._setup_logging()
        self._validate_dependencies()
        self._initialize_token_service()
        self._initialize_components()

    def _setup_logging(self):
        """Setup normalized logging."""
        log_level = os.getenv("STREAMING_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")).upper()
        self.logger = setup_normalized_logging(
            app_name="streaming",
            log_dir="logs/streaming",
        )

        self.logger.info("Initializing Streaming Service...")
        self.logger.info(f"  DTE Range: {self.config.min_dte} - {self.config.max_dte}")
        self.logger.info(f"  Strike Range: ±{self.config.strike_range_pct*100}%")
        self.logger.info(f"  Aggregate Interval: {self.config.aggregate_interval_seconds}s")
        self.logger.info(f"  Token Refresh: Every {self.config.token_refresh_minutes} minutes")

    def _validate_dependencies(self):
        """Validate required dependencies are available."""
        if not TOKEN_SERVICE_AVAILABLE:
            self.logger.error("  Token service client not available")
            self.logger.error("  Please ensure token_service package is installed")
            raise RuntimeError("Token service client not available")

        if not self.config.token_service_url:
            self.logger.error("  Token service URL not configured")
            self.logger.error("  Set TOKEN_SERVICE_URL environment variable")
            raise RuntimeError("Token service URL not configured")

    def _initialize_token_service(self):
        """Initialize token service client and ensure valid tokens."""
        self.logger.info(f"  Token Mode: Centralized (via {self.config.token_service_url})")

        try:
            self.token_service_client = TokenServiceClient(
                base_url=self.config.token_service_url
            )

            health = self.token_service_client.health_check()
            status = health.get("status")

            if status == "healthy":
                self.logger.info("  Token service connected - tokens valid")
            elif status == "degraded":
                # Token expired but can be refreshed - trigger refresh and wait
                self.logger.warning("  Token service degraded (token expired)")
                self.logger.info("  Triggering token refresh...")
                self._wait_for_valid_token()
            elif status == "lockout":
                # Service is locked out - manual intervention required
                self.logger.critical("  TOKEN SERVICE IS IN LOCKOUT STATE!")
                self.logger.critical("  Tokens are invalid - manual re-authentication required.")
                self.logger.critical("  Steps to recover:")
                self.logger.critical("    1. POST /token/clear-lockout")
                self.logger.critical("    2. python scripts/authorize_schwab.py")
                self.logger.critical("    3. Restart services")
                raise RuntimeError("Token service is in LOCKOUT state - manual re-authentication required")
            else:
                # unhealthy or unknown status
                self.logger.error(f"  Token service unhealthy: {health}")
                raise RuntimeError(f"Token service unhealthy: {health}")

        except RuntimeError:
            raise  # Re-raise our RuntimeErrors
        except Exception as e:
            self.logger.error(f"  Failed to connect to token service: {e}")
            raise RuntimeError(f"Failed to connect to token service: {e}")

    def _wait_for_valid_token(self, max_wait_seconds: int = 120, poll_interval: int = 5):
        """Wait for token service to have valid tokens.

        Triggers a refresh and polls until tokens are valid or timeout.

        Args:
            max_wait_seconds: Maximum time to wait for valid tokens
            poll_interval: Seconds between status checks

        Raises:
            RuntimeError: If tokens don't become valid within timeout
        """
        import time

        # Trigger a manual refresh
        try:
            self.logger.info("  Requesting token refresh from token service...")
            refresh_result = self.token_service_client.refresh_token()
            if refresh_result:
                self.logger.info("  Token refresh successful")
                return
        except Exception as e:
            self.logger.warning(f"  Token refresh request failed: {e}")

        # Poll for valid tokens
        self.logger.info(f"  Waiting for valid tokens (max {max_wait_seconds}s)...")
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            try:
                health = self.token_service_client.health_check()
                status = health.get("status")

                if status == "healthy":
                    self.logger.info("  Tokens are now valid")
                    return
                elif status == "lockout":
                    raise RuntimeError("Token service entered LOCKOUT state - manual re-authentication required")
                elif status == "unhealthy":
                    raise RuntimeError("Token service unhealthy - no tokens available")

                # Still degraded, keep waiting
                elapsed = int(time.time() - start_time)
                self.logger.info(f"  Still waiting for valid tokens... ({elapsed}s/{max_wait_seconds}s)")

            except RuntimeError:
                raise
            except Exception as e:
                self.logger.warning(f"  Error checking token status: {e}")

            time.sleep(poll_interval)

        # Timeout reached
        raise RuntimeError(
            f"Timeout waiting for valid tokens after {max_wait_seconds}s. "
            "Token service may need manual intervention."
        )

    def _initialize_components(self):
        """Initialize service components."""
        self.schwab_client = schwabdev.Client(
            os.getenv("SCHWAB_API_KEY"),
            os.getenv("SCHWAB_API_SECRET"),
            os.getenv("SCHWAB_CALLBACK_URL"),
            tokens_db=self.config.tokens_db_path,
        )
        self.streamer = schwabdev.Stream(self.schwab_client)
        self.logger.info("  Schwabdev client initialized")

        self.aggregator = BarAggregator(
            aggregate_interval_seconds=self.config.aggregate_interval_seconds
        )
        self.underlying_aggregator = UnderlyingBarAggregator(
            aggregate_interval_seconds=self.config.aggregate_interval_seconds
        )
        self.ts_store = TimescaleStore()
        self.enricher = OptionContractEnricher(self.schwab_client)

        self._initialize_redis()

        self.logger.info("  Token service client initialized")
        self.logger.info("  Bar aggregator initialized")
        self.logger.info("  Underlying bar aggregator initialized")
        self.logger.info("  TimescaleDB connected")
        self.logger.info("  Contract enricher initialized")

    def _initialize_redis(self):
        """Initialize Redis message broker if enabled."""
        self.message_broker: Optional[RedisMessageBroker] = None

        if not self.config.enable_redis:
            return

        try:
            self.message_broker = RedisMessageBroker(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
            )

            RedisMessageBroker.register_topic_model(Topic.OPTIONS_BARS, OptionsBar)
            RedisMessageBroker.register_topic_model(Topic.UNDERLYING_BARS, UnderlyingBar)

            self.logger.info("  Redis message broker connected")
            self.logger.info("  Registered Pydantic models for topics")
        except Exception as e:
            self.logger.warning(f"  Redis connection failed: {e}")
            self.logger.warning("  Continuing without Redis pub/sub")
            self.message_broker = None

    def get_spxw_contracts(self) -> List[str]:
        """Get list of SPXW option contracts to stream.

        Returns:
            List of option symbols
        """
        self.logger.info(f"Fetching SPXW contracts (DTE: {self.config.min_dte}-{self.config.max_dte}, Strike range: ±{self.config.strike_range_pct*100}%)...")

        spx_price = self._get_spx_price()
        strike_min = spx_price * (1 - self.config.strike_range_pct)
        strike_max = spx_price * (1 + self.config.strike_range_pct)
        self.logger.info(f"  Strike range: ${strike_min:.0f} - ${strike_max:.0f}")

        contracts = []

        try:
            response = self.schwab_client.option_chains("$SPX", strikeCount=50)

            if response.status_code != 200:
                self.logger.error(f"  API Error: HTTP {response.status_code}")
                self.logger.error(f"  Response: {response.text[:500]}")
                return []

            try:
                chain_data = response.json()
            except Exception as json_err:
                self.logger.error(f"  JSON Parse Error: {json_err}")
                self.logger.error(f"  Response status: {response.status_code}")
                self.logger.error(f"  Response text: {response.text[:500]}")
                return []

            contracts = self._extract_contracts_from_chain(
                chain_data, strike_min, strike_max
            )

            self.logger.info(f"  Found {len(contracts)} SPXW contracts")
            self._log_sample_contracts(contracts)

        except Exception as e:
            self.logger.error(f"  Error fetching contracts: {e}", exc_info=True)
            traceback.print_exc()

        return contracts

    def _extract_contracts_from_chain(
        self, chain_data: Dict, strike_min: float, strike_max: float
    ) -> List[str]:
        """Extract SPXW contracts from chain data within strike range.

        Args:
            chain_data: Option chain data from API
            strike_min: Minimum strike price
            strike_max: Maximum strike price

        Returns:
            List of contract symbols
        """
        contracts = []
        today = now_utc().date()

        for option_type in ['callExpDateMap', 'putExpDateMap']:
            if option_type not in chain_data:
                continue

            exp_map = chain_data[option_type]

            for exp_date_str, strikes in exp_map.items():
                exp_date = datetime.strptime(exp_date_str.split(':')[0], '%Y-%m-%d').date()
                dte = (exp_date - today).days

                if dte < self.config.min_dte or dte > self.config.max_dte:
                    continue

                for strike_str, contract_list in strikes.items():
                    strike = float(strike_str)

                    if strike < strike_min or strike > strike_max:
                        continue

                    for contract in contract_list:
                        symbol = contract.get('symbol', '')
                        if 'SPXW' in symbol:
                            contracts.append(symbol)

        return contracts

    def _log_sample_contracts(self, contracts: List[str]):
        """Log sample of contracts found.

        Args:
            contracts: List of contract symbols
        """
        if not contracts:
            return

        self.logger.info("  Sample contracts:")
        for contract in contracts[:5]:
            self.logger.info(f"    {contract}")
        if len(contracts) > 5:
            self.logger.info(f"    ... and {len(contracts) - 5} more")

    @retry_with_backoff(max_retries=3, backoff_base=2.0, exceptions=(Exception,))
    def _get_spx_price(self) -> float:
        """Get current SPX price with retry logic.

        Returns:
            SPX price (or default 6000.0 if fetch fails)
        """
        try:
            response = self.schwab_client.quote("$SPX")

            if response.status_code != 200:
                self.logger.warning(f"  SPX quote API error: HTTP {response.status_code}")
                self.logger.warning(f"  Response: {response.text[:200]}")
                return 6000.0

            spx_data = response.json()

            if "$SPX" in spx_data:
                spx_price = spx_data["$SPX"]["quote"]["lastPrice"]
                self.logger.info(f"  SPX price: ${spx_price:.2f}")
                return spx_price

            self.logger.warning("  Could not get SPX price, using default")
            return 6000.0

        except Exception as e:
            self.logger.warning(f"  Error getting SPX price: {e}")
            return 6000.0

    def handle_message(self, message: str):
        """Handle incoming stream message.

        Args:
            message: JSON string from stream
        """
        self.message_count += 1

        try:
            msg_data = json.loads(message) if isinstance(message, str) else message

            if isinstance(msg_data, dict) and 'data' in msg_data:
                for data_item in msg_data['data']:
                    service = data_item.get('service', '')
                    content = data_item.get('content', [])

                    if service == 'LEVELONE_OPTIONS' and content:
                        self._process_options_data(content)
                    elif service == 'ACCT_ACTIVITY' and content:
                        self._process_account_activity(content)
                    elif service == 'LEVELONE_EQUITIES' and content:
                        self._process_underlying_data(content)

            if self.aggregator.should_flush():
                self._flush_bars()

            if self.underlying_aggregator.should_flush():
                self._flush_underlying_bars()

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)
            traceback.print_exc()

        if self.message_count % 10 == 0:
            self._log_periodic_status()

    def _process_options_data(self, content: List[Dict]):
        """Process level one options data.

        Args:
            content: List of option data items
        """
        timestamp = now_utc()

        for item in content:
            symbol = item.get('key', '')
            if not symbol:
                continue

            quote = self._create_options_quote(item, timestamp, symbol)
            enriched_quote = self.enricher.enrich_quote(quote)
            self.aggregator.add_quote(enriched_quote)

            if self.message_broker:
                self._publish_options_bar(enriched_quote, timestamp)

    def _create_options_quote(self, item: Dict, timestamp: datetime, symbol: str) -> Dict:
        """Create options quote from streaming data.

        Args:
            item: Raw streaming data item
            timestamp: Current timestamp
            symbol: Option symbol

        Returns:
            Quote dictionary
        """
        return {
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

    def _publish_options_bar(self, quote: Dict, timestamp: datetime):
        """Publish options bar to Redis.

        Args:
            quote: Enriched quote dictionary
            timestamp: Bar timestamp
        """
        exp_date = self._parse_expiration_date(quote, quote['symbol'])
        contract_type = self._parse_contract_type(quote)
        strike_price = quote.get('strike')

        if strike_price is None:
            return

        normalized_symbol = normalize_option_ticker(quote['symbol'])

        bid = quote.get('bid')
        ask = quote.get('ask')
        mark = calculate_mark_price(bid, ask)

        current_price = self._determine_current_price(quote, mark, bid, ask)
        if current_price is None:
            return

        current_price_decimal = Decimal(str(current_price))

        try:
            options_bar = OptionsBar(
                timestamp=timestamp,
                option_ticker=normalized_symbol,
                underlying_ticker='SPX',
                strike_price=Decimal(str(strike_price)),
                contract_type=contract_type,
                expiration_date=exp_date,
                open=safe_decimal(quote.get('open'), current_price_decimal),
                high=safe_decimal(quote.get('high'), current_price_decimal),
                low=safe_decimal(quote.get('low'), current_price_decimal),
                close=safe_decimal(quote.get('close'), current_price_decimal),
                volume=quote.get('volume') or 0,
                bid=safe_decimal(bid),
                ask=safe_decimal(ask),
                mark=safe_decimal(mark),
                bid_size=quote.get('bid_size'),
                ask_size=quote.get('ask_size'),
                implied_volatility=safe_decimal(quote.get('iv')),
                delta=safe_decimal(quote.get('delta')),
                gamma=safe_decimal(quote.get('gamma')),
                theta=safe_decimal(quote.get('theta')),
                vega=safe_decimal(quote.get('vega')),
                rho=safe_decimal(quote.get('rho')),
                data_source='schwabdev_stream',
            )
            if self.message_broker.publish(Topic.OPTIONS_BARS, options_bar):
                self.redis_publish_count += 1
        except Exception as model_err:
            self.logger.warning(f"Failed to create OptionsBar model: {model_err}")

    def _determine_current_price(self, quote: Dict, mark: float, bid: float, ask: float) -> Optional[float]:
        """Determine current price from available data.

        Args:
            quote: Quote dictionary
            mark: Calculated mark price
            bid: Bid price
            ask: Ask price

        Returns:
            Current price or None
        """
        current_price = quote.get('last')
        if current_price is None:
            current_price = mark
        if current_price is None:
            current_price = quote.get('close')
        if current_price is None:
            current_price = bid or ask
        return current_price

    def _process_account_activity(self, content: List[Dict]):
        """Process account activity messages.

        Args:
            content: List of account activity items
        """
        if not self.message_broker:
            return

        timestamp = now_utc()

        for item in content:
            account = item.get('0', '')
            if not account:
                continue

            activity_msg = {
                'timestamp': timestamp,
                'account': account,
                'message_type': item.get('1', ''),
                'message_data': item.get('2', ''),
                'activity_timestamp': item.get('3', ''),
            }

            try:
                if self.message_broker.publish(Topic.ACCOUNT_ACTIVITY, activity_msg):
                    self.redis_publish_count += 1
                    self.logger.info(f"  Account activity: {activity_msg['message_type']} for account {account[:8]}...")
            except Exception as pub_err:
                self.logger.warning(f"Failed to publish account activity: {pub_err}")

    def _process_underlying_data(self, content: List[Dict]):
        """Process underlying asset quotes.

        Args:
            content: List of underlying quote items
        """
        timestamp = now_utc()

        for item in content:
            symbol = item.get('key', '')
            if not symbol:
                continue

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

            self.underlying_aggregator.add_quote(quote)

            if self.message_broker:
                self._publish_underlying_bar(quote, timestamp)

    def _publish_underlying_bar(self, quote: Dict, timestamp: datetime):
        """Publish underlying bar to Redis.

        Args:
            quote: Quote dictionary
            timestamp: Bar timestamp
        """
        normalized_symbol = quote['symbol'].replace('$', '').replace('.X', '')

        last = quote.get('last')
        if last is None:
            last = calculate_mark_price(quote.get('bid'), quote.get('ask'))
        if last is None:
            last = quote.get('bid') or quote.get('ask')

        if last is None:
            return

        try:
            underlying_bar = UnderlyingBar(
                timestamp=timestamp,
                ticker=normalized_symbol,
                open=safe_decimal(quote.get('open'), last),
                high=safe_decimal(quote.get('high'), last),
                low=safe_decimal(quote.get('low'), last),
                close=safe_decimal(quote.get('close'), last),
                volume=quote.get('volume') or 0,
                data_source='schwabdev_stream',
            )
            if self.message_broker.publish(Topic.UNDERLYING_BARS, underlying_bar):
                self.redis_publish_count += 1
        except Exception as model_err:
            self.logger.warning(f"Failed to create UnderlyingBar model: {model_err}")

    def _parse_expiration_date(self, quote: Dict, symbol: str) -> Optional[datetime]:
        """Parse expiration date from quote or symbol.

        Args:
            quote: Quote dictionary
            symbol: Option symbol

        Returns:
            Expiration date or None
        """
        try:
            exp_year = quote.get('exp_year')
            exp_month = quote.get('exp_month')
            exp_day = quote.get('exp_day')

            if exp_year and exp_month and exp_day:
                return datetime(int(exp_year), int(exp_month), int(exp_day)).date()
        except (ValueError, TypeError):
            pass

        from quant_vibe.utils import parse_expiration_from_ticker
        return parse_expiration_from_ticker(symbol)

    def _parse_contract_type(self, quote: Dict) -> str:
        """Parse contract type from quote.

        Args:
            quote: Quote dictionary

        Returns:
            'call' or 'put'
        """
        contract_type_raw = quote.get('contract_type')
        if contract_type_raw:
            return 'call' if str(contract_type_raw).upper().startswith('C') else 'put'
        return 'put'

    def _log_periodic_status(self):
        """Log periodic status update."""
        now = now_utc()
        self.logger.info(f"  [{now.strftime('%H:%M:%S')}] Messages: {self.message_count} | Redis publishes: {self.redis_publish_count} | Buffered symbols: {self.aggregator.get_buffered_symbol_count()}")

    def _flush_bars(self):
        """Flush aggregated option bars to database and publish to Redis."""
        bars = self.aggregator.flush()

        if not bars:
            return

        try:
            inserted = self.ts_store.bulk_insert_option_bars(bars)
            self.logger.info(f"  Inserted {inserted} option bars")

            if self.message_broker:
                for bar in bars:
                    self.message_broker.publish(Topic.OPTIONS_BARS, bar)

        except Exception as e:
            self.logger.error(f"  Database error (options): {e}", exc_info=True)

    def _flush_underlying_bars(self):
        """Flush aggregated underlying bars to database and publish to Redis."""
        bars = self.underlying_aggregator.flush()

        if not bars:
            return

        try:
            inserted = self.ts_store.bulk_insert_underlying_bars(bars)
            self.logger.info(f"  Inserted {inserted} underlying bars")

            if self.message_broker:
                for bar in bars:
                    self.message_broker.publish(Topic.UNDERLYING_BARS, bar)

        except Exception as e:
            self.logger.error(f"  Database error (underlying): {e}", exc_info=True)

    def _publish_heartbeat(self):
        """Publish heartbeat to Redis."""
        if not self.message_broker:
            return

        try:
            uptime_seconds = 0
            if self.start_time:
                uptime_seconds = (now_utc() - self.start_time).total_seconds()

            status = "healthy"
            last_error = None

            if self.last_heartbeat_time:
                time_since_heartbeat = (now_utc() - self.last_heartbeat_time).total_seconds()
                if time_since_heartbeat > 120:
                    status = "degraded"
                    last_error = f"No heartbeat for {time_since_heartbeat:.0f}s"

            self.message_broker.publish(
                "heartbeat.streaming",
                {
                    "service": "streaming",
                    "timestamp": now_utc().isoformat(),
                    "status": status,
                    "metrics": {
                        "uptime_seconds": round(uptime_seconds, 1),
                        "messages_processed": self.message_count,
                        "redis_publishes": self.redis_publish_count,
                        "contracts_subscribed": len(self.contracts_subscribed),
                        "last_error": last_error,
                    },
                },
            )

            self.last_heartbeat_time = now_utc()
            self.logger.debug(f"Heartbeat published (status: {status})")

        except Exception as e:
            self.logger.error(f"Failed to publish heartbeat: {e}", exc_info=True)

    def start(self):
        """Start the streaming service."""
        self.start_time = now_utc()
        self.last_heartbeat_time = now_utc()

        self._log_startup_info()

        if not self._verify_token():
            return

        contracts = self.get_spxw_contracts()
        if not contracts:
            self.logger.error("No contracts found to stream!")
            return

        self.contracts_subscribed = contracts
        self._setup_enricher()
        self._start_stream()
        self._subscribe_all(contracts)
        self._run_main_loop()

    def _log_startup_info(self):
        """Log service startup information."""
        self.logger.info("="*70)
        self.logger.info("SPXW OPTIONS STREAMING SERVICE")
        self.logger.info("="*70)
        self.logger.info(f"Started: {now_utc()}")
        self.logger.info(f"DTE Range: {self.config.min_dte} - {self.config.max_dte} days")
        self.logger.info(f"Strike Range: ±{self.config.strike_range_pct*100}%")
        self.logger.info(f"Aggregate Interval: {self.config.aggregate_interval_seconds}s")
        self.logger.info("="*70)

    def _verify_token(self) -> bool:
        """Verify token availability and lockout status.

        Returns:
            True if token is available and service is not locked out, False otherwise
        """
        self.logger.info("Verifying authentication token...")

        try:
            # Check lockout status first
            if self.token_service_client.is_locked_out():
                self.logger.critical("TOKEN SERVICE IS IN LOCKOUT STATE!")
                self.logger.critical("Tokens are invalid - manual re-authentication required.")
                self.logger.critical("Steps to recover:")
                self.logger.critical("  1. Clear lockout: POST /token/clear-lockout")
                self.logger.critical("  2. Re-authenticate: python scripts/authorize_schwab.py")
                self.logger.critical("  3. Restart services")
                return False

            status = self.token_service_client.get_token_status()
            if status.get("has_token"):
                self.logger.info("Token service has valid token")
                return True

            self.logger.error("Token service has no token!")
            self.logger.error("Please authenticate using: python scripts/schwab_auth.py")
            self.logger.error("Then restart the token service: docker-compose restart token_service")
            return False

        except TokenLockoutError as e:
            self.logger.critical(f"Token service lockout detected: {e}")
            return False

        except Exception as e:
            self.logger.error(f"Failed to check token service status: {e}")
            self.logger.error("Please ensure token service is running: docker-compose up -d token_service")
            return False

    def _setup_enricher(self):
        """Setup contract enricher cache."""
        self.logger.info("Populating contract details cache...")
        self.enricher.refresh_contract_details("$SPX", strike_count=50)
        stats = self.enricher.get_cache_stats()
        self.logger.info(f"Cached {stats['contracts_cached']} contracts for enrichment")

    def _start_stream(self):
        """Start the streaming connection."""
        self.logger.info("Starting stream...")
        self.streamer.start_auto(
            self.handle_message,
            start_time=time(9, 29, 0),
            stop_time=time(16, 0, 0),
            on_days=(0, 1, 2, 3, 4),
            now_timezone=zoneinfo.ZoneInfo("America/New_York"),
            daemon=True
        )
        self.logger.info("Stream started")

    def _subscribe_all(self, contracts: List[str]):
        """Subscribe to all data streams.

        Args:
            contracts: List of option contracts to subscribe to
        """
        self._subscribe_to_contracts(contracts)
        self._subscribe_to_underlying()
        self._subscribe_to_account_activity()
        self.logger.info("All subscriptions active")
        self.logger.info("Streaming data... (Press Ctrl+C to stop)")

    def _subscribe_to_contracts(self, contracts: List[str]):
        """Subscribe to option contracts.

        Args:
            contracts: List of contract symbols
        """
        MAX_PER_SUB = self.config.max_symbols_per_subscription
        self.logger.info(f"Subscribing to {len(contracts)} contracts...")

        fields = "0,2,3,4,5,6,7,8,9,10,12,15,16,17,20,21,23,26,28,29,30,31,32,37,38,39"

        for i in range(0, len(contracts), MAX_PER_SUB):
            batch = contracts[i:i+MAX_PER_SUB]
            symbols_str = ",".join(batch)

            self.streamer.send(
                self.streamer.level_one_options(symbols_str, fields)
            )

            self.logger.info(f"  Subscribed to batch {i//MAX_PER_SUB + 1} ({len(batch)} contracts)")
            dt_time.sleep(0.5)

    def _subscribe_to_underlying(self):
        """Subscribe to underlying asset quotes ($SPX)."""
        self.logger.info("Subscribing to underlying asset ($SPX)...")

        fields = "0,2,3,4,8,9,10,28,50"
        self.streamer.send(
            self.streamer.level_one_equities("$SPX", fields)
        )

        self.logger.info("  Subscribed to $SPX equity quotes")

    def _subscribe_to_account_activity(self):
        """Subscribe to account activity updates."""
        self.logger.info("Subscribing to account activity...")

        self.streamer.send(
            self.streamer.account_activity()
        )

        self.logger.info("  Subscribed to account activity")

    def _run_main_loop(self):
        """Run main service loop."""
        try:
            heartbeat_counter = 0

            while True:
                dt_time.sleep(30)
                heartbeat_counter += 1

                self._publish_heartbeat()

                if heartbeat_counter % 2 == 0:
                    self._log_status_update()

        except KeyboardInterrupt:
            self.logger.info("\nStopping service...")
            self.stop()

    def _log_status_update(self):
        """Log periodic status update."""
        token_age = self._get_token_age()
        enricher_stats = self.enricher.get_cache_stats()
        now = now_utc()

        self.logger.info(f"Status Update [{now.strftime('%Y-%m-%d %H:%M:%S')}]:")
        self.logger.info(f"   Messages received: {self.message_count}")
        self.logger.info(f"   Redis publishes: {self.redis_publish_count}")
        self.logger.info(f"   Contracts streaming: {len(self.contracts_subscribed)}")
        self.logger.info(f"   Buffered option symbols: {self.aggregator.get_buffered_symbol_count()}")
        self.logger.info(f"   Buffered underlying symbols: {self.underlying_aggregator.get_buffered_symbol_count()}")
        self.logger.info(f"   Contract cache: {enricher_stats['contracts_cached']} contracts")
        self.logger.info(f"   Cache age: {enricher_stats['cache_age_minutes']:.1f} minutes")
        self.logger.info(f"   Token age: {token_age:.1f} minutes")

    def _get_token_age(self) -> float:
        """Get token age in minutes.

        Returns:
            Token age in minutes
        """
        try:
            status = self.token_service_client.get_token_status()
            if status.get("has_token"):
                return status.get("access_token_age_seconds", 0) / 60.0
        except Exception as e:
            self.logger.warning(f"Failed to get token status from service: {e}")
        return 0.0

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

        self.logger.info("Service stopped")