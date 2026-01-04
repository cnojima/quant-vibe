"""Simple Moving Average crossover strategy with delayed entry.

This strategy waits for confirmation before executing trades,
reducing false signals and whipsaws.
"""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_sma


class SMACrossoverDelayedStrategy(Strategy):
    """
    Simple Moving Average crossover strategy with delayed entry.

    Generates BUY signal when fast SMA crosses above slow SMA
    and remains above for the delay period.
    
    Generates SELL signal when fast SMA crosses below slow SMA
    and remains below for the delay period.
    
    The delay helps filter out false signals and whipsaws.
    """

    def __init__(
        self, 
        fast_period: int = 50, 
        slow_period: int = 200,
        delay_periods: int = 5
    ) -> None:
        """
        Initialize SMA crossover strategy with delay.

        Args:
            fast_period: Period for fast moving average
            slow_period: Period for slow moving average
            delay_periods: Number of periods to wait before confirming signal
                         (e.g., 5 for 5-minute bars = 5 minutes delay,
                          or 1 for 5-minute bars = 5 minutes delay)
        """
        super().__init__(name=f"SMA_Delayed_{fast_period}_{slow_period}_{delay_periods}")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.delay_periods = delay_periods

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on SMA crossover with delay.

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

        # Determine crossover direction
        # True when fast > slow (bullish)
        crossover = fast_sma > slow_sma
        
        # Detect initial crossover points
        crossover_prev = crossover.shift(1).fillna(False).infer_objects(copy=False)
        
        # Bullish crossover (fast crosses above slow)
        bullish_cross = crossover & ~crossover_prev
        
        # Bearish crossover (fast crosses below slow)
        bearish_cross = ~crossover & crossover_prev
        
        # Apply delay: only signal if condition persists for delay_periods
        for i in range(self.delay_periods, len(data)):
            # Check if we had a bullish crossover delay_periods ago
            if bullish_cross.iloc[i - self.delay_periods]:
                # Verify that fast > slow for the entire delay period
                all_bullish = all(crossover.iloc[i - self.delay_periods + j] 
                                 for j in range(self.delay_periods + 1))
                if all_bullish:
                    signals.iloc[i] = Signal.BUY.value
            
            # Check if we had a bearish crossover delay_periods ago
            if bearish_cross.iloc[i - self.delay_periods]:
                # Verify that fast < slow for the entire delay period
                all_bearish = all(not crossover.iloc[i - self.delay_periods + j] 
                                 for j in range(self.delay_periods + 1))
                if all_bearish:
                    signals.iloc[i] = Signal.SELL.value

        return signals
