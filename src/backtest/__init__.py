"""Top-level backtesting orchestration layer.

This module provides a unified interface for running backtests with configuration-based
strategy execution, similar to the live trading engine.

Components:
- engine: BacktestOrchestrator for running configured strategies
- config_loader: Configuration file loading and validation
- runner: CLI runner for executing backtests

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --config config/my_backtest.yaml
    python scripts/run_backtest.py --strategy bullish_vertical_put
"""

from .engine import BacktestOrchestrator
from .config_loader import BacktestConfig

__all__ = [
    'BacktestOrchestrator',
    'BacktestConfig',
]
