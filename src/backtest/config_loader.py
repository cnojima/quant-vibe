"""Configuration loader for backtesting engine."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml


class BacktestConfig:
    """Backtest configuration loader and validator."""

    def __init__(self, config_path: str = "config/backtest.yaml"):
        """Initialize configuration loader."""
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

        if not self.get_enabled_strategies():
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
        return Path(self.config['engine'].get('output_dir', 'reports/backtests'))

    def _resolve_date_preset(self, preset: str) -> tuple[datetime, datetime]:
        """Resolve a date preset to actual dates in EST."""
        est = ZoneInfo('America/New_York')
        now_est = datetime.now(est)

        # Map preset to date range
        preset_map = {
            'today': lambda: (
                datetime(now_est.year, now_est.month, now_est.day),
                datetime(now_est.year, now_est.month, now_est.day)
            ),
            'this_week': lambda: self._current_week_range(now_est),
            'this_month': lambda: (
                datetime(now_est.year, now_est.month, 1),
                datetime(now_est.year, now_est.month, now_est.day)
            ),
            'this_quarter': lambda: (
                datetime(now_est.year, ((now_est.month - 1) // 3) * 3 + 1, 1),
                datetime(now_est.year, now_est.month, now_est.day)
            ),
            'this_year': lambda: (
                datetime(now_est.year, 1, 1),
                datetime(now_est.year, now_est.month, now_est.day)
            )
        }

        if preset not in preset_map:
            raise ValueError(f"Unknown date preset: {preset}")

        return preset_map[preset]()

    def _current_week_range(self, now_est: datetime) -> tuple[datetime, datetime]:
        """Get the current week range (Monday to today or Friday)."""
        days_since_monday = now_est.weekday()
        monday = now_est - timedelta(days=days_since_monday)
        start_date = datetime(monday.year, monday.month, monday.day)

        # End date is today if weekday, or Friday if weekend
        if now_est.weekday() <= 4:  # Mon-Fri
            end_date = datetime(now_est.year, now_est.month, now_est.day)
        else:
            friday = monday + timedelta(days=4)
            end_date = datetime(friday.year, friday.month, friday.day)

        return start_date, end_date

    def get_date_range(self) -> tuple[datetime, datetime]:
        """Get date range for backtest."""
        date_config = self.config.get('date_range', {})
        preset = date_config.get('preset', 'this_month')

        if preset == 'custom':
            return self._parse_custom_dates(date_config.get('custom', {}))

        return self._resolve_date_preset(preset)

    def _parse_custom_dates(self, custom: Dict[str, Any]) -> tuple[datetime, datetime]:
        """Parse custom date range from config."""
        start_val = custom.get('start_date')
        end_val = custom.get('end_date')

        if not start_val or not end_val:
            raise ValueError(
                "Custom date range requires 'start_date' and 'end_date' in config"
            )

        # Handle both string and datetime.date types from YAML
        start_date = self._parse_date_value(start_val)
        end_date = self._parse_date_value(end_val)

        return start_date, end_date

    def _parse_date_value(self, value: Any) -> datetime:
        """Parse date value from string or date object."""
        if isinstance(value, str):
            return datetime.strptime(value, '%Y-%m-%d')
        return datetime(value.year, value.month, value.day)

    def get_date_preset(self) -> str:
        """Get date range preset."""
        return self.config.get('date_range', {}).get('preset', 'this_month')

    def get_underlying_ticker(self) -> str:
        """Get underlying ticker symbol."""
        return self.config['data_source'].get('underlying_ticker', 'SPX')

    def get_db_profile(self) -> Optional[str]:
        """Get database profile (auto, local, or remote)."""
        profile = self.config['data_source'].get('db_profile', 'auto')
        return None if profile == 'auto' else profile

    def get_min_dte(self) -> int:
        """Get minimum days to expiration."""
        return int(self.config['data_source'].get('min_dte', 0))

    def get_max_dte(self) -> int:
        """Get maximum days to expiration."""
        return int(self.config['data_source'].get('max_dte', 45))

    def is_verbose(self) -> bool:
        """Check if verbose output is enabled."""
        return bool(self.config['data_source'].get('verbose', True))

    def get_timeframe(self) -> str:
        """Get timeframe for data aggregation."""
        return self.config['data_source'].get('timeframe', '1min')

    def should_print_trade_details(self) -> bool:
        """Check if trade details should be printed."""
        return self._get_reporting_flag('print_trade_details', True)

    def should_print_educational_metrics(self) -> bool:
        """Check if educational metrics should be printed."""
        return self._get_reporting_flag('print_educational_metrics', True)

    def should_print_performance_summary(self) -> bool:
        """Check if performance summary should be printed."""
        return self._get_reporting_flag('print_performance_summary', True)

    def _get_reporting_flag(self, key: str, default: bool) -> bool:
        """Get a boolean flag from reporting config."""
        return bool(self.config.get('reporting', {}).get(key, default))

    def should_auto_save_results(self) -> bool:
        """Check if results should be saved automatically."""
        return bool(self.config['engine'].get('auto_save_results', True))

    def should_save_trades(self) -> bool:
        """Check if trades should be saved."""
        return self._get_output_flag('save_trades', True)

    def should_save_equity_curve(self) -> bool:
        """Check if equity curve should be saved."""
        return self._get_output_flag('save_equity_curve', True)

    def should_save_log(self) -> bool:
        """Check if log should be saved."""
        return self._get_output_flag('save_log', True)

    def _get_output_flag(self, key: str, default: bool) -> bool:
        """Get a boolean flag from output config."""
        return bool(self.config.get('output', {}).get(key, default))

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
        strategy_names = [s['name'] for s in self.get_enabled_strategies()]
        return (
            f"BacktestConfig(config_path={self.config_path}, "
            f"strategies={strategy_names}, "
            f"capital={self.get_initial_capital()})"
        )