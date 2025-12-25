"""Backtest orchestrator - top-level engine for running configured backtests.

This module provides a unified interface for executing backtests similar to
the live trading engine. It handles configuration loading, strategy initialization,
data loading, execution, and reporting.
"""

import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config_loader import BacktestConfig
from quant_vibe.backtesting import BacktestReporter, OptionsBacktestEngine
from quant_vibe.utils import (
    get_date_range,
    load_options_backtest_data,
    save_backtest_results,
    setup_backtest_output,
)
from quant_vibe.config.logging_config import setup_normalized_logging


class BacktestOrchestrator:
    """
    Top-level orchestrator for running backtests.

    Coordinates configuration loading, strategy initialization, data fetching,
    backtest execution, and result reporting.

    Similar to LiveTradingEngine but for historical backtesting.
    """

    def __init__(
        self,
        config_path: str = "config/backtest.yaml",
        strategy_filter: Optional[str] = None
    ):
        """
        Initialize backtest orchestrator.

        Args:
            config_path: Path to backtest configuration file
            strategy_filter: Optional strategy name to run (filters enabled strategies)
        """
        # Load configuration
        self.config = BacktestConfig(config_path)
        self.strategy_filter = strategy_filter

        # Setup normalized logging
        self.logger = setup_normalized_logging(
            app_name="backtest",
            log_level=self.config.get_log_level(),
            log_dir="logs/backtests",
            console_output=True,
        )

        # Statistics
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.results: List[Dict[str, Any]] = []

        self.logger.info("=" * 70)
        self.logger.info(" " * 20 + "BACKTEST ORCHESTRATOR")
        self.logger.info("=" * 70)
        self.logger.info(f"Configuration: {config_path}")
        self.logger.info(f"Initial Capital: ${self.config.get_initial_capital():,.2f}")
        self.logger.info(f"Output Directory: {self.config.get_output_dir()}")

    def _get_strategies_to_run(self) -> List[Dict[str, Any]]:
        """Get list of strategies to run based on config and filter."""
        strategies = self.config.get_enabled_strategies()

        if self.strategy_filter:
            strategies = [
                s for s in strategies
                if s['name'] == self.strategy_filter
            ]

            if not strategies:
                raise ValueError(
                    f"Strategy '{self.strategy_filter}' not found or not enabled.\n"
                    f"Available strategies: {[s['name'] for s in self.config.get_enabled_strategies()]}"
                )

        return strategies

    def _load_strategy(self, strategy_name: str, params: Dict[str, Any]):
        """
        Dynamically load strategy class and instantiate with parameters.

        Args:
            strategy_name: Name of strategy (e.g., 'bullish_vertical_put')
            params: Strategy parameters from config

        Returns:
            Instantiated strategy object
        """
        # Import strategy dynamically
        # Map strategy names to module paths
        strategy_map = {
            'bullish_vertical_put': 'quant_vibe.strategies.bullish_vertical_put.BullishVerticalPutStrategy',
            'bullish_vertical_call': 'quant_vibe.strategies.bullish_vertical_call.BullishVerticalCallStrategy',
        }

        if strategy_name not in strategy_map:
            raise ValueError(
                f"Unknown strategy: {strategy_name}\n"
                f"Available strategies: {list(strategy_map.keys())}"
            )

        # Parse module and class name
        module_path = strategy_map[strategy_name]
        module_name, class_name = module_path.rsplit('.', 1)

        # Import module
        module = __import__(module_name, fromlist=[class_name])
        strategy_class = getattr(module, class_name)

        # Instantiate strategy with parameters
        strategy = strategy_class(**params)

        return strategy

    def _run_single_backtest(
        self,
        strategy_name: str,
        strategy_params: Dict[str, Any],
        underlying_data,
        options_data,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """
        Run a single backtest for one strategy.

        Args:
            strategy_name: Name of the strategy
            strategy_params: Strategy parameters
            underlying_data: Underlying price data
            options_data: Options chain data
            start_date: Backtest start date
            end_date: Backtest end date

        Returns:
            Dictionary with backtest results
        """
        self.logger.info("=" * 70)
        self.logger.info(f"RUNNING BACKTEST: {strategy_name.upper()}")
        self.logger.info("=" * 70)

        # Load strategy
        strategy = self._load_strategy(strategy_name, strategy_params)

        # Setup output for this strategy
        output_dir, timestamp, tee = setup_backtest_output(
            strategy_name=strategy_name,
            base_dir=str(self.config.get_output_dir())
        )

        # Redirect stdout to tee if enabled AND add logger handler for tee file
        original_stdout = sys.stdout
        tee_handler = None
        removed_handlers = []

        if self.config.should_tee_output():
            sys.stdout = tee

            # Remove existing console handlers to avoid duplicates
            import logging
            for handler in self.logger.handlers[:]:
                if isinstance(handler, logging.StreamHandler) and handler.stream == original_stdout:
                    self.logger.removeHandler(handler)
                    removed_handlers.append(handler)

            # Add a handler to write logger output to the tee file (which includes console)
            tee_handler = logging.StreamHandler(tee)
            tee_handler.setLevel(logging.DEBUG)
            from quant_vibe.config.unified_logging import NormalizedFormatter
            tee_handler.setFormatter(NormalizedFormatter(app_name="backtest", include_func=False))
            self.logger.addHandler(tee_handler)

        try:
            # Log strategy configuration
            self.logger.info(f"Strategy: {strategy_name}")
            self.logger.info("Parameters:")
            for key, value in strategy_params.items():
                self.logger.info(f"  {key}: {value}")
            self.logger.info(f"Date Range: {start_date} to {end_date}")
            self.logger.info(f"Underlying: {self.config.get_underlying_ticker()}")

            # Run backtest
            engine = OptionsBacktestEngine(
                initial_capital=self.config.get_initial_capital()
            )

            results = engine.run(
                strategy=strategy,
                underlying_data=underlying_data,
                options_data=options_data,
                start_date=start_date,
                end_date=end_date,
            )

            # Generate reports
            reporter = BacktestReporter()

            if self.config.should_print_trade_details():
                self.logger.info("=" * 70)
                self.logger.info("TRADE DETAILS")
                self.logger.info("=" * 70)
                reporter.print_trade_details(results["trades"])

            if self.config.should_print_educational_metrics():
                self.logger.info("=" * 70)
                self.logger.info("EDUCATIONAL METRICS")
                self.logger.info("=" * 70)
                reporter.print_educational_metrics(
                    results["trades"],
                    results["equity_curve"],
                    self.config.get_initial_capital(),
                )

            # Save results
            if self.config.should_auto_save_results():
                self.logger.info("=" * 70)
                self.logger.info("SAVING RESULTS")
                self.logger.info("=" * 70)

                saved_files = save_backtest_results(
                    results=results,
                    strategy_name=strategy_name,
                    output_dir=output_dir,
                    timestamp=timestamp,
                    verbose=True,
                )

                self.logger.info("Results saved to:")
                for file_type, file_path in saved_files.items():
                    self.logger.info(f"  {file_type}: {file_path}")

            self.logger.info("=" * 70)
            self.logger.info(f"BACKTEST COMPLETE: {strategy_name.upper()}")
            self.logger.info("=" * 70)

            return {
                'strategy_name': strategy_name,
                'results': results,
                'output_dir': output_dir,
                'timestamp': timestamp,
            }

        finally:
            # Remove tee handler from logger
            if tee_handler is not None:
                self.logger.removeHandler(tee_handler)
                tee_handler.close()

            # Restore original console handlers
            for handler in removed_handlers:
                self.logger.addHandler(handler)

            # Restore stdout
            sys.stdout = original_stdout
            if self.config.should_tee_output():
                tee.close()

    def run(self) -> List[Dict[str, Any]]:
        """
        Run all configured backtests.

        Returns:
            List of result dictionaries for each strategy
        """
        self.start_time = datetime.now()

        # Get strategies to run
        strategies = self._get_strategies_to_run()

        self.logger.info(f"Strategies to run: {[s['name'] for s in strategies]}")

        # Get date range
        # Check if we have custom dates in config
        start_date, end_date = self.config.get_date_range()

        if start_date is None or end_date is None:
            # Use interactive date selection with preset
            preset = self.config.get_date_preset()
            self.logger.info(f"Using date preset: {preset}")
            start_date, end_date = get_date_range()
        else:
            self.logger.info("Using custom date range from config")
            self.logger.info(f"Start: {start_date}")
            self.logger.info(f"End: {end_date}")

        # Load data once (shared across all strategies)
        self.logger.info("=" * 70)
        self.logger.info("LOADING DATA")
        self.logger.info("=" * 70)

        options_data, underlying_data = load_options_backtest_data(
            underlying_ticker=self.config.get_underlying_ticker(),
            start_date=start_date,
            end_date=end_date,
            min_dte=self.config.get_min_dte(),
            max_dte=self.config.get_max_dte(),
            verbose=self.config.is_verbose(),
            db_profile=self.config.get_db_profile(),
        )

        self.logger.info(f"Loaded {len(options_data):,} options bars")
        self.logger.info(f"Loaded {len(underlying_data):,} underlying bars")

        # Run backtests for each strategy
        results = []
        for strategy_config in strategies:
            strategy_name = strategy_config['name']
            strategy_params = strategy_config.get('params', {})

            result = self._run_single_backtest(
                strategy_name=strategy_name,
                strategy_params=strategy_params,
                underlying_data=underlying_data,
                options_data=options_data,
                start_date=start_date,
                end_date=end_date,
            )

            results.append(result)

        self.end_time = datetime.now()
        self.results = results

        # Print summary
        self._print_summary()

        return results

    def _print_summary(self) -> None:
        """Print summary of all backtests."""
        self.logger.info("=" * 70)
        self.logger.info(" " * 25 + "SUMMARY")
        self.logger.info("=" * 70)

        duration = self.end_time - self.start_time
        self.logger.info(f"Total Backtests: {len(self.results)}")
        self.logger.info(f"Total Duration: {duration}")

        for result in self.results:
            strategy_name = result['strategy_name']
            trades = result['results']['trades']
            equity = result['results']['equity_curve']

            total_trades = len(trades)
            # Handle empty equity curve
            if len(equity) > 0 and 'portfolio_value' in equity.columns:
                final_equity = equity['portfolio_value'].iloc[-1]
            elif len(equity) > 0 and 'equity' in equity.columns:
                final_equity = equity['equity'].iloc[-1]
            else:
                final_equity = self.config.get_initial_capital()

            total_return = final_equity - self.config.get_initial_capital()
            return_pct = (total_return / self.config.get_initial_capital()) * 100

            self.logger.info(f"Strategy: {strategy_name}")
            self.logger.info(f"  Total Trades: {total_trades}")
            self.logger.info(f"  Final Equity: ${final_equity:,.2f}")
            self.logger.info(f"  Total Return: ${total_return:,.2f} ({return_pct:+.2f}%)")

        self.logger.info("=" * 70)
