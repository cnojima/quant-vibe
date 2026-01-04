"""Integration tests for complete backtest workflow."""

import pandas as pd
import numpy as np
from backtest import BacktestEngine, PerformanceMetrics
from quant_vibe.strategies.base import Strategy, Signal


class SimpleBuyAndHold(Strategy):
    """Simple buy-and-hold strategy for testing."""

    def __init__(self):
        super().__init__("BuyAndHold")

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """Generate buy signal on first day, hold thereafter."""
        signals = pd.Series(Signal.HOLD.value, index=data.index)
        signals.iloc[0] = Signal.BUY.value  # Buy on first day
        return signals


def test_complete_backtest_workflow(sample_ohlcv_data):
    """Test complete workflow from strategy to performance analysis."""
    # Create simple test strategy
    strategy = SimpleBuyAndHold()

    # Run backtest
    engine = BacktestEngine(initial_capital=100000.0, commission=0.001)
    portfolio = engine.run(strategy, sample_ohlcv_data)

    # Verify portfolio has expected columns
    expected_columns = [
        "Price",
        "Signal",
        "Position",
        "Shares",
        "Holdings",
        "Cash",
        "Total",
        "Returns",
    ]
    assert all(col in portfolio.columns for col in expected_columns)

    # Calculate performance metrics
    metrics = PerformanceMetrics.calculate(portfolio)

    # Verify metrics
    assert "total_return" in metrics
    assert "sharpe_ratio" in metrics
    assert "max_drawdown" in metrics
    assert "volatility" in metrics
    assert "win_rate" in metrics

    # Verify metrics are reasonable
    assert -100 <= metrics["total_return"] <= 1000  # Between -100% and 1000%
    assert -10 <= metrics["sharpe_ratio"] <= 10  # Reasonable Sharpe ratio range
    assert -100 <= metrics["max_drawdown"] <= 0  # Drawdown should be negative
    assert 0 <= metrics["win_rate"] <= 100  # Win rate percentage
