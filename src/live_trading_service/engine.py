"""Live Trading Engine - Core orchestrator for real-time options trading.

The LiveTradingEngine coordinates all components:
- Data feed consumption
- Strategy execution
- Order management
- Position tracking
- Risk management
- State persistence
"""

import os
import time
from datetime import datetime
from typing import Dict, List, Optional
import signal
import yaml
from pathlib import Path

import schwabdev
from dotenv import load_dotenv

from live_trading_service.redis_data_feed import RedisDataFeed
from live_trading_service.state_store import StateStore
from live_trading_service.order_manager import OrderManager
from live_trading_service.position_manager import PositionManager
from live_trading_service.strategy_executor import StrategyExecutor
from live_trading_service.strategy_loader import StrategyLoader
from live_trading_service.utils import (
    TradingState, EventType,
    is_market_open
)
from quant_vibe.logging import setup_normalized_logging
from quant_vibe.data import LiveMarketDataProvider
from quant_vibe.logging.unified_logging import get_logger
from quant_vibe.messaging import RedisMessageBroker
from quant_vibe.notifications import TradingNotifier
from quant_vibe.utils import now_utc

# Import token service client
try:
    from token_service.client import TokenServiceClient
    TOKEN_SERVICE_AVAILABLE = True
except ImportError:
    TOKEN_SERVICE_AVAILABLE = False
    TokenServiceClient = None

load_dotenv()


