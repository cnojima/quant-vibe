"""Exponential Moving Average crossover strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_ema


class EMACrossoverStrategy(Strategy):
    """
    Exponential Moving Average crossover strategy.

    Generates BUY signal when fast EMA crosses above slow EMA.
    Generates SELL signal when fast EMA crosses below slow EMA.
    
    More responsive than SMA crossover due to exponential weighting.
    """

    def __init__(self, fast_period: int = 12, slow_period: int = 26) -> None:
        """
        Initialize EMA crossover strategy.

        Args:
            fast_period: Period for fast moving average (default: 12)
            slow_period: Period for slow moving average (default: 26)
        """
        super().__init__(name=f"EMA_{fast_period}_{slow_period}")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on EMA crossover.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate moving averages
        fast_ema = calculate_ema(data["Close"], self.fast_period)
        slow_ema = calculate_ema(data["Close"], self.slow_period)

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Generate crossover signals
        crossover = fast_ema > slow_ema
        crossover_prev = crossover.shift(1)
        crossover_prev = crossover_prev.astype('object').fillna(False).astype(bool)
        
        signals[crossover & ~crossover_prev] = Signal.BUY.value
        signals[~crossover & crossover_prev] = Signal.SELL.value

        return signals
