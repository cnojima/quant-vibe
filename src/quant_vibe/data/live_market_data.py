"""Live market data provider for trading engine.

Provides unified access to underlying asset bars and options snapshots
for live trading strategies. Acts as a data access layer that converts
streaming data into the DataFrame format expected by strategy executors.
"""

import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List, TYPE_CHECKING
from collections import deque, defaultdict

if TYPE_CHECKING:
    from ..live.data_feed import RealtimeDataFeed


class LiveMarketDataProvider:
    """
    Data access layer for live trading engine.

    Wraps RealtimeDataFeed and provides structured access to:
    - Historical underlying bars (for strategy analysis)
    - Current options chain snapshot (for spread construction)

    This class converts the streaming data format into pandas DataFrames
    that match the format used in backtesting.
    """

    def __init__(self, data_feed: "RealtimeDataFeed"):
        """
        Initialize market data provider.

        Args:
            data_feed: RealtimeDataFeed instance with streaming data
        """
        self.data_feed = data_feed

        # Track underlying bars separately for easy access
        # ticker -> deque of bars
        self.underlying_bars: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=data_feed.window_size)
        )

    def get_underlying_history(
        self,
        ticker: str = "SPX",
        lookback_bars: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get historical bars for underlying asset.

        This provides the OHLCV data needed for strategy analysis
        (calculating indicators, detecting trends, etc.).

        Args:
            ticker: Underlying ticker (default: SPX)
            lookback_bars: Number of recent bars to return (None = all available)

        Returns:
            DataFrame with columns:
                - timestamp: Bar timestamp
                - open, high, low, close: OHLC prices
                - volume: Trading volume
                - vwap: Volume-weighted average price (if available)

        Example:
            >>> provider = LiveMarketDataProvider(data_feed)
            >>> underlying = provider.get_underlying_history("SPX", lookback_bars=100)
            >>> # DataFrame with last 100 1-minute bars of SPX
        """
        # Get underlying price from data feed
        bars = self._build_underlying_bars_from_options(ticker)

        if not bars:
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'vwap'
            ])

        # Convert to DataFrame
        df = pd.DataFrame(bars)

        # Apply lookback limit
        if lookback_bars is not None and len(df) > lookback_bars:
            df = df.tail(lookback_bars).copy()

        # Ensure timestamp is datetime
        if 'timestamp' in df.columns and not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            # Convert timestamps, handling mixed formats
            # Use format='mixed' to suppress warnings about inconsistent formats
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, format='mixed')

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        return df

    def get_current_options_snapshot(
        self,
        underlying_ticker: str = "SPX"
    ) -> pd.DataFrame:
        """
        Get current snapshot of all options contracts.

        This provides the full options chain needed for spread construction
        (selecting strikes, checking liquidity, calculating Greeks, etc.).

        Args:
            underlying_ticker: Underlying ticker (default: SPX)

        Returns:
            DataFrame with columns:
                - timestamp: Bar timestamp
                - contract_symbol: Option contract symbol (e.g., SPXW251226C06875000)
                - underlying_ticker: Underlying ticker (SPX)
                - strike_price: Strike price
                - contract_type: 'call' or 'put' (lowercase, matches DB schema)
                - expiration_date: Expiration date
                - open, high, low, close: OHLC prices
                - volume: Trading volume
                - bid, ask, mark: Bid/ask prices and mark (midpoint)
                - bid_size, ask_size: Bid/ask sizes
                - delta, gamma, theta, vega, rho: Greeks
                - implied_volatility: IV

        Example:
            >>> provider = LiveMarketDataProvider(data_feed)
            >>> options = provider.get_current_options_snapshot("SPX")
            >>> # DataFrame with all active SPXW contracts and their latest bars
        """
        # Get all bars from data feed
        all_bars = self.data_feed.get_bars(symbol=None)

        if all_bars.empty:
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=[
                'timestamp', 'contract_symbol', 'underlying_ticker',
                'strike_price', 'contract_type', 'expiration_date',
                'open', 'high', 'low', 'close', 'volume', 'vwap',
                'bid', 'ask', 'mark', 'bid_size', 'ask_size',
                'delta', 'gamma', 'theta', 'vega', 'rho',
                'implied_volatility', 'transactions'
            ])

        # Filter by underlying ticker if needed
        if 'underlying_ticker' in all_bars.columns:
            all_bars = all_bars[all_bars['underlying_ticker'] == underlying_ticker].copy()

        # Rename option_ticker to contract_symbol for consistency with backtest data
        if not all_bars.empty and 'option_ticker' in all_bars.columns:
            all_bars = all_bars.rename(columns={'option_ticker': 'contract_symbol'})

        # Filter out underlying bars (keep only options bars)
        # Options bars should have expiration_date, strike_price, and contract_type
        if not all_bars.empty:
            # Keep only rows that have option-specific fields
            if 'strike_price' in all_bars.columns:
                all_bars = all_bars[all_bars['strike_price'].notna()].copy()

        # Get most recent bar for each contract (for snapshot)
        if not all_bars.empty and 'contract_symbol' in all_bars.columns:
            # Sort by timestamp to get latest
            all_bars = all_bars.sort_values('timestamp')

            # Get last bar for each symbol
            snapshot = all_bars.groupby('contract_symbol', as_index=False).last()
        else:
            snapshot = all_bars

        # Ensure timestamp is datetime
        if not snapshot.empty and 'timestamp' in snapshot.columns:
            if not pd.api.types.is_datetime64_any_dtype(snapshot['timestamp']):
                # Convert timestamps, handling mixed formats
                # Use format='mixed' to suppress warnings about inconsistent formats
                snapshot['timestamp'] = pd.to_datetime(snapshot['timestamp'], utc=True, format='mixed')

        return snapshot.reset_index(drop=True)

    def _build_underlying_bars_from_options(self, ticker: str) -> List[Dict]:
        """
        Build underlying bars from options data.

        When we don't have direct underlying data, we can derive it
        from the ATM options (at-the-money calls/puts should track
        the underlying price closely).

        Args:
            ticker: Underlying ticker

        Returns:
            List of bar dictionaries with OHLCV data
        """
        # Check if we have direct underlying price tracking
        underlying_prices = self.data_feed.underlying_prices.get(ticker)

        if underlying_prices:
            # We have direct price data - build bars from it
            # For now, return simple bars with the current price
            # In the future, we could aggregate these into proper OHLCV bars
            current_price = underlying_prices
            current_time = self.data_feed.last_update_time or datetime.now()

            return [{
                'timestamp': current_time,
                'open': current_price,
                'high': current_price,
                'low': current_price,
                'close': current_price,
                'volume': 0,
                'vwap': current_price,
            }]

        # Fallback: Get all options bars and extract underlying price
        options_df = self.data_feed.get_bars(symbol=None)

        if options_df.empty:
            return []

        # Group by timestamp and take median underlying price
        # (if we have it in the options data)
        if 'underlying_price' in options_df.columns:
            # Build bars from underlying_price field
            underlying_bars = (
                options_df.groupby('timestamp')
                .agg({
                    'underlying_price': ['first', 'max', 'min', 'last', 'median']
                })
                .reset_index()
            )

            underlying_bars.columns = ['timestamp', 'open', 'high', 'low', 'close', 'vwap']
            underlying_bars['volume'] = 0  # No volume data for underlying

            return underlying_bars.to_dict('records')

        # Last fallback: estimate from ATM options
        # This is less accurate but better than nothing
        bars = []
        for timestamp in options_df['timestamp'].unique():
            timestamp_data = options_df[options_df['timestamp'] == timestamp]

            # Get close prices of all options at this timestamp
            prices = timestamp_data['close'].dropna()

            if len(prices) > 0:
                # Simple aggregation (not perfect, but works as fallback)
                bars.append({
                    'timestamp': timestamp,
                    'open': float(prices.iloc[0]),
                    'high': float(prices.max()),
                    'low': float(prices.min()),
                    'close': float(prices.iloc[-1]),
                    'volume': 0,
                    'vwap': float(prices.median()),
                })

        return bars