class LiveTradingEngine:
    """
    Main trading engine for live options trading.

    Coordinates data streaming, strategy execution, order management,
    position tracking, and risk management.
    """

    def __init__(
        self,
        trading_mode: str,
        config_path: str = "config/live_trading_paper.yaml"
    ):
        """
        Initialize live trading engine.

        Args:
            trading_mode: Trading mode ('real' or 'paper')
            config_path: Path to configuration file
        """
        # Validate trading mode
        if trading_mode not in ['real', 'paper']:
            raise ValueError(f"trading_mode must be 'real' or 'paper', got: {trading_mode}")

        self.trading_mode = trading_mode

        # Load configuration
        self.config = self._load_config(config_path)

        # Setup logging with file output (important for multiprocessing)
        from quant_vibe.logging import setup_normalized_logging
        self.logger = setup_normalized_logging(
            app_name=f'live_trading_{self.trading_mode}',
            log_dir=f'logs/live_trading',
            console_output=True,
            capture_submodules=True
        )
        self.logger.info("="*70)
        self.logger.info("Initializing Live Trading Engine {} Mode".format(self.trading_mode.upper()))
        self.logger.info("="*70)

        # State
        self.state = TradingState.STOPPED

        # Validate config matches trading mode
        config_paper = self.config['engine'].get('paper_trading', True)
        if (self.trading_mode == 'real' and config_paper) or \
           (self.trading_mode == 'paper' and not config_paper):
            self.logger.warning(f"⚠️  Config mismatch: trading_mode={self.trading_mode} but paper_trading={config_paper}")
            self.logger.warning(f"⚠️  Using trading_mode={self.trading_mode} (ignoring config)")

        # Set paper_trading flag for backward compatibility
        self.paper_trading = (self.trading_mode == 'paper')

        self.use_token_service = self.config['engine'].get('use_token_service', True)
        self.token_service_url = os.getenv("TOKEN_SERVICE_URL")

        # Initialize components
        self.redis_feed: Optional[RedisDataFeed] = None
        self.market_data: Optional[LiveMarketDataProvider] = None
        self.state_store: Optional[StateStore] = None
        self.token_service_client: Optional[TokenServiceClient] = None
        self.schwab_client: Optional[schwabdev.Client] = None
        self.streamer: Optional[schwabdev.Stream] = None
        self.order_manager: Optional[OrderManager] = None
        self.position_manager: Optional[PositionManager] = None
        self.strategy_executor: Optional[StrategyExecutor] = None
        self.message_broker: Optional[RedisMessageBroker] = None
        self.notifier: Optional[TradingNotifier] = None

        # Strategies (loaded from config)
        self.strategies: List = []

        # Statistics
        self.start_time: Optional[datetime] = None
        self.last_heartbeat_time: Optional[datetime] = None
        self.total_bars_processed = 0
        self.total_signals_generated = 0

        # Shutdown handling
        self._shutdown_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        mode_emoji = '💵' if self.trading_mode == 'real' else '📝'
        self.logger.info(f"{mode_emoji} Trading Mode: {self.trading_mode.upper()}")
        self.logger.info(f"📊 Database Schema: {self.trading_mode}_trading")
        self.logger.info(f"📄 Configuration: {config_path}")

        if self.trading_mode == 'real':
            self.logger.warning("⚠️  REAL MONEY TRADING - TRADES WILL EXECUTE WITH REAL FUNDS")
        else:
            self.logger.info("ℹ️  Paper Trading - Simulated fills, no real orders")

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file."""
        config_file = Path(config_path)

        if not config_file.exists():
            # Create default config
            default_config = self._get_default_config()

            # Save default config
            config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(config_file, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)

            print(f"Created default configuration at: {config_path}")
            return default_config

        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        return config

    def _get_default_config(self) -> Dict:
        """Get default configuration."""
        return {
            'engine': {
                'paper_trading': True,  # CRITICAL: Start with paper trading
                'max_positions': 25,
                'max_capital_per_trade': 10000,
                'daily_loss_limit_pct': 0.05,  # 5%
                'data_stale_timeout_seconds': 300,  # 5 minutes
            },
            'strategies': {
                'enabled': []  # Will be populated later
            },
            'data_feed': {
                'window_size': 100,  # Keep last 100 bars
                'aggregate_interval_seconds': 60,  # 1-minute bars
                'max_dte': 45,
                'min_dte': 0,
                'strike_range_pct': 0.10,  # ±10%
            },
            'redis': {
                'host': None,  # Defaults to env var
                'port': None,  # Defaults to env var
                'db': None,    # Defaults to env var
            },
            'risk': {
                'max_total_exposure': 100000,
                'max_drawdown_pct': 0.10,  # 10%
                'position_concentration_limit': 0.30,  # 30% max in single position
            },
            'monitoring': {
                'status_update_interval_seconds': 60,
                'health_check_interval_seconds': 30,
            },
            'logging': {
                'log_dir': 'logs/live_trading',
                'log_level': 'INFO',
            }
        }

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self.logger.warning(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_requested = True

    def get_data_feed_mode(self) -> str:
        """Get the current data feed mode."""
        return self.config.get('data_feed', {}).get('mode', 'live')

    def _load_mode_state(self):
        """Load existing state for current trading mode."""
        self.logger.info(f"  - Loading state for {self.trading_mode.upper()} mode...")

        # Get account balance if available
        balance = self.state_store.get_account_balance()
        if balance:
            self.logger.info(f"    💰 Cash: ${balance.get('cash_balance', 0):,.2f}")
            self.logger.info(f"    📈 Portfolio Value: ${balance.get('portfolio_value', 0):,.2f}")
            self.logger.info(f"    📊 Total P&L: ${balance.get('total_pnl', 0):,.2f}")
            if balance.get('win_rate'):
                win_rate = balance.get('win_rate', 0) * 100
                self.logger.info(f"    🎯 Win Rate: {win_rate:.1f}%")
        else:
            self.logger.info(f"    ℹ️  No existing balance found (will be initialized)")

        # Get open positions
        positions = self.state_store.get_open_positions()
        self.logger.info(f"    📍 Open Positions: {len(positions)}")
        if positions:
            for pos in positions[:3]:  # Show first 3
                self.logger.info(f"       - {pos['position_id']}: {pos['strategy_name']}")
            if len(positions) > 3:
                self.logger.info(f"       ... and {len(positions) - 3} more")

        # Get strategy states
        try:
            strategies = self.state_store.get_all_strategy_states()
            self.logger.info(f"    ⚙️  Strategy States: {len(strategies)}")
        except Exception as e:
            self.logger.debug(f"    Could not load strategy states: {e}")

    def initialize(self):
        """Initialize all components."""
        self.logger.info("Initializing components...")

        # Initialize message broker for heartbeats and control messages
        self.logger.info("  - Initializing message broker...")
        try:
            redis_config = self.config.get('redis', {})
            self.message_broker = RedisMessageBroker(
                host=redis_config.get('host'),
                port=redis_config.get('port'),
                db=redis_config.get('db'),
            )
            self.logger.info("    ✓ Message broker ready (for heartbeats and control)")
        except Exception as e:
            self.logger.warning(f"    ⚠️  Failed to initialize message broker: {e}")
            self.logger.warning("    Heartbeats and control messages will be disabled")
            self.message_broker = None

        # Initialize state store with trading mode
        self.logger.info("  - Initializing state store...")
        self.state_store = StateStore(trading_mode=self.trading_mode)
        self.logger.info("    ✓ State store ready")

        # Load existing state for this trading mode
        self._load_mode_state()

        # Initialize data feed (Redis)
        self.logger.info("  - Initializing Redis data feed...")
        redis_config = self.config.get('redis', {})
        data_feed_mode = self.get_data_feed_mode()
        self.redis_feed = RedisDataFeed(
            window_size=self.config['data_feed']['window_size'],
            callbacks=[self._on_new_bars],
            redis_host=redis_config.get('host'),
            redis_port=redis_config.get('port'),
            redis_db=redis_config.get('db'),
            mode=data_feed_mode,
        )
        self.logger.info("    ✓ Redis data feed ready")
        if data_feed_mode == "replay":
            self.logger.info("    ℹ️  Using REPLAY mode for market data (replay service)")
        else:
            self.logger.info("    ℹ️  Using LIVE mode for market data (streaming service)")

        # Initialize market data provider (wraps data feed)
        self.logger.info("  - Initializing market data provider...")
        feed = self.redis_feed
        self.market_data = LiveMarketDataProvider(feed)
        self.logger.info("    ✓ Market data provider ready")

        # Initialize Schwab client for real trading (needed for order execution)
        # Paper trading doesn't need Schwab client (simulated fills)
        if self.trading_mode == 'real':
            self.logger.info("  - Initializing Schwab client for REAL trading...")

            # Initialize token service client if enabled
            if self.use_token_service and TOKEN_SERVICE_AVAILABLE and self.token_service_url:
                self.logger.info(f"    - Connecting to token service ({self.token_service_url})...")
                try:
                    self.token_service_client = TokenServiceClient(
                        base_url=self.token_service_url,
                        logger=self.logger
                    )
                    health = self.token_service_client.health_check()
                    if health.get("status") == "healthy":
                        self.logger.info("      ✓ Token service connected")
                    else:
                        self.logger.warning(f"      ⚠️ Token service unhealthy: {health}")
                        self.logger.warning("      Falling back to local token management")
                        self.token_service_client = None
                except Exception as e:
                    self.logger.warning(f"      ⚠️ Failed to connect to token service: {e}")
                    self.logger.warning("      Falling back to local token management")
                    self.token_service_client = None

            # Initialize Schwab client (required for real trading)
            tokens_db = "tokens/schwabdev_tokens.db"
            self.schwab_client = schwabdev.Client(
                os.getenv("SCHWAB_API_KEY"),
                os.getenv("SCHWAB_API_SECRET"),
                os.getenv("SCHWAB_CALLBACK_URL"),
                tokens_db=tokens_db,
            )

            if self.token_service_client:
                self.logger.info("    ✓ Schwab client ready (tokens via token service)")
            else:
                self.logger.info("    ✓ Schwab client ready (tokens via local database)")
        else:
            # Paper trading - no Schwab client needed
            self.logger.info("  - Schwab client: Not needed for paper trading (simulated fills)")
            self.schwab_client = None
            self.token_service_client = None

        # Initialize OrderManager
        self.logger.info("  - Initializing OrderManager...")
        oco_config = self.config.get('oco', {})
        broker_config = self.config.get('broker', {})
        account_hash = broker_config.get('account_hash')
        account_index = broker_config.get('account_index', 0)

        self.order_manager = OrderManager(
            schwab_client=self.schwab_client,
            state_store=self.state_store,
            paper_trading=self.paper_trading,
            use_oco=oco_config.get('enabled', False),
            oco_config=oco_config,
            account_hash=account_hash,
            account_index=account_index,
        )

        if account_hash:
            self.logger.info(f"    ✓ OrderManager ready (account_hash={account_hash[:8]}...)")
        else:
            self.logger.info(f"    ✓ OrderManager ready (account_index={account_index})")

        # Initialize PositionManager
        self.logger.info("  - Initializing PositionManager...")
        self.position_manager = PositionManager(
            state_store=self.state_store
        )
        self.logger.info("    ✓ PositionManager ready")

        # Load strategies
        self.logger.info("  - Loading strategies...")
        self._load_strategies()
        self.logger.info(f"    ✓ Loaded {len(self.strategies)} strategies")

        # Initialize TradingNotifier (Pushover) - MUST be before StrategyExecutor
        self.logger.info("  - Initializing notification system...")
        try:
            notification_config = self.config.get('notifications', {})
            self.notifier = TradingNotifier(
                config=notification_config
            )
            # Validate credentials if enabled
            if self.notifier.pushover.enabled:
                if self.notifier.validate():
                    self.logger.info("    ✓ Pushover notifications enabled and validated")
                else:
                    self.logger.warning("    ⚠️  Pushover validation failed - check credentials in .env")
            else:
                self.logger.info("    ℹ️  Pushover notifications disabled")
        except Exception as e:
            self.logger.warning(f"    ⚠️  Failed to initialize notifier: {e}")
            self.logger.warning("    Notifications will be disabled")
            self.notifier = None

        # Initialize StrategyExecutor
        self.logger.info("  - Initializing StrategyExecutor...")
        self.strategy_executor = StrategyExecutor(
            strategies=self.strategies,
            order_manager=self.order_manager,
            position_manager=self.position_manager,
            state_store=self.state_store,
            underlying_ticker="SPX",
            enabled=True,
            notifier=self.notifier,
        )
        self.logger.info("    ✓ StrategyExecutor ready")

        # Save initial state
        self.state_store.save_engine_state(
            self.state,
            {'initialized': True, 'paper_trading': self.paper_trading}
        )

        self.logger.info("✅ All components initialized")

    def _load_strategies(self):
        """Load and initialize strategies from configuration."""
        # Use StrategyLoader to load strategies from config
        self.strategies = StrategyLoader.load_strategies(self.config)

        for strategy in self.strategies:
            self.logger.info(f"    Loaded strategy: {strategy.name}")

    def _reconcile_with_broker(self, account_hash: Optional[str] = None):
        """
        Reconcile internal positions with Schwab broker.
        Called on startup for real trading mode.

        Args:
            account_hash: Optional specific account hash to reconcile.
                         If not provided, uses the configured account.
        """
        try:
            # 1. List available accounts
            self.logger.info("Step 1: Listing Schwab accounts...")
            success, accounts, error = self.order_manager.list_available_accounts()

            if not success:
                self.logger.error(f"❌ Failed to list accounts: {error}")
                return

            if accounts:
                self.logger.info(f"📊 Found {len(accounts)} Schwab account(s):")
                for acc in accounts:
                    # Mark the account we're reconciling
                    if account_hash:
                        marker = "🎯 RECONCILING" if acc['hash_value'] == account_hash else ""
                    else:
                        marker = "✓ ACTIVE" if acc['is_current'] else ""
                    self.logger.info(
                        f"  [{acc['index']}] Account ending in ...{acc['hash_value'][-4:]} "
                        f"({acc['type']}) {marker}"
                    )
            else:
                self.logger.warning("⚠️  No Schwab accounts found")
                return

            # 2. Get broker positions (pass account_hash if provided)
            self.logger.info("\nStep 2: Fetching positions from Schwab...")
            if account_hash:
                # Temporarily override the order manager's account for this reconciliation
                success, broker_positions, error = self.order_manager.get_broker_positions_for_account(account_hash)
            else:
                success, broker_positions, error = self.order_manager.get_broker_positions()

            if not success:
                self.logger.error(f"❌ Failed to fetch broker positions: {error}")
                return

            self.logger.info(f"📊 Broker has {len(broker_positions)} open position(s)")
            if broker_positions:
                for pos in broker_positions:
                    self.logger.info(
                        f"  - {pos['symbol']}: {pos['quantity']} contracts "
                        f"@ ${pos['average_price']:.2f} (MktVal: ${pos['market_value']:.2f})"
                    )

            # 3. Get internal positions
            self.logger.info("\nStep 3: Fetching internal positions...")
            internal_positions_raw = self.position_manager.get_active_positions()
            self.logger.info(f"📊 Internal tracker has {len(internal_positions_raw)} open position(s)")

            # Transform internal positions to format expected by reconcile_positions
            internal_positions = []
            for pos in internal_positions_raw:
                quantities = {}
                if hasattr(pos, 'legs') and pos.legs:
                    for leg in pos.legs:
                        symbol = leg.contract_symbol
                        qty = leg.quantity
                        quantities[symbol] = quantities.get(symbol, 0) + qty

                internal_positions.append({
                    'position_id': pos.position_id,
                    'contract_symbols': list(quantities.keys()),
                    'quantities': quantities
                })

            # 4. Reconcile
            self.logger.info("\nStep 4: Reconciling positions...")
            # Pass the broker positions we already fetched to avoid duplicate API call
            success, report, error = self.order_manager.reconcile_positions(internal_positions, broker_positions)

            if not success:
                self.logger.error(f"❌ Reconciliation failed: {error}")
                return

            # 5. Report results
            self.logger.info("\n" + "─"*70)
            self.logger.info("RECONCILIATION RESULTS")
            self.logger.info("─"*70)
            self.logger.info(f"Timestamp: {report['timestamp']}")
            self.logger.info(f"Broker Positions: {report['broker_positions_count']}")
            self.logger.info(f"Internal Positions: {report['internal_positions_count']}")
            self.logger.info(f"Broker Contract Legs: {report['total_broker_legs']}")
            self.logger.info(f"Internal Contract Legs: {report['total_internal_legs']}")
            self.logger.info(f"Status: {report['status'].upper()}")

            if report['discrepancies']:
                self.logger.warning(f"\n⚠️  Found {report['discrepancies_count']} discrepancy(ies):")
                for disc in report['discrepancies']:
                    self.logger.warning(
                        f"  [{disc['type']}] {disc['symbol']}: "
                        f"Broker={disc['broker_quantity']}, "
                        f"Internal={disc['internal_quantity']}, "
                        f"Diff={disc['difference']:+.1f}"
                    )

                # Handle mismatch based on config
                broker_config = self.config.get('broker', {})
                on_mismatch = broker_config.get('on_mismatch', 'warn')

                if on_mismatch == 'halt':
                    self.logger.error("❌ HALTING ENGINE due to position mismatch")
                    self.state_store.log_event(
                        EventType.ENGINE_ERROR,
                        f"Engine halted due to {report['discrepancies_count']} position discrepancies",
                        severity='error',
                        details=report
                    )
                    self._shutdown_requested = True
                elif on_mismatch == 'sync':
                    self.logger.warning("🔄 Syncing internal state to match broker...")
                    self._sync_broker_positions(broker_positions, report, account_hash)
                else:  # warn (default)
                    self.logger.warning("⚠️  Continuing with warning - manual review recommended")

                # Log event
                self.state_store.log_event(
                    EventType.RECONCILIATION,
                    f"Position reconciliation found {report['discrepancies_count']} discrepancies",
                    severity='warning',
                    details=report
                )
            else:
                self.logger.info("\n✅ All positions matched! Internal state matches broker.")
                self.state_store.log_event(
                    EventType.RECONCILIATION,
                    "Position reconciliation successful - all positions matched",
                    severity='info',
                    details=report
                )

        except Exception as e:
            self.logger.error(f"❌ Reconciliation error: {str(e)}", exc_info=True)
            self.state_store.log_event(
                EventType.ENGINE_ERROR,
                f"Reconciliation failed with error: {str(e)}",
                severity='error'
            )

    def _cleanup_synthetic_positions(self):
        """
        Clean up old synthetic positions from state store.

        This removes any positions with IDs starting with SYNC_ to prevent
        accumulation of duplicate synthetic positions across reconciliations.
        """
        # Note: This method is currently not called to avoid removing valid synthetic positions
        # The _find_existing_sync_position check is sufficient to prevent duplicates
        pass

    def _find_existing_sync_position(self, symbol: str) -> Optional[Dict]:
        """
        Check if a synthetic position already exists for the given symbol.

        Args:
            symbol: The contract symbol to check

        Returns:
            The existing synthetic position if found, None otherwise
        """
        try:
            # Get all positions from state store
            positions = self.state_store.get_all_positions()

            # Look for synthetic position with matching symbol in legs
            for pos in positions:
                if pos.get('position_id', '').startswith('SYNC_'):
                    # Check if any leg has the matching symbol
                    legs = pos.get('legs', [])
                    for leg in legs:
                        if leg.get('contract_symbol') == symbol:
                            return pos

            return None

        except Exception as e:
            self.logger.error(f"Error finding existing sync position: {e}", exc_info=True)
            return None

    def _sync_broker_positions(self, broker_positions: List[Dict], reconciliation_report: Dict, account_hash: Optional[str] = None):
        """
        Sync internal state with broker positions.

        This adds missing positions from the broker to internal tracking.

        Args:
            broker_positions: List of positions from broker
            reconciliation_report: Reconciliation report with discrepancies
            account_hash: Account hash for the positions being synced
        """
        from quant_vibe.strategies.options_base import OptionsPosition, OptionLeg, OptionType, SpreadType

        try:
            # Note: We don't call _cleanup_synthetic_positions() anymore as it's too aggressive
            # The _find_existing_sync_position check is sufficient to prevent duplicates

            # Process each discrepancy
            for discrepancy in reconciliation_report.get('discrepancies', []):
                if discrepancy['type'] == 'missing_internal':
                    # Find the full broker position data
                    symbol = discrepancy['symbol']
                    broker_qty = discrepancy['broker_quantity']

                    # Check if we already have a synthetic position for this symbol
                    existing_sync_position = self._find_existing_sync_position(symbol)
                    if existing_sync_position:
                        self.logger.info(f"♻️ Synthetic position already exists for {symbol}: {existing_sync_position}")
                        continue

                    # Find the broker position details
                    broker_pos = None
                    for pos in broker_positions:
                        if pos['symbol'] == symbol:
                            broker_pos = pos
                            break

                    if not broker_pos:
                        self.logger.warning(f"Could not find broker position details for {symbol}")
                        continue

                    # Extract option details from the instrument
                    instrument = broker_pos.get('instrument', {})

                    # Parse the option symbol (format: "CRWV  260220C00090000")
                    # This is Schwab's OCC format: SYMBOL(6) YYMMDD(6) P/C(1) STRIKE(8)
                    symbol_parts = symbol.strip()
                    underlying = instrument.get('underlyingSymbol', symbol[:4].strip())
                    put_call = instrument.get('putCall', 'CALL')
                    option_type = OptionType.CALL if put_call == 'CALL' else OptionType.PUT

                    # Create a synthetic position for tracking (use symbol as base ID)
                    position_id = f"SYNC_{symbol.replace(' ', '_')}"

                    self.logger.info(f"📥 Creating synthetic position {position_id} for {symbol}")

                    # Parse strike price from symbol (last 8 digits divided by 1000)
                    # CRWV  260220C00090000 -> strike = 90.00
                    strike_str = symbol[-8:]  # "00090000"
                    strike_price = float(strike_str) / 1000.0  # 90.00

                    # Parse expiration date from symbol (YYMMDD)
                    # CRWV  260220C00090000 -> 260220 -> 2026-02-20
                    date_str = symbol[-15:-9]  # "260220"
                    from datetime import date
                    expiration_date = date(
                        2000 + int(date_str[:2]),  # Year: 26 -> 2026
                        int(date_str[2:4]),         # Month: 02
                        int(date_str[4:6])          # Day: 20
                    )

                    # Get average price (try both snake_case and camelCase)
                    avg_price = broker_pos.get('average_price', broker_pos.get('averagePrice', 0))
                    if avg_price == 0:
                        # Try to get from market value
                        market_value = broker_pos.get('market_value', broker_pos.get('marketValue', 0))
                        if market_value != 0 and broker_qty != 0:
                            avg_price = abs(market_value) / abs(broker_qty) / 100

                    # Create an OptionLeg
                    leg = OptionLeg(
                        contract_symbol=symbol,
                        quantity=int(broker_qty),  # Positive for long
                        option_type=option_type,
                        strike_price=strike_price,
                        expiration_date=expiration_date,
                        entry_price=avg_price,
                    )

                    # Get current underlying price
                    underlying_price = 0.0
                    try:
                        if self.data_feed and hasattr(self.data_feed, 'get_current_price'):
                            underlying_price = self.data_feed.get_current_price(underlying)
                        if underlying_price == 0.0:
                            # Fallback to a reasonable estimate based on strike
                            underlying_price = strike_price
                    except Exception:
                        underlying_price = strike_price  # Fallback

                    # Calculate entry cost (negative for credit, positive for debit)
                    # For single leg: entry_cost = quantity * entry_price * 100
                    entry_cost = broker_qty * avg_price * 100

                    # Create an OptionsPosition
                    position = OptionsPosition(
                        position_id=position_id,
                        spread_type=SpreadType.SINGLE,  # Single leg position
                        legs=[leg],
                        entry_time=now_utc(),
                        entry_cost=entry_cost,
                        underlying_price_at_entry=underlying_price,
                        profit_target_pct=0.5,  # Default 50% profit target
                        stop_loss=None,
                        trailing_stop=None
                    )

                    # Add to position manager
                    self.position_manager.open_positions[position_id] = position

                    # Use the account_hash passed to this function, or fall back to default
                    position_account_hash = account_hash or (self.order_manager._get_account_hash() if hasattr(self.order_manager, '_get_account_hash') else None)

                    # Create position data dict for database (includes strategy_name)
                    position_data = {
                        'position_id': position_id,
                        'strategy_name': 'broker_sync',  # Strategy name for database
                        'spread_type': 'SINGLE',
                        'entry_time': now_utc(),
                        'entry_cost': entry_cost,
                        'underlying_price_at_entry': underlying_price,
                        'status': 'open',
                        'current_value': broker_pos.get('marketValue', 0),
                        'account_hash': position_account_hash,  # Use correct account_hash
                        'legs': [{
                            'contract_symbol': leg.contract_symbol,
                            'option_type': leg.option_type.value,
                            'strike_price': leg.strike_price,
                            'expiration_date': leg.expiration_date.isoformat(),
                            'quantity': leg.quantity,
                            'entry_price': avg_price,
                            'current_price': None
                        }],
                        'metadata': {
                            'source': 'broker_reconciliation',
                            'broker_data': broker_pos
                        }
                    }

                    # Persist to database
                    self.state_store.save_position(position_data)

                    self.logger.info(
                        f"✅ Synced position {position_id}: "
                        f"{symbol} x{broker_qty} @ ${avg_price:.2f}"
                    )

                elif discrepancy['type'] == 'missing_broker':
                    # Position exists internally but not at broker - should close it
                    self.logger.warning(
                        f"⚠️  Position {discrepancy['symbol']} exists internally but not at broker. "
                        f"Consider closing with reason='broker_sync'"
                    )
                    # TODO: Implement closing phantom positions

                elif discrepancy['type'] == 'quantity_mismatch':
                    # Quantity mismatch - log for manual review
                    self.logger.warning(
                        f"⚠️  Quantity mismatch for {discrepancy['symbol']}: "
                        f"Broker={discrepancy['broker_quantity']}, "
                        f"Internal={discrepancy['internal_quantity']}"
                    )
                    # TODO: Implement quantity adjustment

            self.logger.info("🔄 Sync complete - internal state updated")

            # Log event
            self.state_store.log_event(
                EventType.RECONCILIATION,
                f"Synced {len([d for d in reconciliation_report['discrepancies'] if d['type'] == 'missing_internal'])} positions from broker",
                severity='info',
                details=reconciliation_report
            )

        except Exception as e:
            self.logger.error(f"Failed to sync broker positions: {str(e)}", exc_info=True)
            self.state_store.log_event(
                EventType.ENGINE_ERROR,
                f"Position sync failed: {str(e)}",
                severity='error'
            )

    def start(self):
        """Start the live trading engine."""
        self.logger.info("\n" + "="*70)
        self.logger.info("STARTING LIVE TRADING ENGINE")
        self.logger.info("="*70)

        self.state = TradingState.STARTING
        self.start_time = now_utc()

        # Log state
        self.state_store.log_event(
            EventType.ENGINE_STARTED,
            f"Engine started in {'PAPER' if self.paper_trading else 'LIVE'} mode",
            severity='info'
        )

        # Start control message listener (non-blocking)
        if self.message_broker:
            self.logger.info("Starting control message listener...")
            import threading
            self.control_thread = threading.Thread(
                target=self._listen_for_control_messages,
                daemon=True,
                name="ControlMessageListener"
            )
            self.control_thread.start()
            self.logger.info("✅ Control message listener started")

        # Use Redis feed - no need to subscribe to contracts
        self.logger.info("Starting Redis data feed...")
        self.redis_feed.start()
        self.logger.info("✅ Redis feed connected - receiving data from StreamingService")

        self.state = TradingState.RUNNING
        self.state_store.save_engine_state(
            self.state,
            {
                'data_source': 'redis',
                'data_feed_mode': self.get_data_feed_mode(),
            }
        )


        self.logger.info("✅ Engine is RUNNING")
        self.logger.info("="*70)

        # Perform startup reconciliation for real trading
        if not self.paper_trading:
            broker_config = self.config.get('broker', {})
            if broker_config.get('reconcile_on_startup', True):
                self.logger.info("\n" + "="*70)
                self.logger.info("PERFORMING ACCOUNT RECONCILIATION")
                self.logger.info("="*70)
                self._reconcile_with_broker()
                self.logger.info("="*70 + "\n")

        # Send start notification
        if self.notifier:
            mode = "PAPER" if self.paper_trading else "LIVE"
            strategy_names = [s.name for s in self.strategies]
            self.notifier.on_engine_start(mode=mode, strategies=strategy_names)

        # Main loop
        self._run_main_loop()



    def _subscribe_to_contracts(self, contracts: List[str]):
        """Subscribe to option contracts for streaming."""
        MAX_PER_SUB = 500
        self.logger.info(f"Subscribing to {len(contracts)} contracts...")

        for i in range(0, len(contracts), MAX_PER_SUB):
            batch = contracts[i:i+MAX_PER_SUB]
            symbols_str = ",".join(batch)

            # All fields we need
            fields = "0,2,3,4,5,6,7,8,9,10,12,15,16,17,20,21,23,26,28,29,30,31,32,35,37,38,39"

            self.streamer.send(
                self.streamer.level_one_options(symbols_str, fields)
            )

            self.logger.info(f"  ✓ Batch {i//MAX_PER_SUB + 1} ({len(batch)} contracts)")
            time.sleep(0.5)

        self.logger.info("✅ All subscriptions active")

    def _feed_is_stale(self) -> bool:
        """Check if data feed is stale."""
        if self.redis_feed:
            return self.redis_feed.is_data_stale()
        return True

    def _on_new_bars(self, new_bars: List[Dict]):
        """
        Callback when new bars are created by data feed.

        This is where strategy execution happens.

        Args:
            new_bars: List of newly created bars
        """
        self.total_bars_processed += len(new_bars)

        # self.logger.debug(f"Received {len(new_bars)} new bars")

        # Check data staleness (use correct feed reference)
        feed = self.redis_feed
        if feed.is_data_stale():
            self.logger.warning("Data is stale! Pausing new entries.")
            if self.strategy_executor:
                self.strategy_executor.disable()
            return
        else:
            if self.strategy_executor and not self.strategy_executor.enabled:
                self.logger.info("Data recovered, re-enabling strategies")
                self.strategy_executor.enable()

        # Execute strategies on new bars
        if self.strategy_executor and self.market_data and new_bars:
            # Group bars by timestamp FIRST to process each timestamp only once
            # This is critical for replay performance: instead of processing 1000 bars
            # one-by-one (calling get_*_snapshot 1000 times), we group them and
            # process each unique timestamp once (e.g., 100 unique timestamps)
            from collections import defaultdict
            from datetime import datetime

            bars_by_timestamp = defaultdict(list)

            for bar in new_bars:
                # Get current timestamp
                current_time = bar.get('timestamp')
                if not current_time:
                    continue

                # Parse timestamp if it's a string (from Redis)
                if isinstance(current_time, str):
                    current_time = datetime.fromisoformat(current_time)

                bars_by_timestamp[current_time].append(bar)

            # Process each unique timestamp once (sorted for chronological order)
            for current_time in sorted(bars_by_timestamp.keys()):
                try:
                    # Get underlying data (historical + current bar) - called once per timestamp
                    underlying_data = self.market_data.get_underlying_history(
                        ticker="SPX",
                        lookback_bars=100
                    )

                    # Get options data (current snapshot) - called once per timestamp
                    options_data = self.market_data.get_current_options_snapshot()

                    # Execute strategy for this timestamp
                    self.strategy_executor.on_bar(
                        underlying_data=underlying_data,
                        options_data=options_data,
                        current_time=current_time,
                    )

                except Exception as e:
                    self.logger.error(f"Error executing strategies on bar: {e}", exc_info=True)

            # Log batch summary
            # if bars_by_timestamp:
            #     self.logger.debug(
            #         f"Batch processed: {len(bars_by_timestamp)} unique timestamps, "
            #         f"{len(new_bars)} total bars"
            #     )

    def _listen_for_control_messages(self):
        """
        Listen for control messages on Redis pub/sub.

        Runs in a background thread and processes commands like reload_strategies.
        """
        if not self.message_broker:
            return

        self.logger.info("Control message listener thread started")

        try:
            # Create a separate broker instance for subscription (thread-safe)
            from quant_vibe.messaging import RedisMessageBroker
            redis_config = self.config.get('redis', {})
            listener_broker = RedisMessageBroker(
                host=redis_config.get('host'),
                port=redis_config.get('port'),
                db=redis_config.get('db'),
            )

            def handle_control_message(topic: str, data: dict):
                """Handle incoming control messages."""
                try:
                    command = data.get('command')
                    self.logger.info(f"Received control command: {command}")

                    if command == 'reload_strategies':
                        self.logger.info("Processing reload_strategies command...")
                        result = self.reload_strategies()
                        if result['success']:
                            self.logger.info(f"✅ {result['message']}")
                        else:
                            self.logger.error(f"❌ {result['message']}")

                    elif command == 'reconcile':
                        self.logger.info("Processing reconcile command...")
                        if self.paper_trading:
                            self.logger.info("ℹ️  Paper trading mode - skipping broker reconciliation")
                        else:
                            # Extract account_hash from data if provided
                            account_hash = data.get('account_hash')
                            if account_hash:
                                self.logger.info(f"🎯 Using specific account: {account_hash[:8]}...")
                            self.logger.info("\n" + "="*70)
                            self.logger.info("MANUAL RECONCILIATION TRIGGERED")
                            self.logger.info("="*70)
                            self._reconcile_with_broker(account_hash=account_hash)
                            self.logger.info("="*70 + "\n")

                    else:
                        self.logger.warning(f"Unknown control command: {command}")

                except Exception as e:
                    self.logger.error(f"Error handling control message: {e}", exc_info=True)

            # Subscribe to control topic
            listener_broker.subscribe(["control.live_trading"], callback=handle_control_message)

            # Listen for messages (blocking in this thread)
            listener_broker.listen()

        except Exception as e:
            self.logger.error(f"Control message listener error: {e}", exc_info=True)

    def _publish_heartbeat(self):
        """Publish heartbeat to Redis."""
        if not self.message_broker:
            return

        try:
            # Calculate uptime
            uptime_seconds = 0
            if self.start_time:
                uptime_seconds = (now_utc() - self.start_time).total_seconds()

            # Determine status
            status = "healthy"
            last_error = None

            # Check data staleness (only mark as degraded during market hours)
            feed_stale = self._feed_is_stale()

            if feed_stale and is_market_open():
                status = "degraded"
                last_error = "Data feed is stale"

            # Publish heartbeat
            self.message_broker.publish(
                "heartbeat.live_trading",
                {
                    "service": "live_trading",
                    "timestamp": now_utc().isoformat(),
                    "status": status,
                    "metrics": {
                        "uptime_seconds": round(uptime_seconds, 1),
                        "bars_processed": self.total_bars_processed,
                        "signals_generated": self.total_signals_generated,
                        "data_stale": feed_stale,
                        "state": self.state if self.state else "unknown",
                        "paper_trading": self.paper_trading,
                        "last_error": last_error,
                    },
                },
            )

            self.last_heartbeat_time = now_utc()
            self.logger.debug(f"Heartbeat published (status: {status})")

        except Exception as e:
            self.logger.error(f"Failed to publish heartbeat: {e}", exc_info=True)

    def _run_main_loop(self):
        """Main event loop."""
        status_interval = self.config['monitoring']['status_update_interval_seconds']
        last_status_time = now_utc()
        last_heartbeat_time = now_utc()

        try:
            while not self._shutdown_requested:
                time.sleep(1)

                # Heartbeat every 30 seconds
                heartbeat_elapsed = (now_utc() - last_heartbeat_time).total_seconds()
                if heartbeat_elapsed >= 30:
                    self._publish_heartbeat()
                    last_heartbeat_time = now_utc()

                # Status update
                elapsed = (now_utc() - last_status_time).total_seconds()
                if elapsed >= status_interval:
                    self._print_status()
                    last_status_time = now_utc()

                # Health checks
                self._health_check()

        except KeyboardInterrupt:
            self.logger.warning("Keyboard interrupt received")
            self._shutdown_requested = True

        finally:
            self.stop()

    def _health_check(self):
        """Perform health checks."""
        # Check data staleness (only warn during market hours)
        feed_stale = self._feed_is_stale()
        if feed_stale and is_market_open():
            self.logger.warning("⚠️  Data feed is stale!")
            self.state_store.log_event(
                EventType.DATA_STALE,
                "Data feed has not received updates in 5+ minutes",
                severity='warning'
            )

        # TODO: Add more health checks
        # - Check account connection
        # - Verify position reconciliation
        # - Check for stuck orders

    def _print_status(self):
        """Print status update."""
        uptime = (now_utc() - self.start_time).total_seconds() if self.start_time else 0
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)

        # Get stats from active feed
        if self.redis_feed:
            stats = self.redis_feed.get_stats()
            feed_type = "Redis"
        else:
            stats = {}
            feed_type = "Unknown"

        self.logger.info("\n" + "="*70)
        self.logger.info(f"STATUS UPDATE - {now_utc().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("-"*70)
        self.logger.info(f"State: {self.state}")
        self.logger.info(f"Mode: {'PAPER TRADING' if self.paper_trading else '⚠️  LIVE TRADING ⚠️'}")
        self.logger.info(f"Data Feed: {feed_type}")
        self.logger.info(f"Uptime: {hours}h {minutes}m")
        self.logger.info(f"Bars Processed: {self.total_bars_processed}")
        self.logger.info(f"Messages Received: {stats.get('message_count', 0)}")
        self.logger.info(f"Symbols Tracked: {stats.get('underlying_symbols_tracked', stats.get('symbols_tracked', 0))}")
        self.logger.info(f"Data Stale: {stats.get('data_stale', False)}")
        self.logger.info("="*70)

        # Save state to database for admin UI
        self.state_store.save_engine_state(
            self.state,
            {
                'paper_trading': self.paper_trading,
                'total_bars_processed': self.total_bars_processed,
                'total_signals_generated': 0,  # TODO: track signals
                'uptime_seconds': uptime,
                'data_source': feed_type.lower(),
                'data_feed_mode': self.get_data_feed_mode(),
            }
        )

    def stop(self):
        """Stop the trading engine gracefully."""
        self.logger.info("\n" + "="*70)
        self.logger.info("STOPPING LIVE TRADING ENGINE")
        self.logger.info("="*70)

        self.state = TradingState.STOPPING

        # Stop data feed
        if self.redis_feed:
            self.logger.info("Stopping Redis feed...")
            try:
                self.redis_feed.stop()
                self.logger.info("  ✓ Redis feed stopped")
            except Exception as e:
                self.logger.error(f"  Error stopping Redis feed: {e}")

        # TODO: Close all positions if configured

        # Close connections
        if self.message_broker:
            self.logger.info("Closing message broker...")
            try:
                self.message_broker.close()
                self.logger.info("  ✓ Message broker closed")
            except Exception as e:
                self.logger.error(f"  Error closing message broker: {e}")

        if self.state_store:
            self.logger.info("Closing state store...")
            self.state_store.save_engine_state(
                TradingState.STOPPED,
                {'stopped_at': now_utc().isoformat()}
            )
            self.state_store.log_event(
                EventType.ENGINE_STOPPED,
                "Engine stopped",
                severity='info'
            )
            self.state_store.close()
            self.logger.info("  ✓ State store closed")

        self.state = TradingState.STOPPED

        # Send stop notification
        if self.notifier:
            self.notifier.on_engine_stop(reason="Manual shutdown")

        self.logger.info("="*70)
        self.logger.info("✅ ENGINE STOPPED")
        self.logger.info("="*70)

    def reload_strategies(self) -> Dict:
        """
        Reload strategies from configuration file without restarting.

        This allows hot-reloading of strategy changes from the YAML config.
        Active positions are preserved and transferred to matching strategies.

        Returns:
            Dictionary with reload status and details
        """
        self.logger.info("="*70)
        self.logger.info("RELOADING STRATEGIES")
        self.logger.info("="*70)

        try:
            # Reload config from file
            self.config = self._load_config("config/live_trading.yaml")
            self.logger.info("  ✓ Configuration reloaded")

            # Load new strategies
            from live_trading_service.strategy_loader import StrategyLoader
            new_strategies = StrategyLoader.load_strategies(self.config)
            self.logger.info(f"  ✓ Loaded {len(new_strategies)} strategies from config")

            # Update strategy executor
            if self.strategy_executor:
                self.strategy_executor.update_strategies(new_strategies)
                self.logger.info("  ✓ Strategy executor updated")
            else:
                self.logger.warning("  ⚠️  Strategy executor not initialized")

            # Update our local reference
            self.strategies = new_strategies

            # Log event
            if self.state_store:
                self.state_store.log_event(
                    EventType.STRATEGY_RELOAD,
                    f"Strategies reloaded: {[s.name for s in new_strategies]}",
                    severity='info'
                )

            self.logger.info("="*70)
            self.logger.info("✅ STRATEGIES RELOADED SUCCESSFULLY")
            self.logger.info("="*70)

            return {
                'success': True,
                'message': f'Successfully reloaded {len(new_strategies)} strategies',
                'strategies': [s.name for s in new_strategies],
            }

        except Exception as e:
            self.logger.error(f"Failed to reload strategies: {e}", exc_info=True)

            if self.state_store:
                self.state_store.log_event(
                    EventType.STRATEGY_RELOAD,
                    f"Strategy reload failed: {str(e)}",
                    severity='error'
                )

            return {
                'success': False,
                'message': f'Failed to reload strategies: {str(e)}',
                'strategies': [],
            }

    def get_status(self) -> Dict:
        """Get current engine status."""
        return {
            'state': self.state,
            'paper_trading': self.paper_trading,
            'uptime_seconds': (now_utc() - self.start_time).total_seconds() if self.start_time else 0,
            'bars_processed': self.total_bars_processed,
            'strategies_loaded': len(self.strategies),
            'data_feed_stats': self.redis_feed.get_stats() if self.redis_feed else {},
        }
