"""Market data fetching client."""

import os
from typing import Optional
from datetime import datetime

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


class MarketDataClient:
    """Client for fetching market data from various sources."""

    def __init__(self, provider: str = "alpha_vantage") -> None:
        """
        Initialize market data client.

        Args:
            provider: Data provider to use ('alpha_vantage', 'polygon', etc.)
        """
        self.provider = provider
        self._api_key: Optional[str] = None
        self._load_credentials()

    def _load_credentials(self) -> None:
        """Load API credentials from environment."""
        if self.provider == "alpha_vantage":
            self._api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        elif self.provider == "polygon":
            self._api_key = os.getenv("POLYGON_API_KEY")
        elif self.provider == "massive":
            self._api_key = os.getenv("MASSIVE_API_KEY")
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def fetch_daily_data(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV data for a symbol.

        Args:
            symbol: Stock ticker symbol
            start_date: Start date for data range
            end_date: End date for data range

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
        """
        if self.provider == "alpha_vantage":
            return self._fetch_alpha_vantage_daily(symbol)
        else:
            raise NotImplementedError(f"Provider {self.provider} not implemented")

    def _fetch_alpha_vantage_daily(self, symbol: str) -> pd.DataFrame:
        """Fetch daily data from Alpha Vantage."""
        if not self._api_key:
            raise ValueError("Alpha Vantage API key not set")

        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "full",
            "apikey": self._api_key,
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if "Time Series (Daily)" not in data:
            raise ValueError(f"Failed to fetch data for {symbol}: {data}")

        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.rename(
            columns={
                "1. open": "Open",
                "2. high": "High",
                "3. low": "Low",
                "4. close": "Close",
                "5. volume": "Volume",
            }
        )
        df = df.astype(float)
        df = df.sort_index()

        return df
