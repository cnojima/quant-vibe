#!/usr/bin/env python3
"""Trading Launcher - Manages parallel real and paper trading engines.

This launcher can run real and paper trading engines simultaneously as
separate processes. Both engines consume the same Redis data feed, so the
data source (live or replay) is independent of the trading modes.

Architecture:
    Data Source (StreamingService or ReplayService)
           ↓
      Redis Pub/Sub (options_bars, underlying_bars)
           ↓
      ┌────┴────┐
      ↓         ↓
   Real Engine  Paper Engine
   (separate    (separate
    process)     process)

Usage:
    # Both real and paper
    python scripts/run_trading_launcher.py

    # Only paper (for testing)
    python scripts/run_trading_launcher.py --paper-only

    # Only real (production)
    python scripts/run_trading_launcher.py --real-only
"""

import sys
import time
import signal
import argparse
import multiprocessing as mp
from typing import Dict
import yaml

# Add src to path for Docker container
sys.path.insert(0, "/app/src")

from quant_vibe.logging.unified_logging import get_logger


def _run_engine_process(mode: str, config_path: str):
    """
    Run a single trading engine (in child process).
    This must be a module-level function (not a method) to avoid
    pickling issues with multiprocessing.

    Args:
        mode: 'real' or 'paper'
        config_path: Path to engine config
    """
    # Write errors to a file since child stdout might not be visible
    error_log = Path(f"logs/live_trading/{mode}_engine_startup_errors.log")
    error_log.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Import here to avoid issues with multiprocessing
        from live_trading_service.engine import LiveTradingEngine

        with open(error_log, 'w') as f:
            f.write(f"[{mode}] Starting engine initialization...\n")
            f.write(f"[{mode}] Config path: {config_path}\n")
            f.flush()

        engine = LiveTradingEngine(
            trading_mode=mode,
            config_path=config_path
        )

        with open(error_log, 'a') as f:
            f.write(f"[{mode}] Engine created, calling initialize()...\n")
            f.flush()

        engine.initialize()

        with open(error_log, 'a') as f:
            f.write(f"[{mode}] Initialized, calling start()...\n")
            f.flush()

        engine.start()

        with open(error_log, 'a') as f:
            f.write(f"[{mode}] Engine started, entering main loop...\n")
            f.flush()

        # Run the main loop
        engine._run_main_loop()

    except KeyboardInterrupt:
        with open(error_log, 'a') as f:
            f.write(f"\n[{mode}] Shutdown requested\n")
    except Exception as e:
        import traceback
        with open(error_log, 'a') as f:
            f.write(f"\n❌ [{mode}] Engine crashed: {e}\n")
            f.write(traceback.format_exc())
            f.flush()


