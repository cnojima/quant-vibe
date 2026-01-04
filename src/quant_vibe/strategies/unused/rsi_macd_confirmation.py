"""RSI + MACD Confirmation Strategy."""

import pandas as pd

from .base import Strategy, Signal
from ..indicators import calculate_rsi, calculate_macd


class RSIMACDConfirmationStrategy(Strategy):
    """
    RSI + MACD Confirmation Strategy.

    Requires both indicators to agree before signaling:
    - BUY: RSI < oversold AND MACD crosses above signal line
    - SELL: RSI > overbought AND MACD crosses below signal line
    
    This dual confirmation reduces false signals significantly.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold_threshold: int = 30,
        overbought_threshold: int = 70,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
    ) -> None:
        """
        Initialize RSI + MACD confirmation strategy.

        Args:
            rsi_period: Period for RSI calculation (default: 14)
            oversold_threshold: RSI level to trigger buy (default: 30)
            overbought_threshold: RSI level to trigger sell (default: 70)
            macd_fast: Fast EMA period for MACD (default: 12)
            macd_slow: Slow EMA period for MACD (default: 26)
            macd_signal: Signal line period for MACD (default: 9)
        """
        super().__init__(
            name=f"RSI_MACD_Confirm_{rsi_period}_{oversold_threshold}_{overbought_threshold}"
        )
        self.rsi_period = rsi_period
        self.oversold = oversold_threshold
        self.overbought = overbought_threshold
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on RSI + MACD confirmation.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        self.validate_data(data)

        # Calculate RSI
        rsi = calculate_rsi(data["Close"], self.rsi_period)

        # Calculate MACD
        macd_line, signal_line, _ = calculate_macd(
            data["Close"],
            self.macd_fast,
            self.macd_slow,
            self.macd_signal,
        )

        # Initialize signals
        signals = pd.Series(Signal.HOLD.value, index=data.index)

        # Detect MACD crossovers
        macd_above_signal = macd_line > signal_line
        macd_above_signal_prev = macd_above_signal.shift(1)
        macd_above_signal_prev = macd_above_signal_prev.fillna(False).infer_objects(copy=False).astype(bool)
        
        macd_bullish_cross = macd_above_signal & ~macd_above_signal_prev
        macd_bearish_cross = ~macd_above_signal & macd_above_signal_prev

        # Generate signals requiring both conditions
        # Buy: RSI oversold AND MACD bullish crossover
        signals[macd_bullish_cross & (rsi < self.oversold)] = Signal.BUY.value

        # Sell: RSI overbought AND MACD bearish crossover
        signals[macd_bearish_cross & (rsi > self.overbought)] = Signal.SELL.value

        return signals
