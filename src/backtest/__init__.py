"""Backtesting framework for trading strategies.

This module provides a unified backtesting framework with:
- Options backtesting engine with realistic pricing and greeks
- Simple equity backtesting engine
- Performance metrics and detailed reporting
- Parameter optimization via grid search
- Walk-forward analysis for robustness testing
- Configuration-based orchestration

Components:
- orchestrator: BacktestOrchestrator for running configured strategies
- options_engine: OptionsBacktestEngine for options strategies
- simple_engine: BacktestEngine for simple equity strategies
- reporter: BacktestReporter for detailed analytics
- performance: PerformanceMetrics calculator
- parameter_optimizer: Grid search optimization
- walk_forward: Walk-forward validation
- config_loader: YAML configuration loading

Usage:
    # Run configured backtests
    python scripts/run_backtest.py
    python scripts/run_backtest.py --config config/my_backtest.yaml
    python scripts/run_backtest.py --strategy bullish_vertical_put

    # Optimize strategy parameters
    python scripts/optimize_strategy.py --strategy bullish_vertical_put
"""

from .orchestrator import BacktestOrchestrator
from .config_loader import BacktestConfig
from .options_engine import OptionsBacktestEngine
from .simple_engine import BacktestEngine
from .reporter import BacktestReporter
from .performance import PerformanceMetrics
from .parameter_optimizer import ParameterOptimizer
from .walk_forward import WalkForwardAnalysis

__all__ = [
    'BacktestOrchestrator',
    'BacktestConfig',
    'OptionsBacktestEngine',
    'BacktestEngine',
    'BacktestReporter',
    'PerformanceMetrics',
    'ParameterOptimizer',
    'WalkForwardAnalysis',
]
