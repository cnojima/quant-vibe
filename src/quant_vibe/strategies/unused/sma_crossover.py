"""Simple Moving Average crossover strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_sma


class SMACrossoverStrategy(Strategy):
    """
    Simple Moving Average crossover strategy.

    Generates BUY signal when fast SMA crosses above slow SMA.
    Generates SELL signal when fast SMA crosses below slow SMA.
    """

    def __init__(self, fast_period: int = 50, slow_period: int = 200) -> None:
        """
        Initialize SMA crossover strategy.

        Args:
            fast_period: Period for fast moving average
            slow_period: Period for slow moving average
        """
        super().__init__(name=f"SMA_{fast_period}_{slow_period}")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on SMA crossover.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate moving averages
        fast_sma = calculate_sma(data["Close"], self.fast_period)
        slow_sma = calculate_sma(data["Close"], self.slow_period)

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Generate crossover signals
        crossover = fast_sma > slow_sma
        crossover_prev = crossover.shift(1).fillna(False).infer_objects(copy=False)
        
        signals[crossover & ~crossover_prev] = Signal.BUY.value
        signals[~crossover & crossover_prev] = Signal.SELL.value

        return signals
