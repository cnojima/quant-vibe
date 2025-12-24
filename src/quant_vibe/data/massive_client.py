"""
Massive API Client (formerly Polygon.io) - Options Data Integration

This module integrates with Massive's API for:
- Fetching historical options data
- Retrieving options chain data
- Getting options contracts information

Documentation: https://massive.com/docs

Setup Instructions:
==================
1. Register at https://massive.com/
2. Get your API key from the dashboard
3. Add to .env:
   MASSIVE_API_KEY=your_api_key_here

Note: This client focuses on options data endpoints.
Subscription level must include options data access.
"""

import os
from typing import Optional, List, Iterator
from datetime import datetime, date, timedelta
import pandas as pd
from dotenv import load_dotenv

from massive import RESTClient
from massive.rest.models import OptionsContract, Agg

load_dotenv()


class MassiveClient:
    """
    Client for Massive API integration for options data.

    This client provides access to options data including:
    - Options contracts
    - Historical options prices
    - Options chain data
    - Options snapshots
    """

    def __init__(self, api_key: Optional[str] = None, verbose: bool = False):
        """
        Initialize Massive API client.

        Args:
            api_key: Optional API key. If not provided, reads from .env
            verbose: Enable verbose logging
        """
        self.api_key = api_key or os.getenv("MASSIVE_API_KEY")

        if not self.api_key:
            raise ValueError(
                "API key required. Set MASSIVE_API_KEY in .env or pass to constructor."
            )

        self.client = RESTClient(api_key=self.api_key, verbose=verbose)

    def list_options_contracts(
        self,
        underlying_ticker: str,
        expiration_date: Optional[str] = None,
        expiration_date_gte: Optional[str] = None,
        expiration_date_lte: Optional[str] = None,
        contract_type: Optional[str] = None,
        strike_price: Optional[float] = None,
        strike_price_gte: Optional[float] = None,
        strike_price_lte: Optional[float] = None,
        expired: Optional[bool] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        List options contracts for an underlying symbol.

        Args:
            underlying_ticker: Underlying stock ticker (e.g., 'SPX', 'AAPL')
            expiration_date: Specific expiration date (YYYY-MM-DD)
            expiration_date_gte: Minimum expiration date (YYYY-MM-DD)
            expiration_date_lte: Maximum expiration date (YYYY-MM-DD)
            contract_type: Contract type ('call' or 'put')
            strike_price: Specific strike price
            strike_price_gte: Minimum strike price
            strike_price_lte: Maximum strike price
            expired: Filter for expired contracts (True/False)
            limit: Maximum number of results per page (default 1000)

        Returns:
            DataFrame with options contract data

        Example:
            >>> client = MassiveClient()
            >>> contracts = client.list_options_contracts(
            ...     "SPX",
            ...     expiration_date="2024-12-20",
            ...     contract_type="call"
            ... )
        """
        contracts: Iterator[OptionsContract] = self.client.list_options_contracts(
            underlying_ticker=underlying_ticker,
            expiration_date=expiration_date,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            contract_type=contract_type,
            strike_price=strike_price,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            expired=expired,
            limit=limit,
        )

        # Convert iterator to list of dicts
        contract_list = []
        for contract in contracts:
            contract_dict = {
                "ticker": contract.ticker,
                "underlying_ticker": contract.underlying_ticker,
                "expiration_date": contract.expiration_date,
                "strike_price": contract.strike_price,
                "contract_type": contract.contract_type,
            }

            # Add optional fields if they exist
            if hasattr(contract, "exercise_style"):
                contract_dict["exercise_style"] = contract.exercise_style
            if hasattr(contract, "shares_per_contract"):
                contract_dict["shares_per_contract"] = contract.shares_per_contract
            if hasattr(contract, "cfi"):
                contract_dict["cfi"] = contract.cfi
            if hasattr(contract, "primary_exchange"):
                contract_dict["primary_exchange"] = contract.primary_exchange

            contract_list.append(contract_dict)

        if not contract_list:
            return pd.DataFrame()

        df = pd.DataFrame(contract_list)

        # Sort by strike price if available
        if "strike_price" in df.columns:
            df = df.sort_values("strike_price")

        return df

    def get_option_chain(
        self,
        underlying_ticker: str,
        expiration_date: str,
        strike_min: Optional[float] = None,
        strike_max: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Get full options chain for a given expiration date.

        Args:
            underlying_ticker: Underlying stock ticker
            expiration_date: Expiration date in YYYY-MM-DD format
            strike_min: Minimum strike price filter
            strike_max: Maximum strike price filter

        Returns:
            DataFrame with options chain data (both calls and puts)

        Example:
            >>> client = MassiveClient()
            >>> chain = client.get_option_chain("SPX", "2024-12-20")
        """
        return self.list_options_contracts(
            underlying_ticker=underlying_ticker,
            expiration_date=expiration_date,
            strike_price_gte=strike_min,
            strike_price_lte=strike_max,
        )

    def get_option_bars(
        self,
        option_ticker: str,
        multiplier: int = 1,
        timespan: str = "day",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 5000,
        adjusted: bool = True,
    ) -> pd.DataFrame:
        """
        Get historical aggregate bars for an option contract.

        Args:
            option_ticker: Options ticker (e.g., 'O:SPX241220C04500000')
            multiplier: Size of timespan multiplier (e.g., 1 for 1 day)
            timespan: Timespan ('minute', 'hour', 'day', 'week', 'month', 'quarter', 'year')
            from_date: Start date (YYYY-MM-DD or datetime)
            to_date: End date (YYYY-MM-DD or datetime)
            limit: Maximum number of results (default 5000, max 50000)
            adjusted: Whether results are adjusted for splits

        Returns:
            DataFrame with OHLCV data for the option

        Example:
            >>> client = MassiveClient()
            >>> bars = client.get_option_bars(
            ...     "O:SPX241220C04500000",
            ...     from_date="2024-01-01",
            ...     to_date="2024-12-20"
            ... )
        """
        # Set default dates if not provided
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")
        if not from_date:
            from_dt = datetime.now() - timedelta(days=365)
            from_date = from_dt.strftime("%Y-%m-%d")

        # Get aggregates from Massive API
        aggs: List[Agg] = self.client.get_aggs(
            ticker=option_ticker,
            multiplier=multiplier,
            timespan=timespan,
            from_=from_date,
            to=to_date,
            adjusted=adjusted,
            limit=limit,
        )

        if not aggs:
            return pd.DataFrame()

        # Convert to list of dicts
        agg_list = []
        for agg in aggs:
            agg_dict = {
                "timestamp": agg.timestamp,
                "open": agg.open,
                "high": agg.high,
                "low": agg.low,
                "close": agg.close,
                "volume": agg.volume,
            }

            # Add optional fields if they exist
            if hasattr(agg, "vwap"):
                agg_dict["vwap"] = agg.vwap
            if hasattr(agg, "transactions"):
                agg_dict["transactions"] = agg.transactions

            agg_list.append(agg_dict)

        df = pd.DataFrame(agg_list)

        # Convert timestamp to datetime
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.set_index("timestamp")

        # Capitalize standard OHLCV columns
        rename_map = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        df = df.rename(columns=rename_map)

        return df

    def get_index_bars(
        self,
        index_ticker: str = "I:SPX",
        multiplier: int = 1,
        timespan: str = "minute",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50000,
        adjusted: bool = True,
    ) -> pd.DataFrame:
        """
        Get historical aggregate bars for an index (e.g., SPX).

        Args:
            index_ticker: Index ticker (default: 'I:SPX' for S&P 500)
                         Use 'I:' prefix for indices in Polygon/Massive API
            multiplier: Size of timespan multiplier (e.g., 1 for 1 minute)
            timespan: Timespan ('minute', 'hour', 'day', 'week', 'month')
            from_date: Start date (YYYY-MM-DD or datetime)
            to_date: End date (YYYY-MM-DD or datetime)
            limit: Maximum number of results (default 50000)
            adjusted: Whether results are adjusted for splits

        Returns:
            DataFrame with OHLCV data for the index
            Columns: Open, High, Low, Close, Volume
            Index: timestamp (datetime)

        Example:
            >>> client = MassiveClient()
            >>> # Get 1-minute SPX bars for a specific day
            >>> bars = client.get_index_bars(
            ...     index_ticker="I:SPX",
            ...     multiplier=1,
            ...     timespan="minute",
            ...     from_date="2025-12-23",
            ...     to_date="2025-12-23"
            ... )
        """
        # Set default dates if not provided
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")
        if not from_date:
            from_dt = datetime.now() - timedelta(days=7)
            from_date = from_dt.strftime("%Y-%m-%d")

        # Get aggregates from Massive API
        aggs: List[Agg] = self.client.get_aggs(
            ticker=index_ticker,
            multiplier=multiplier,
            timespan=timespan,
            from_=from_date,
            to=to_date,
            adjusted=adjusted,
            limit=limit,
        )

        if not aggs:
            return pd.DataFrame()

        # Convert to list of dicts
        agg_list = []
        for agg in aggs:
            agg_dict = {
                "timestamp": agg.timestamp,
                "open": agg.open,
                "high": agg.high,
                "low": agg.low,
                "close": agg.close,
                "volume": agg.volume if hasattr(agg, 'volume') else 0,
            }

            # Add optional fields if they exist
            if hasattr(agg, "vwap"):
                agg_dict["vwap"] = agg.vwap
            if hasattr(agg, "transactions"):
                agg_dict["transactions"] = agg.transactions

            agg_list.append(agg_dict)

        df = pd.DataFrame(agg_list)

        # Convert timestamp to datetime
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.set_index("timestamp")

        # Capitalize standard OHLCV columns
        rename_map = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        df = df.rename(columns=rename_map)

        return df

    def get_snapshot_option(self, underlying_ticker: str, option_ticker: str) -> dict:
        """
        Get snapshot data for a specific option contract.

        Args:
            underlying_ticker: Underlying stock ticker (e.g., 'AAPL')
            option_ticker: Specific option contract ticker (e.g., 'O:AAPL241220C00150000')

        Returns:
            Dictionary with snapshot data including greeks, implied volatility, etc.

        Example:
            >>> client = MassiveClient()
            >>> snapshot = client.get_snapshot_option("AAPL", "O:AAPL241220C00150000")
        """
        result = self.client.get_snapshot_option(
            underlying_ticker=underlying_ticker, option_contract=option_ticker
        )

        # Convert to dict if it's an object
        if hasattr(result, "__dict__"):
            return result.__dict__
        return result

    def get_snapshot_options_chain(
        self, underlying_ticker: str, strike_price: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Get snapshot data for an entire options chain.

        Args:
            underlying_ticker: Underlying stock ticker
            strike_price: Optional strike price filter

        Returns:
            DataFrame with snapshot data for all contracts in the chain

        Example:
            >>> client = MassiveClient()
            >>> chain = client.get_snapshot_options_chain("AAPL")
        """
        params = {}
        if strike_price is not None:
            params["strike_price"] = strike_price

        results = self.client.list_snapshot_options_chain(
            underlying_ticker=underlying_ticker, params=params
        )

        # Convert results to DataFrame
        snapshot_list = []
        for snapshot in results:
            snapshot_dict = {}
            if hasattr(snapshot, "__dict__"):
                snapshot_dict = snapshot.__dict__
            else:
                snapshot_dict = dict(snapshot)
            snapshot_list.append(snapshot_dict)

        if not snapshot_list:
            return pd.DataFrame()

        return pd.DataFrame(snapshot_list)

    def search_options_by_date_range(
        self,
        underlying_ticker: str,
        start_date: str,
        end_date: str,
        contract_type: Optional[str] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Search for options contracts within a date range.

        Args:
            underlying_ticker: Underlying stock ticker
            start_date: Minimum expiration date (YYYY-MM-DD)
            end_date: Maximum expiration date (YYYY-MM-DD)
            contract_type: Optional contract type ('call' or 'put')
            limit: Maximum results per page

        Returns:
            DataFrame with matching contracts

        Example:
            >>> client = MassiveClient()
            >>> # Get all SPX contracts expiring in next 30 days
            >>> today = datetime.now().strftime("%Y-%m-%d")
            >>> future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            >>> contracts = client.search_options_by_date_range("SPX", today, future)
        """
        return self.list_options_contracts(
            underlying_ticker=underlying_ticker,
            expiration_date_gte=start_date,
            expiration_date_lte=end_date,
            contract_type=contract_type,
            limit=limit,
        )
