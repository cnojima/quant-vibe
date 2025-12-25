"""Configuration loader for backtesting engine.

Loads and validates backtest configuration from YAML files.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
import yaml


class BacktestConfig:
    """Backtest configuration loader and validator."""

    def __init__(self, config_path: str = "config/backtest.yaml"):
        """
        Initialize configuration loader.

        Args:
            config_path: Path to YAML configuration file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._validate_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please create a config file or use the default: config/backtest.yaml"
            )

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        if config is None:
            raise ValueError(f"Empty configuration file: {self.config_path}")

        return config

    def _validate_config(self) -> None:
        """Validate required configuration sections."""
        required_sections = ['engine', 'strategies', 'data_source']
        missing = [s for s in required_sections if s not in self.config]

        if missing:
            raise ValueError(
                f"Missing required configuration sections: {missing}\n"
                f"Required: {required_sections}"
            )

        # Validate at least one strategy is enabled
        enabled_strategies = self.get_enabled_strategies()
        if not enabled_strategies:
            raise ValueError(
                "No strategies enabled in configuration.\n"
                "Set 'enabled: true' for at least one strategy in the 'strategies' section."
            )

    def get_enabled_strategies(self) -> List[Dict[str, Any]]:
        """Get list of enabled strategies with their configurations."""
        strategies = self.config.get('strategies', {}).get('enabled', [])
        return [s for s in strategies if s.get('enabled', False)]

    def get_initial_capital(self) -> float:
        """Get initial capital for backtests."""
        return float(self.config['engine'].get('initial_capital', 100000.0))

    def get_output_dir(self) -> Path:
        """Get output directory for backtest results."""
        output_dir = self.config['engine'].get('output_dir', 'reports/backtests')
        return Path(output_dir)

    def get_date_range(self) -> tuple[datetime, datetime]:
        """
        Get date range for backtest.

        Returns:
            Tuple of (start_date, end_date) as datetime objects

        Note:
            This returns the configured dates. The actual date range
            will be converted to market hours by the orchestrator.
        """
        date_config = self.config.get('date_range', {})
        preset = date_config.get('preset', 'this_month')

        if preset == 'custom':
            custom = date_config.get('custom', {})
            start_val = custom.get('start_date')
            end_val = custom.get('end_date')

            if not start_val or not end_val:
                raise ValueError(
                    "Custom date range requires 'start_date' and 'end_date' in config"
                )

            # Handle both string and datetime.date types from YAML
            if isinstance(start_val, str):
                start_date = datetime.strptime(start_val, '%Y-%m-%d')
            else:
                start_date = datetime(start_val.year, start_val.month, start_val.day)

            if isinstance(end_val, str):
                end_date = datetime.strptime(end_val, '%Y-%m-%d')
            else:
                end_date = datetime(end_val.year, end_val.month, end_val.day)
        else:
            # Preset will be handled by get_date_range() utility
            # Return None to signal that preset should be used interactively
            start_date = None
            end_date = None

        return start_date, end_date

    def get_date_preset(self) -> str:
        """Get date range preset."""
        return self.config.get('date_range', {}).get('preset', 'this_month')

    def get_underlying_ticker(self) -> str:
        """Get underlying ticker symbol."""
        return self.config['data_source'].get('underlying_ticker', 'SPX')

    def get_db_profile(self) -> Optional[str]:
        """Get database profile (auto, local, or remote)."""
        profile = self.config['data_source'].get('db_profile', 'auto')
        if profile == 'auto':
            return None  # Let load_options_backtest_data auto-detect
        return profile

    def get_min_dte(self) -> int:
        """Get minimum days to expiration."""
        return int(self.config['data_source'].get('min_dte', 0))

    def get_max_dte(self) -> int:
        """Get maximum days to expiration."""
        return int(self.config['data_source'].get('max_dte', 45))

    def is_verbose(self) -> bool:
        """Check if verbose output is enabled."""
        return bool(self.config['data_source'].get('verbose', True))

    def should_print_trade_details(self) -> bool:
        """Check if trade details should be printed."""
        return bool(self.config.get('reporting', {}).get('print_trade_details', True))

    def should_print_educational_metrics(self) -> bool:
        """Check if educational metrics should be printed."""
        return bool(self.config.get('reporting', {}).get('print_educational_metrics', True))

    def should_print_performance_summary(self) -> bool:
        """Check if performance summary should be printed."""
        return bool(self.config.get('reporting', {}).get('print_performance_summary', True))

    def should_auto_save_results(self) -> bool:
        """Check if results should be saved automatically."""
        return bool(self.config['engine'].get('auto_save_results', True))

    def should_save_trades(self) -> bool:
        """Check if trades should be saved."""
        return bool(self.config.get('output', {}).get('save_trades', True))

    def should_save_equity_curve(self) -> bool:
        """Check if equity curve should be saved."""
        return bool(self.config.get('output', {}).get('save_equity_curve', True))

    def should_save_log(self) -> bool:
        """Check if log should be saved."""
        return bool(self.config.get('output', {}).get('save_log', True))

    def get_log_level(self) -> str:
        """Get logging level."""
        return self.config.get('logging', {}).get('log_level', 'INFO')

    def should_tee_output(self) -> bool:
        """Check if output should be dual-logged (console + file)."""
        return bool(self.config.get('logging', {}).get('tee_output', True))

    def get_timestamp_format(self) -> str:
        """Get timestamp format for output files."""
        return self.config.get('output', {}).get('timestamp_format', '%Y%m%d_%H%M%S')

    def __repr__(self) -> str:
        """String representation of config."""
        enabled = self.get_enabled_strategies()
        strategy_names = [s['name'] for s in enabled]
        return (
            f"BacktestConfig(config_path={self.config_path}, "
            f"strategies={strategy_names}, "
            f"capital={self.get_initial_capital()})"
        )
