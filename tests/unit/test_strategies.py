"""Tests for trading strategies."""

import pytest
import pandas as pd

from quant_vibe.strategies import SMACrossoverStrategy
from quant_vibe.strategies.base import Signal


def test_sma_crossover_strategy(sample_ohlcv_data):
    """Test SMA crossover strategy signal generation."""
    strategy = SMACrossoverStrategy(fast_period=10, slow_period=20)
    signals = strategy.generate_signals(sample_ohlcv_data)

    assert len(signals) == len(sample_ohlcv_data)
    # Signals should only contain valid values
    assert set(signals.unique()).issubset({Signal.BUY.value, Signal.SELL.value, Signal.HOLD.value})


def test_sma_crossover_buy_signal():
    """Test that BUY signal is generated on upward crossover."""
    # Create data with clear upward trend
    dates = pd.date_range(start="2023-01-01", periods=50, freq="D")
    prices = pd.Series(range(100, 150), index=dates)

    data = pd.DataFrame(
        {
            "Open": prices,
            "High": prices + 1,
            "Low": prices - 1,
            "Close": prices,
            "Volume": 1000000,
        }
    )

    strategy = SMACrossoverStrategy(fast_period=5, slow_period=10)
    signals = strategy.generate_signals(data)

    # Should have at least one BUY signal
    assert (signals == Signal.BUY.value).any()


def test_sma_crossover_sell_signal():
    """Test that SELL signal is generated on downward crossover."""
    # Create data that goes up then down
    dates = pd.date_range(start="2023-01-01", periods=50, freq="D")
    prices_up = list(range(100, 125))
    prices_down = list(range(124, 99, -1))
    prices = pd.Series(prices_up + prices_down, index=dates)

    data = pd.DataFrame(
        {
            "Open": prices,
            "High": prices + 1,
            "Low": prices - 1,
            "Close": prices,
            "Volume": 1000000,
        }
    )

    strategy = SMACrossoverStrategy(fast_period=5, slow_period=10)
    signals = strategy.generate_signals(data)

    # Should have at least one SELL signal
    assert (signals == Signal.SELL.value).any()


def test_strategy_validate_data():
    """Test that strategy validates required columns."""
    strategy = SMACrossoverStrategy()

    # Missing required columns
    invalid_data = pd.DataFrame({"Price": [100, 101, 102]})

    with pytest.raises(ValueError, match="Missing required columns"):
        strategy.generate_signals(invalid_data)
