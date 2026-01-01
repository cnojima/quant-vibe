"""Analytics module for trading performance analysis.

This module provides tools for analyzing trading performance:
- Slippage analysis (backtest vs actual fills)
- Performance attribution
- Risk metrics
"""

from quant_vibe.analytics.slippage_analyzer import SlippageAnalyzer

__all__ = ['SlippageAnalyzer']
