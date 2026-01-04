"""RSI with Moving Average Filter Strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_rsi, calculate_sma


class RSIMAFilterStrategy(Strategy):
    """
    RSI Mean Reversion with Moving Average Trend Filter.

    Only takes positions in the direction of the trend:
    - BUY: RSI oversold AND price above MA (uptrend)
    - SELL: RSI overbought AND price below MA (downtrend)
    
    This reduces false signals by ensuring we trade with the trend.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold_threshold: int = 30,
        overbought_threshold: int = 70,
        ma_period: int = 200,
    ) -> None:
        """
        Initialize RSI with MA filter strategy.

        Args:
            rsi_period: Period for RSI calculation (default: 14)
            oversold_threshold: RSI level to trigger buy (default: 30)
            overbought_threshold: RSI level to trigger sell (default: 70)
            ma_period: Period for trend-filtering MA (default: 200)
        """
        super().__init__(
            name=f"RSI_MA_Filter_{rsi_period}_{oversold_threshold}_{overbought_threshold}_{ma_period}"
        )
        self.rsi_period = rsi_period
        self.oversold = oversold_threshold
        self.overbought = overbought_threshold
        self.ma_period = ma_period

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on RSI with MA filter.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate indicators
        rsi = calculate_rsi(data["Close"], self.rsi_period)
        ma = calculate_sma(data["Close"], self.ma_period)

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Determine trend
        price_above_ma = data["Close"] > ma
        price_below_ma = data["Close"] < ma

        # Generate signals (only in trend direction)
        # Buy when RSI oversold AND in uptrend
        signals[(rsi < self.oversold) & price_above_ma] = Signal.BUY.value

        # Sell when RSI overbought AND in downtrend
        signals[(rsi > self.overbought) & price_below_ma] = Signal.SELL.value

        return signals
