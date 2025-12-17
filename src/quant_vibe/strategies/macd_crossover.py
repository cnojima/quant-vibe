"""MACD Crossover Strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_macd


class MACDCrossoverStrategy(Strategy):
    """
    MACD Crossover Strategy.

    Generates BUY signal when MACD line crosses above signal line.
    Generates SELL signal when MACD line crosses below signal line.
    
    MACD is a trend-following momentum indicator.
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        """
        Initialize MACD crossover strategy.

        Args:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line EMA period (default: 9)
        """
        super().__init__(name=f"MACD_{fast_period}_{slow_period}_{signal_period}")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on MACD crossover.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate MACD
        macd_line, signal_line, _ = calculate_macd(
            data["Close"],
            self.fast_period,
            self.slow_period,
            self.signal_period,
        )

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Generate crossover signals
        crossover = macd_line > signal_line
        crossover_prev = crossover.shift(1)
        crossover_prev = crossover_prev.fillna(False).infer_objects(copy=False).astype(bool)
        
        signals[crossover & ~crossover_prev] = Signal.BUY.value
        signals[~crossover & crossover_prev] = Signal.SELL.value

        return signals
