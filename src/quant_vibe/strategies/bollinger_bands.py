"""Bollinger Bands Mean Reversion Strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_bollinger_bands


class BollingerBandsStrategy(Strategy):
    """
    Bollinger Bands Mean Reversion Strategy.

    BUY: When price touches or crosses below the lower band (oversold)
    SELL: When price touches or crosses above the upper band (overbought)
    
    Bollinger Bands expand and contract with volatility, making them
    adaptive to market conditions.
    """

    def __init__(
        self,
        period: int = 20,
        num_std: float = 2.0,
    ) -> None:
        """
        Initialize Bollinger Bands strategy.

        Args:
            period: Period for moving average (default: 20)
            num_std: Number of standard deviations for bands (default: 2.0)
        """
        super().__init__(name=f"BB_{period}_{num_std}")
        self.period = period
        self.num_std = num_std

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on Bollinger Bands.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate Bollinger Bands
        upper_band, middle_band, lower_band = calculate_bollinger_bands(
            data["Close"],
            self.period,
            self.num_std,
        )

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Generate signals based on band touches
        # Buy when price touches lower band (oversold)
        price_below_lower = data["Close"] <= lower_band
        price_below_lower_prev = price_below_lower.shift(1)
        price_below_lower_prev = price_below_lower_prev.fillna(False).infer_objects(copy=False).astype(bool)
        
        # Sell when price touches upper band (overbought)
        price_above_upper = data["Close"] >= upper_band
        price_above_upper_prev = price_above_upper.shift(1)
        price_above_upper_prev = price_above_upper_prev.fillna(False).infer_objects(copy=False).astype(bool)

        # Signal on new touches
        signals[price_below_lower & ~price_below_lower_prev] = Signal.BUY.value
        signals[price_above_upper & ~price_above_upper_prev] = Signal.SELL.value

        return signals
