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

    def __init__(self, config_path: str = "config/live_trading.yaml"):
        """
        Initialize live trading engine.

        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        self.config = self._load_config(config_path)

        # Setup normalized logging
        # self.logger = setup_normalized_logging(
        #     app_name="live_trading",
        #     log_dir="logs/live_trading",
        # )
        self.logger = get_logger('live_trading')

        self.logger.info("="*70)
        self.logger.info("Initializing Live Trading Engine")
        self.logger.info("="*70)

        # State
        self.state = TradingState.STOPPED
        self.paper_trading = self.config['engine'].get('paper_trading', True)
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

        self.logger.info(f"Paper Trading Mode: {self.paper_trading}")
        self.logger.info(f"Configuration loaded from: {config_path}")

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

        # Initialize state store
        self.logger.info("  - Initializing state store...")
        self.state_store = StateStore()
        self.logger.info("    ✓ State store ready")

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

        # Initialize token service client if enabled
        if data_feed_mode != 'replay' and self.use_token_service and TOKEN_SERVICE_AVAILABLE and self.token_service_url:
            self.logger.info(f"  - Connecting to token service ({self.token_service_url})...")
            try:
                self.token_service_client = TokenServiceClient(
                    base_url=self.token_service_url,
                    logger=self.logger
                )
                health = self.token_service_client.health_check()
                if health.get("status") == "healthy":
                    self.logger.info("    ✓ Token service connected")
                else:
                    self.logger.warning(f"    ⚠️ Token service unhealthy: {health}")
                    self.logger.warning("    Falling back to local token management")
                    self.token_service_client = None
            except Exception as e:
                self.logger.warning(f"    ⚠️ Failed to connect to token service: {e}")
                self.logger.warning("    Falling back to local token management")
                self.token_service_client = None

        if data_feed_mode != 'replay':
            # Initialize Schwab client (only for order execution, not streaming)
            self.logger.info("  - Initializing Schwab client...")
            tokens_db = "tokens/schwabdev_tokens.db"
            self.schwab_client = schwabdev.Client(
                os.getenv("SCHWAB_API_KEY"),
                os.getenv("SCHWAB_API_SECRET"),
                os.getenv("SCHWAB_CALLBACK_URL"),
                tokens_db=tokens_db,
            )

            if self.token_service_client:
                self.logger.info("    ✓ Schwab client ready (order execution only, tokens via token service)")
            else:
                self.logger.info("    ✓ Schwab client ready (order execution only, tokens via local database)")

        # Initialize OrderManager
        self.logger.info("  - Initializing OrderManager...")
        oco_config = self.config.get('oco', {})
        self.order_manager = OrderManager(
            schwab_client=self.schwab_client,
            state_store=self.state_store,
            paper_trading=self.paper_trading,
            use_oco=oco_config.get('enabled', False),
            oco_config=oco_config,
        )
        self.logger.info("    ✓ OrderManager ready")

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
