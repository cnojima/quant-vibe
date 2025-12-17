"""Multi-Timeframe RSI Strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_rsi


class MultiRSIStrategy(Strategy):
    """
    Multi-Timeframe RSI Strategy.

    Uses multiple RSI periods to confirm signals:
    - BUY: All RSI values < oversold threshold
    - SELL: All RSI values > overbought threshold
    
    This requires multiple timeframes to agree, reducing false signals.
    """

    def __init__(
        self,
        rsi_periods: tuple = (7, 14, 21),
        oversold_threshold: int = 30,
        overbought_threshold: int = 70,
    ) -> None:
        """
        Initialize Multi-RSI strategy.

        Args:
            rsi_periods: Tuple of RSI periods to use (default: (7, 14, 21))
            oversold_threshold: RSI level to trigger buy (default: 30)
            overbought_threshold: RSI level to trigger sell (default: 70)
        """
        periods_str = "_".join(map(str, rsi_periods))
        super().__init__(
            name=f"MultiRSI_{periods_str}_{oversold_threshold}_{overbought_threshold}"
        )
        self.rsi_periods = rsi_periods
        self.oversold = oversold_threshold
        self.overbought = overbought_threshold

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on multiple RSI timeframes.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate RSI for each period
        rsi_values = []
        for period in self.rsi_periods:
            rsi = calculate_rsi(data["Close"], period)
            rsi_values.append(rsi)

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Check if all RSI values are oversold
        all_oversold = pd.Series(True, index=data.index)
        for rsi in rsi_values:
            all_oversold &= rsi < self.oversold

        # Check if all RSI values are overbought
        all_overbought = pd.Series(True, index=data.index)
        for rsi in rsi_values:
            all_overbought &= rsi > self.overbought

        # Generate signals
        signals[all_oversold] = Signal.BUY.value
        signals[all_overbought] = Signal.SELL.value

        return signals
