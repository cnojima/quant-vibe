"""MACD Histogram Momentum Strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_macd


class MACDHistogramStrategy(Strategy):
    """
    MACD Histogram Momentum Strategy.

    Generates BUY signal when histogram turns positive (crosses above zero).
    Generates SELL signal when histogram turns negative (crosses below zero).
    
    The histogram represents the difference between MACD and signal line,
    capturing momentum shifts earlier than the crossover strategy.
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        threshold: float = 0.0,
    ) -> None:
        """
        Initialize MACD histogram strategy.

        Args:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line EMA period (default: 9)
            threshold: Minimum histogram value to trigger signal (default: 0.0)
        """
        super().__init__(name=f"MACD_Hist_{fast_period}_{slow_period}_{signal_period}")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.threshold = threshold

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on MACD histogram.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate MACD
        _, _, histogram = calculate_macd(
            data["Close"],
            self.fast_period,
            self.slow_period,
            self.signal_period,
        )

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Generate signals based on histogram crossing zero
        above_threshold = histogram > self.threshold
        above_threshold_prev = above_threshold.shift(1)
        above_threshold_prev = above_threshold_prev.fillna(False).infer_objects(copy=False).astype(bool)
        
        # Buy when histogram crosses above threshold
        signals[above_threshold & ~above_threshold_prev] = Signal.BUY.value
        
        # Sell when histogram crosses below threshold
        signals[~above_threshold & above_threshold_prev] = Signal.SELL.value

        return signals
