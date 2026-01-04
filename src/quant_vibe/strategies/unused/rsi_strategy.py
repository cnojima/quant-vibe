"""RSI Mean Reversion Strategy - Template for Learning.

This strategy buys when RSI indicates oversold conditions
and sells when RSI indicates overbought conditions.

Learning objectives:
- Understand RSI indicator
- Implement entry/exit logic
- Handle signal generation
"""

import pandas as pd
from .base import Strategy, Signal
from ..indicators import calculate_rsi


class RSIStrategy(Strategy):
    """
    RSI Mean Reversion Strategy.
    
    Buy Signal: RSI < oversold_threshold (default: 30)
    Sell Signal: RSI > overbought_threshold (default: 70)
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold_threshold: int = 30,
        overbought_threshold: int = 70,
    ) -> None:
        """
        Initialize RSI strategy.

        Args:
            rsi_period: Period for RSI calculation (default: 14)
            oversold_threshold: RSI level to trigger buy (default: 30)
            overbought_threshold: RSI level to trigger sell (default: 70)
        """
        super().__init__(name=f"RSI_{rsi_period}_{oversold_threshold}_{overbought_threshold}")
        self.rsi_period = rsi_period
        self.oversold = oversold_threshold
        self.overbought = overbought_threshold

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on RSI levels.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate RSI
        rsi = calculate_rsi(data["Close"], self.rsi_period)

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Generate signals
        # TODO: Fill in the logic!
        # Hint: Use boolean indexing
        # signals[condition] = Signal.BUY.value
        # signals[condition] = Signal.SELL.value
        
        # Buy when RSI crosses below oversold threshold
        signals[rsi < self.oversold] = Signal.BUY.value
        
        # Sell when RSI crosses above overbought threshold  
        signals[rsi > self.overbought] = Signal.SELL.value

        return signals
