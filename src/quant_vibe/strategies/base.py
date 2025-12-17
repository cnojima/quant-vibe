"""Base strategy class."""

from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd


class Signal(Enum):
    """Trading signal types."""

    BUY = 1
    SELL = -1
    HOLD = 0


class Strategy(ABC):
    """Base class for trading strategies."""

    def __init__(self, name: str) -> None:
        """
        Initialize strategy.

        Args:
            name: Strategy name
        """
        self.name = name

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on market data.

        Args:
            data: Market data DataFrame with OHLCV columns

        Returns:
            Series of signals (BUY=1, SELL=-1, HOLD=0)
        """
        pass

    def validate_data(self, data: pd.DataFrame) -> None:
        """
        Validate that data has required columns.

        Args:
            data: Market data DataFrame

        Raises:
            ValueError: If required columns are missing
        """
        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = set(required) - set(data.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