class TradingLauncher:
    """Launches and manages multiple trading engines in parallel."""

    def __init__(self, config_path: str = "config/trading_launcher.yaml"):
        """
        Initialize trading launcher.

        Args:
            config_path: Path to launcher configuration file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.processes: Dict[str, mp.Process] = {}
        self.logger = get_logger('trading_launcher')
        self._setup_signal_handlers()

    def _load_config(self) -> Dict:
        """Load launcher configuration."""
        config_file = Path(self.config_path)

        if not config_file.exists():
            self.logger.error(f"Config file not found: {self.config_path}")
            self.logger.info("Creating default config...")
            self._create_default_config()
            return self._load_config()

        with open(config_file, 'r') as f:
            return yaml.safe_load(f)

    def _create_default_config(self):
        """Create default launcher configuration."""
        default_config = {
            'data_source': {
                'mode': 'live',  # 'live' or 'replay'
                'replay': {
                    'start_date': '2024-12-01',
                    'end_date': '2024-12-31',
                    'speed_multiplier': 1.0
                }
            },
            'engines': {
                'real_trading': {
                    'enabled': False,  # CRITICAL: Start disabled for safety
                    'config': 'config/live_trading_real.yaml'
                },
                'paper_trading': {
                    'enabled': True,
                    'config': 'config/live_trading_paper.yaml'
                }
            }
        }

        config_file = Path(self.config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)

        print(f"✅ Created default config: {self.config_path}")
        print("⚠️  Real trading is DISABLED by default - enable manually if needed")

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, _frame):
        """Handle shutdown signals."""
        self.logger.warning(f"\n🛑 Received signal {signum}, shutting down...")
        self.stop_all()
        sys.exit(0)

    def start(self, real_only: bool = False, paper_only: bool = False):
        """
        Start enabled trading engines.

        Args:
            real_only: Only start real trading engine
            paper_only: Only start paper trading engine
        """
        self.logger.info("=" * 70)
        self.logger.info("Trading Launcher Starting")
        self.logger.info("=" * 70)

        engines_config = self.config.get('engines', {})

        # Start real trading engine
        real_enabled = engines_config.get('real_trading', {}).get('enabled', False)
        if not paper_only and real_enabled:
            self.logger.info("\n💵 Starting REAL trading engine...")
            self._start_engine('real', engines_config['real_trading']['config'])
        elif not paper_only and not real_only:
            self.logger.info("\n💵 Real trading engine: DISABLED")

        # Start paper trading engine
        paper_enabled = engines_config.get('paper_trading', {}).get('enabled', False)
        self.logger.info(f"\n📝 Paper trading check: enabled={paper_enabled}, real_only={real_only}")
        if not real_only and paper_enabled:
            self.logger.info("   Starting PAPER trading engine...")
            self._start_engine('paper', engines_config['paper_trading']['config'])
        elif not real_only and not paper_only:
            self.logger.info("   Paper trading engine: DISABLED")

        if not self.processes:
            self.logger.error("\n❌ No engines enabled or started!")
            self.logger.info("Enable engines in config: config/trading_launcher.yaml")
            sys.exit(1)

        self.logger.info(f"\n✅ Started {len(self.processes)} engine(s)")
        self.logger.info("=" * 70)
        self.logger.info("")

        # Monitor processes
        self._monitor_processes()

    def _start_engine(self, mode: str, config_path: str):
        """
        Start a single trading engine in a separate process.

        Args:
            mode: 'real' or 'paper'
            config_path: Path to engine-specific config file
        """
        self.logger.info(f"   _start_engine called for mode={mode}, config={config_path}")

        # Verify config exists
        if not Path(config_path).exists():
            self.logger.error(f"   ❌ Config not found: {config_path}")
            self.logger.info(f"   Creating default config...")
            self._create_engine_config(config_path, mode)

        self.logger.info(f"   Creating multiprocessing.Process for {mode}...")
        try:
            p = mp.Process(
                target=_run_engine_process,
                args=(mode, config_path),
                name=f'{mode}-trading'
            )
            self.logger.info(f"   Starting process for {mode}...")
            p.start()
            self.processes[mode] = p
            self.logger.info(f"   ✅ {mode.upper()} engine started (PID: {p.pid})")

            # Give it a moment and check if it's still alive
            time.sleep(0.5)
            if not p.is_alive():
                self.logger.error(f"   ⚠️  {mode} process died immediately! Check logs/live_trading/{mode}_engine_startup_errors.log")
        except Exception as e:
            self.logger.error(f"   ❌ Failed to start {mode} engine: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    def _create_engine_config(self, config_path: str, mode: str):
        """
        Create default engine config file.

        Args:
            config_path: Path where config should be created
            mode: 'real' or 'paper'
        """
        # Load example config as template
        example_path = Path("config/live_trading.example.yaml")
        if example_path.exists():
            with open(example_path, 'r') as f:
                config = yaml.safe_load(f)
        else:
            # Create minimal config
            config = {
                'engine': {
                    'paper_trading': mode == 'paper',
                    'max_positions': 25,
                    'max_capital_per_trade': 10000,
                },
                'strategies': {'enabled': []},
                'data_feed': {'window_size': 100},
                'redis': {'host': None, 'port': None, 'db': None}
            }

        # Save
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)

        with open(config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"   ✅ Created config: {config_path}")

    def _monitor_processes(self):
        """Monitor child processes and handle exits."""
        # Show which processes are running
        self.logger.info("\nMonitoring processes:")
        for mode, process in self.processes.items():
            self.logger.info(f"  - {mode} trading: PID {process.pid} (alive: {process.is_alive()})")

        try:
            while self.processes:
                for mode, process in list(self.processes.items()):
                    if not process.is_alive():
                        exit_code = process.exitcode
                        if exit_code == 0:
                            self.logger.info(f"✅ {mode} engine exited cleanly")
                        else:
                            self.logger.error(f"❌ {mode} engine exited with code {exit_code}")
                        del self.processes[mode]

                        # If all processes died, exit
                        if not self.processes:
                            self.logger.info("All engines stopped")
                            return

                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("\n🛑 Keyboard interrupt - shutting down...")
            self.stop_all()

    def stop_all(self):
        """Stop all running engines gracefully."""
        if not self.processes:
            return

        self.logger.info("Stopping all engines...")

        for mode, process in self.processes.items():
            self.logger.info(f"  Stopping {mode} engine...")
            process.terminate()

        # Wait for graceful shutdown
        time.sleep(5)

        # Force kill if still alive
        for mode, process in self.processes.items():
            if process.is_alive():
                self.logger.warning(f"  Force killing {mode} engine...")
                process.kill()

        # Wait for processes to finish
        for process in self.processes.values():
            process.join(timeout=5)

        self.processes.clear()
        self.logger.info("✅ All engines stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Launch parallel real and paper trading engines"
    )
    parser.add_argument(
        '--config',
        default='config/trading_launcher.yaml',
        help='Path to launcher config file'
    )
    parser.add_argument(
        '--real-only',
        action='store_true',
        help='Only start real trading engine'
    )
    parser.add_argument(
        '--paper-only',
        action='store_true',
        help='Only start paper trading engine'
    )

    args = parser.parse_args()

    if args.real_only and args.paper_only:
        print("❌ Cannot specify both --real-only and --paper-only")
        sys.exit(1)

    launcher = TradingLauncher(config_path=args.config)
    launcher.start(real_only=args.real_only, paper_only=args.paper_only)


if __name__ == '__main__':
    # Required for multiprocessing on macOS
    mp.set_start_method('spawn', force=True)
    main()
