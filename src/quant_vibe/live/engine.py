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
from datetime import datetime, time as dt_time
from typing import Dict, List, Optional
import signal
import yaml
from pathlib import Path

import schwabdev
from dotenv import load_dotenv

from .data_feed import RealtimeDataFeed
from .state_store import StateStore
from .utils import (
    setup_logging, TradingState, EventType,
    is_market_open, get_market_hours
)

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

        # Setup logging
        self.logger = setup_logging(
            log_dir=self.config.get('logging', {}).get('log_dir', 'logs/live_trading'),
            log_level=self.config.get('logging', {}).get('log_level', 'INFO')
        )

        self.logger.info("="*70)
        self.logger.info("Initializing Live Trading Engine")
        self.logger.info("="*70)

        # State
        self.state = TradingState.STOPPED
        self.paper_trading = self.config['engine'].get('paper_trading', True)

        # Initialize components
        self.data_feed: Optional[RealtimeDataFeed] = None
        self.state_store: Optional[StateStore] = None
        self.schwab_client: Optional[schwabdev.Client] = None
        self.streamer: Optional[schwabdev.Stream] = None

        # Strategies (to be loaded)
        self.strategies: Dict[str, any] = {}
        self.active_positions: Dict[str, List] = {}  # strategy_name -> [positions]

        # Statistics
        self.start_time: Optional[datetime] = None
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
                'max_positions': 5,
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

    def initialize(self):
        """Initialize all components."""
        self.logger.info("Initializing components...")

        # Initialize state store
        self.logger.info("  - Initializing state store...")
        self.state_store = StateStore()
        self.logger.info("    ✓ State store ready")

        # Initialize data feed
        self.logger.info("  - Initializing data feed...")
        self.data_feed = RealtimeDataFeed(
            window_size=self.config['data_feed']['window_size'],
            aggregate_interval_seconds=self.config['data_feed']['aggregate_interval_seconds'],
            callbacks=[self._on_new_bars]  # Register callback
        )
        self.logger.info("    ✓ Data feed ready")

        # Initialize Schwab client
        self.logger.info("  - Initializing Schwab client...")
        tokens_db = "tokens/schwabdev_tokens.db"
        self.schwab_client = schwabdev.Client(
            os.getenv("SCHWAB_API_KEY"),
            os.getenv("SCHWAB_API_SECRET"),
            os.getenv("SCHWAB_CALLBACK_URL"),
            tokens_db=tokens_db,
        )
        self.streamer = schwabdev.Stream(self.schwab_client)
        self.logger.info("    ✓ Schwab client ready")

        # Load strategies
        self.logger.info("  - Loading strategies...")
        self._load_strategies()
        self.logger.info(f"    ✓ Loaded {len(self.strategies)} strategies")

        # Save initial state
        self.state_store.save_engine_state(
            self.state,
            {'initialized': True, 'paper_trading': self.paper_trading}
        )

        self.logger.info("✅ All components initialized")

    def _load_strategies(self):
        """Load and initialize strategies from configuration."""
        # TODO: Implement dynamic strategy loading
        # For now, this is a placeholder

        enabled_strategies = self.config['strategies'].get('enabled', [])

        for strategy_config in enabled_strategies:
            strategy_name = strategy_config.get('name')
            if not strategy_name:
                continue

            self.logger.info(f"    Loading strategy: {strategy_name}")

            # Initialize position tracking for strategy
            self.active_positions[strategy_name] = []

            # Store strategy config
            self.strategies[strategy_name] = {
                'config': strategy_config,
                'instance': None,  # Will be created later
                'enabled': strategy_config.get('enabled', True)
            }

    def start(self):
        """Start the live trading engine."""
        self.logger.info("\n" + "="*70)
        self.logger.info("STARTING LIVE TRADING ENGINE")
        self.logger.info("="*70)

        self.state = TradingState.STARTING
        self.start_time = datetime.now()

        # Log state
        self.state_store.log_event(
            EventType.ENGINE_STARTED,
            f"Engine started in {'PAPER' if self.paper_trading else 'LIVE'} mode",
            severity='info'
        )

        # Subscribe to options contracts
        contracts = self._get_contracts_to_stream()

        if not contracts:
            self.logger.error("No contracts to stream! Exiting.")
            return

        # Start schwabdev stream
        self.logger.info("Starting schwabdev stream...")
        import zoneinfo
        self.streamer.start_auto(
            self.data_feed.handle_message,
            start_time=dt_time(9, 29, 0),
            stop_time=dt_time(16, 0, 0),
            on_days=(0, 1, 2, 3, 4),
            now_timezone=zoneinfo.ZoneInfo("America/New_York"),
            daemon=True
        )

        # Subscribe to contracts (batched)
        self._subscribe_to_contracts(contracts)

        self.state = TradingState.RUNNING
        self.state_store.save_engine_state(self.state, {'contracts': len(contracts)})

        self.logger.info("✅ Engine is RUNNING")
        self.logger.info("="*70)

        # Main loop
        self._run_main_loop()

    def _get_contracts_to_stream(self) -> List[str]:
        """Get list of option contracts to stream."""
        self.logger.info("Fetching SPXW contracts...")

        max_dte = self.config['data_feed']['max_dte']
        min_dte = self.config['data_feed']['min_dte']
        strike_range_pct = self.config['data_feed']['strike_range_pct']

        # Get SPX price
        try:
            response = self.schwab_client.quote("$SPX")
            spx_data = response.json()

            if "$SPX" in spx_data:
                spx_price = spx_data["$SPX"]["quote"]["lastPrice"]
                self.logger.info(f"  SPX price: ${spx_price:.2f}")
            else:
                self.logger.warning("  Could not get SPX price, using default")
                spx_price = 6000.0
        except Exception as e:
            self.logger.error(f"  Error getting SPX price: {e}")
            spx_price = 6000.0

        # Calculate strike range
        strike_min = spx_price * (1 - strike_range_pct)
        strike_max = spx_price * (1 + strike_range_pct)

        self.logger.info(f"  Strike range: ${strike_min:.0f} - ${strike_max:.0f}")
        self.logger.info(f"  DTE range: {min_dte} - {max_dte}")

        # Get option chain
        contracts = []

        try:
            response = self.schwab_client.option_chains("$SPX", strikeCount=50)
            chain_data = response.json()

            today = datetime.now().date()

            for option_type in ['callExpDateMap', 'putExpDateMap']:
                if option_type not in chain_data:
                    continue

                exp_map = chain_data[option_type]

                for exp_date_str, strikes in exp_map.items():
                    exp_date = datetime.strptime(exp_date_str.split(':')[0], '%Y-%m-%d').date()
                    dte = (exp_date - today).days

                    if dte < min_dte or dte > max_dte:
                        continue

                    for strike_str, contract_list in strikes.items():
                        strike = float(strike_str)

                        if strike < strike_min or strike > strike_max:
                            continue

                        for contract in contract_list:
                            symbol = contract.get('symbol', '')
                            if 'SPXW' in symbol:
                                contracts.append(symbol)

            self.logger.info(f"  Found {len(contracts)} SPXW contracts")

        except Exception as e:
            self.logger.error(f"  Error fetching contracts: {e}", exc_info=True)

        return contracts

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

    def _on_new_bars(self, new_bars: List[Dict]):
        """
        Callback when new bars are created by data feed.

        This is where strategy execution happens.

        Args:
            new_bars: List of newly created bars
        """
        self.total_bars_processed += len(new_bars)

        # TODO: Execute strategies on new bars
        # For now, just log
        self.logger.debug(f"Received {len(new_bars)} new bars")

        # Check data staleness
        if self.data_feed.is_data_stale():
            self.logger.warning("Data is stale! Pausing new entries.")
            # TODO: Implement pause logic

    def _run_main_loop(self):
        """Main event loop."""
        status_interval = self.config['monitoring']['status_update_interval_seconds']
        last_status_time = datetime.now()

        try:
            while not self._shutdown_requested:
                time.sleep(1)

                # Status update
                elapsed = (datetime.now() - last_status_time).total_seconds()
                if elapsed >= status_interval:
                    self._print_status()
                    last_status_time = datetime.now()

                # Health checks
                self._health_check()

        except KeyboardInterrupt:
            self.logger.warning("Keyboard interrupt received")
            self._shutdown_requested = True

        finally:
            self.stop()

    def _health_check(self):
        """Perform health checks."""
        # Check data staleness
        if self.data_feed and self.data_feed.is_data_stale():
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
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)

        stats = self.data_feed.get_stats() if self.data_feed else {}

        self.logger.info("\n" + "="*70)
        self.logger.info(f"STATUS UPDATE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("-"*70)
        self.logger.info(f"State: {self.state}")
        self.logger.info(f"Mode: {'PAPER TRADING' if self.paper_trading else '⚠️  LIVE TRADING ⚠️'}")
        self.logger.info(f"Uptime: {hours}h {minutes}m")
        self.logger.info(f"Bars Processed: {self.total_bars_processed}")
        self.logger.info(f"Messages Received: {stats.get('message_count', 0)}")
        self.logger.info(f"Symbols Tracked: {stats.get('symbols_tracked', 0)}")
        self.logger.info(f"Data Stale: {stats.get('data_stale', False)}")
        self.logger.info("="*70)

    def stop(self):
        """Stop the trading engine gracefully."""
        self.logger.info("\n" + "="*70)
        self.logger.info("STOPPING LIVE TRADING ENGINE")
        self.logger.info("="*70)

        self.state = TradingState.STOPPING

        # Stop streaming
        if self.streamer:
            self.logger.info("Stopping stream...")
            try:
                self.streamer.stop()
                self.logger.info("  ✓ Stream stopped")
            except Exception as e:
                self.logger.error(f"  Error stopping stream: {e}")

        # TODO: Close all positions if configured

        # Close connections
        if self.state_store:
            self.logger.info("Closing state store...")
            self.state_store.save_engine_state(
                TradingState.STOPPED,
                {'stopped_at': datetime.now().isoformat()}
            )
            self.state_store.log_event(
                EventType.ENGINE_STOPPED,
                "Engine stopped",
                severity='info'
            )
            self.state_store.close()
            self.logger.info("  ✓ State store closed")

        self.state = TradingState.STOPPED
        self.logger.info("="*70)
        self.logger.info("✅ ENGINE STOPPED")
        self.logger.info("="*70)

    def get_status(self) -> Dict:
        """Get current engine status."""
        return {
            'state': self.state,
            'paper_trading': self.paper_trading,
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            'bars_processed': self.total_bars_processed,
            'strategies_loaded': len(self.strategies),
            'data_feed_stats': self.data_feed.get_stats() if self.data_feed else {},
        }
