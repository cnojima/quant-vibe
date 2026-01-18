"""Live market data provider for trading engine.

Provides unified access to underlying asset bars and options snapshots
for live trading strategies. Acts as a data access layer that converts
streaming data into the DataFrame format expected by strategy executors.
"""

import pandas as pd

from typing import Optional, Dict, List, TYPE_CHECKING
from collections import deque, defaultdict
from pydantic import ValidationError
from quant_vibe.logging.unified_logging import get_logger
from quant_vibe.utils.timestamp_utils import now_utc
from quant_vibe.utils.dataframe_utils import convert_string_columns_to_numeric

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
        self.logger = get_logger('streaming')

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

        # Convert string columns to numeric types (from Redis JSON deserialization)
        df = convert_string_columns_to_numeric(df)

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

        Uses Pydantic OptionsBar model for validation to ensure:
        - Type safety (expiration_date is date, not string/timestamp)
        - Schema consistency (contract_symbol, not option_ticker)
        - UTC-aware timestamps
        - Normalized symbols and contract types

        Args:
            underlying_ticker: Underlying ticker (default: SPX)

        Returns:
            DataFrame with columns:
                - timestamp: Bar timestamp (UTC-aware)
                - contract_symbol: Option contract symbol (e.g., SPXW251226C06875000)
                - underlying_ticker: Underlying ticker (SPX)
                - strike_price: Strike price
                - contract_type: 'call' or 'put' (lowercase, matches DB schema)
                - expiration_date: Expiration date (date object, not string)
                - open, high, low, close: OHLC prices
                - volume: Trading volume
                - bid, ask, mark: Bid/ask prices and mark (midpoint)
                - bid_size, ask_size: Bid/ask sizes
                - delta, gamma, theta, vega, rho: Greeks
                - implied_volatility: IV

                """
        # Get all bars from data feed
        all_bars = self.data_feed.get_bars(symbol=None)

        if all_bars.empty:
            self.logger.debug("No bars available from data feed")
            # Return empty DataFrame with expected columns
            return pd.DataFrame(columns=[
                'timestamp', 'contract_symbol', 'underlying_ticker',
                'strike_price', 'contract_type', 'expiration_date',
                'open', 'high', 'low', 'close', 'volume', 'vwap',
                'bid', 'ask', 'mark', 'bid_size', 'ask_size',
                'delta', 'gamma', 'theta', 'vega', 'rho',
                'implied_volatility', 'transactions'
            ])

        # Import OptionsBar at runtime to avoid circular import
        from quant_vibe.models import OptionsBar

        # Validate and normalize all bars using Pydantic OptionsBar model
        # This ensures:
        # - Correct types (expiration_date is date, not string)
        # - Schema consistency (contract_symbol, not option_ticker)
        # - UTC-aware timestamps
        # - Normalized symbols and contract types
        validated_bars = []
        validation_errors = 0

        for idx, row in all_bars.iterrows():
            try:
                # Convert DataFrame row to dict
                row_dict = row.to_dict()

                # Handle option_ticker -> contract_symbol renaming
                if 'option_ticker' in row_dict and 'contract_symbol' not in row_dict:
                    row_dict['contract_symbol'] = row_dict.pop('option_ticker')

                # Skip if no contract_symbol (underlying bars)
                if 'contract_symbol' not in row_dict or pd.isna(row_dict.get('contract_symbol')):
                    continue

                # Convert pandas NaN to None for optional fields
                # Pydantic rejects NaN but accepts None
                for key, value in row_dict.items():
                    if pd.isna(value):
                        row_dict[key] = None

                # Validate with Pydantic model
                # This automatically:
                # - Parses expiration_date from contract_symbol if missing
                # - Converts expiration_date to date object
                # - Normalizes contract_type to lowercase
                # - Ensures UTC-aware timestamps
                # - Validates OHLC constraints
                bar = OptionsBar(**row_dict)

                # Filter by underlying ticker
                if bar.underlying_ticker == underlying_ticker:
                    validated_bars.append(bar)

            except ValidationError as e:
                validation_errors += 1
                if validation_errors <= 5:  # Log first 5 errors
                    self.logger.warning(f"Bar validation failed for row {idx}: {e}")
            except Exception as e:
                validation_errors += 1
                if validation_errors <= 5:
                    self.logger.error(f"Unexpected error validating row {idx}: {e}")

        if validation_errors > 5:
            self.logger.warning(f"Total validation errors: {validation_errors} (showing first 5)")

        # Convert validated bars back to DataFrame
        if not validated_bars:
            self.logger.debug("No valid options bars after Pydantic validation")
            return pd.DataFrame(columns=[
                'timestamp', 'contract_symbol', 'underlying_ticker',
                'strike_price', 'contract_type', 'expiration_date',
                'open', 'high', 'low', 'close', 'volume', 'vwap',
                'bid', 'ask', 'mark', 'bid_size', 'ask_size',
                'delta', 'gamma', 'theta', 'vega', 'rho',
                'implied_volatility', 'transactions', 'data_source'
            ])

        # Convert to DataFrame
        # Use mode='python' to convert Decimals to float for pandas compatibility
        snapshot_df = pd.DataFrame([bar.model_dump(mode='python') for bar in validated_bars])

        # Ensure numeric columns are float (not Decimal)
        # This is needed because model_dump(mode='python') may not fully convert
        # nested Decimal objects in all edge cases
        from quant_vibe.utils.dataframe_utils import convert_decimals_to_float
        snapshot_df = convert_decimals_to_float(snapshot_df)

        # Get most recent bar for each contract (for snapshot)
        if 'contract_symbol' in snapshot_df.columns:
            # Sort by timestamp to get latest
            snapshot_df = snapshot_df.sort_values('timestamp')

            # Get last bar for each symbol
            snapshot = snapshot_df.groupby('contract_symbol', as_index=False).last()
        else:
            snapshot = snapshot_df

        # Calculate 'mark' price (midpoint of bid/ask) if not present or has NaN values
        if not snapshot.empty and 'bid' in snapshot.columns and 'ask' in snapshot.columns:
            # Create mark column if it doesn't exist
            if 'mark' not in snapshot.columns:
                snapshot['mark'] = None

            # Calculate mark for rows where it's missing or NaN
            mask = snapshot['mark'].isna()
            if mask.any():
                # Calculate from bid/ask where both are available
                has_both = snapshot['bid'].notna() & snapshot['ask'].notna()
                snapshot.loc[mask & has_both, 'mark'] = (
                    (snapshot.loc[mask & has_both, 'bid'] + snapshot.loc[mask & has_both, 'ask']) / 2.0
                )

                # Fallback to bid if no ask
                has_bid_only = snapshot['bid'].notna() & snapshot['ask'].isna()
                snapshot.loc[mask & has_bid_only, 'mark'] = snapshot.loc[mask & has_bid_only, 'bid']

                # Fallback to ask if no bid
                has_ask_only = snapshot['bid'].isna() & snapshot['ask'].notna()
                snapshot.loc[mask & has_ask_only, 'mark'] = snapshot.loc[mask & has_ask_only, 'ask']

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
            current_time = self.data_feed.last_update_time or now_utc()

            # print(f"DEBUG   Using direct price data: ${current_price:.2f} at {current_time}")

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
            print("DEBUG   No options data available - returning empty")
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
