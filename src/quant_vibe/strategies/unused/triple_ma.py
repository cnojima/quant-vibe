"""Triple Moving Average Strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_sma


class TripleMAStrategy(Strategy):
    """
    Triple Moving Average Strategy.

    Uses three moving averages to identify strong trends:
    - BUY: When short > medium > long (all aligned bullish)
    - SELL: When short < medium < long (all aligned bearish)
    
    This strategy waits for all three MAs to align before signaling,
    reducing false signals during choppy markets.
    """

    def __init__(
        self,
        short_period: int = 5,
        medium_period: int = 20,
        long_period: int = 50,
    ) -> None:
        """
        Initialize triple MA strategy.

        Args:
            short_period: Period for short moving average (default: 5)
            medium_period: Period for medium moving average (default: 20)
            long_period: Period for long moving average (default: 50)
        """
        super().__init__(name=f"TripleMA_{short_period}_{medium_period}_{long_period}")
        self.short_period = short_period
        self.medium_period = medium_period
        self.long_period = long_period

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on triple MA alignment.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate moving averages
        short_ma = calculate_sma(data["Close"], self.short_period)
        medium_ma = calculate_sma(data["Close"], self.medium_period)
        long_ma = calculate_sma(data["Close"], self.long_period)

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Check current and previous alignment
        bullish_aligned = (short_ma > medium_ma) & (medium_ma > long_ma)
        bearish_aligned = (short_ma < medium_ma) & (medium_ma < long_ma)
        
        bullish_aligned_prev = bullish_aligned.shift(1)
        bullish_aligned_prev = bullish_aligned_prev.fillna(False).infer_objects(copy=False).astype(bool)
        bearish_aligned_prev = bearish_aligned.shift(1)
        bearish_aligned_prev = bearish_aligned_prev.fillna(False).infer_objects(copy=False).astype(bool)

        # Generate signals on alignment change
        signals[bullish_aligned & ~bullish_aligned_prev] = Signal.BUY.value
        signals[bearish_aligned & ~bearish_aligned_prev] = Signal.SELL.value

        return signals
