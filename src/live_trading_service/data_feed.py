"""Real-time data feed consumer for live trading.

Consumes streaming data from schwabdev and maintains a sliding window
of recent bars for strategy execution.
"""

import sys
from pathlib import Path
import json
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Dict, List, Optional, Callable
import pandas as pd
import pytz

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from streaming_service.underlying_aggregator import UnderlyingBarAggregator
from .utils import setup_logging


class RealtimeDataFeed:
    """
    Manages real-time data feed from schwabdev stream.

    Maintains a sliding window of recent bars and notifies
    subscribers when new data arrives.
    """

    def __init__(
        self,
        window_size: int = 100,
        aggregate_interval_seconds: int = 60,
        callbacks: Optional[List[Callable]] = None
    ):
        """
        Initialize realtime data feed.

        Args:
            window_size: Number of bars to keep in memory (e.g., 100 = last 100 minutes)
            aggregate_interval_seconds: Bar aggregation interval (60 = 1min bars)
            callbacks: List of callback functions to call on new bar
        """
        self.window_size = window_size
        self.aggregate_interval = aggregate_interval_seconds
        self.callbacks = callbacks or []

        # Data storage
        # symbol -> deque of bars (most recent at end)
        self.bars: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))

        # Quote buffer for aggregation (same as in stream_spxw_schwabdev.py)
        self.quote_buffer: Dict[str, List[Dict]] = defaultdict(list)
        self.last_flush_time = datetime.now()

        # Underlying data tracking
        self.underlying_aggregator = UnderlyingBarAggregator(aggregate_interval_seconds)
        self.underlying_bars: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self.underlying_prices: Dict[str, float] = {}  # ticker -> price

        # Statistics
        self.message_count = 0
        self.bars_created = 0
        self.last_update_time: Optional[datetime] = None

        self.logger = setup_logging()

    def handle_message(self, message: str):
        """
        Handle incoming stream message (from schwabdev).

        This method should be passed as the callback to schwabdev streaming.

        Args:
            message: JSON string from stream
        """
        self.message_count += 1
        self.last_update_time = datetime.now()

        try:
            # Parse message (same logic as stream_spxw_schwabdev.py)
            msg_data = json.loads(message) if isinstance(message, str) else message

            if isinstance(msg_data, dict) and 'data' in msg_data:
                for data_item in msg_data['data']:
                    service = data_item.get('service', '')
                    content = data_item.get('content', [])

                    # Process level one options data
                    if service == 'LEVELONE_OPTIONS' and content:
                        timestamp = datetime.now()

                        for item in content:
                            symbol = item.get('key', '')
                            if not symbol:
                                continue

                            # Create quote record
                            quote = {
                                'timestamp': timestamp,
                                'symbol': symbol,
                                'bid': item.get('2'),
                                'ask': item.get('3'),
                                'last': item.get('4'),
                                'high': item.get('5'),
                                'low': item.get('6'),
                                'close': item.get('7'),
                                'volume': item.get('8'),
                                'open': item.get('15'),
                                'bid_size': item.get('16'),
                                'ask_size': item.get('17'),
                                'strike': item.get('20'),
                                'contract_type': item.get('21'),
                                'exp_year': item.get('12'),
                                'exp_month': item.get('23'),
                                'exp_day': item.get('26'),
                                'iv': item.get('10'),
                                'delta': item.get('28'),
                                'gamma': item.get('29'),
                                'theta': item.get('30'),
                                'vega': item.get('31'),
                                'rho': item.get('32'),
                                'underlying_price': item.get('35'),
                            }

                            # Track underlying price
                            if quote.get('underlying_price'):
                                self.underlying_prices['SPX'] = quote['underlying_price']

                            # Add to buffer
                            self.quote_buffer[symbol].append(quote)

            # Check if we should flush (create bars)
            elapsed = (datetime.now() - self.last_flush_time).total_seconds()
            if elapsed >= self.aggregate_interval:
                self._aggregate_and_flush()

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    def _aggregate_and_flush(self):
        """Aggregate buffered quotes into bars and notify callbacks."""

        if not self.quote_buffer:
            self.last_flush_time = datetime.now()
            return

        flush_timestamp = self.last_flush_time
        new_bars = []

        for symbol, quotes in self.quote_buffer.items():
            if not quotes:
                continue

            # Aggregate quotes into OHLC bar (same logic as stream script)
            prices = []
            for q in quotes:
                price = q.get('last')
                if price is None and q.get('bid') and q.get('ask'):
                    price = (q['bid'] + q['ask']) / 2.0
                if price:
                    prices.append(price)

            if not prices:
                continue

            # Calculate OHLC
            volumes = [q.get('volume', 0) for q in quotes if q.get('volume') is not None]
            max_volume = max(volumes) if volumes else 0

            # Calculate VWAP
            vwap = None
            price_volume_sum = 0.0
            total_volume_for_vwap = 0.0

            for i, q in enumerate(quotes):
                price = q.get('last')
                if price is None and q.get('bid') and q.get('ask'):
                    price = (q['bid'] + q['ask']) / 2.0

                volume = q.get('volume', 0)

                # Calculate incremental volume
                if i > 0 and volume is not None:
                    prev_volume = quotes[i-1].get('volume', 0)
                    if prev_volume is not None:
                        incremental_volume = volume - prev_volume
                    else:
                        incremental_volume = volume
                else:
                    incremental_volume = volume if volume is not None else 0

                if price and incremental_volume and incremental_volume > 0:
                    price_volume_sum += price * incremental_volume
                    total_volume_for_vwap += incremental_volume

            if total_volume_for_vwap > 0:
                vwap = price_volume_sum / total_volume_for_vwap

            # Get latest quote for contract details
            latest_quote = quotes[-1]

            # Build expiration date
            exp_date = None
            try:
                exp_year = latest_quote.get('exp_year')
                exp_month = latest_quote.get('exp_month')
                exp_day = latest_quote.get('exp_day')

                if exp_year and exp_month and exp_day:
                    exp_date = datetime(int(exp_year), int(exp_month), int(exp_day)).date()
            except (ValueError, TypeError):
                pass

            # Get contract type
            contract_type_raw = latest_quote.get('contract_type')
            if contract_type_raw:
                contract_type = 'call' if str(contract_type_raw).upper().startswith('C') else 'put'
            else:
                contract_type = 'call' if 'C' in symbol else 'put'

            bar = {
                'timestamp': flush_timestamp,
                'contract_symbol': symbol,
                'underlying_ticker': 'SPX',
                'open': prices[0],
                'high': max(prices),
                'low': min(prices),
                'close': prices[-1],
                'volume': max_volume,
                'vwap': vwap,
                'transactions': len(quotes),
                # Latest quote data
                'bid': latest_quote.get('bid'),
                'ask': latest_quote.get('ask'),
                'mark': (latest_quote.get('bid') + latest_quote.get('ask')) / 2.0
                        if latest_quote.get('bid') and latest_quote.get('ask') else None,
                'bid_size': latest_quote.get('bid_size'),
                'ask_size': latest_quote.get('ask_size'),
                # Contract details
                'strike_price': latest_quote.get('strike'),
                'contract_type': contract_type,  # lowercase 'call' or 'put' (matches DB schema)
                'expiration_date': exp_date,
                # Greeks
                'delta': latest_quote.get('delta'),
                'gamma': latest_quote.get('gamma'),
                'theta': latest_quote.get('theta'),
                'vega': latest_quote.get('vega'),
                'rho': latest_quote.get('rho'),
                'implied_volatility': latest_quote.get('iv'),
            }

            # Add to sliding window
            self.bars[symbol].append(bar)
            new_bars.append(bar)
            self.bars_created += 1

        # Notify callbacks with new bars
        if new_bars and self.callbacks:
            self._notify_callbacks(new_bars)

        # Clear buffer
        self.quote_buffer.clear()
        self.last_flush_time = datetime.now()

        self.logger.debug(f"Created {len(new_bars)} new bars | Total bars in memory: {sum(len(b) for b in self.bars.values())}")

    def _notify_callbacks(self, new_bars: List[Dict]):
        """Notify all registered callbacks of new bars."""
        for callback in self.callbacks:
            try:
                callback(new_bars)
            except Exception as e:
                self.logger.error(f"Error in callback {callback.__name__}: {e}", exc_info=True)

    def register_callback(self, callback: Callable):
        """
        Register a callback function to be called when new bars arrive.

        Callback signature: callback(new_bars: List[Dict])
        """
        self.callbacks.append(callback)
        self.logger.info(f"Registered callback: {callback.__name__}")

    def get_bars(
        self,
        symbol: Optional[str] = None,
        lookback: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get bars as a pandas DataFrame.

        Args:
            symbol: Specific symbol (None = all symbols)
            lookback: Number of recent bars (None = all in window)

        Returns:
            DataFrame with columns matching bar dict keys
        """
        if symbol:
            bars_list = list(self.bars[symbol])
            if lookback:
                bars_list = bars_list[-lookback:]
            return pd.DataFrame(bars_list)
        else:
            # All symbols
            all_bars = []
            for sym, bars in self.bars.items():
                bars_list = list(bars)
                if lookback:
                    bars_list = bars_list[-lookback:]
                all_bars.extend(bars_list)

            if not all_bars:
                return pd.DataFrame()

            df = pd.DataFrame(all_bars)
            df = df.sort_values('timestamp')
            return df

    def get_latest_bar(self, symbol: str) -> Optional[Dict]:
        """Get the most recent bar for a symbol."""
        if symbol in self.bars and len(self.bars[symbol]) > 0:
            return self.bars[symbol][-1]
        return None

    def get_underlying_price(self, ticker: str = 'SPX') -> Optional[float]:
        """Get the latest underlying price."""
        return self.underlying_prices.get(ticker)

    def get_options_at_time(
        self,
        timestamp: datetime,
        underlying_ticker: str = 'SPX'
    ) -> pd.DataFrame:
        """
        Get all options bars at a specific timestamp.

        Useful for strategy logic that needs the full options chain.

        Args:
            timestamp: Timestamp to query
            underlying_ticker: Underlying ticker

        Returns:
            DataFrame of all options at that timestamp
        """
        matching_bars = []

        for symbol, bars in self.bars.items():
            for bar in bars:
                if bar['timestamp'] == timestamp and bar['underlying_ticker'] == underlying_ticker:
                    matching_bars.append(bar)

        return pd.DataFrame(matching_bars)

    def is_data_stale(self, max_age_seconds: int = 300) -> bool:
        """
        Check if data is stale (no updates for too long).

        Args:
            max_age_seconds: Maximum age before considering stale (default: 5 minutes)

        Returns:
            True if data is stale
        """
        if self.last_update_time is None:
            return True

        age = (datetime.now() - self.last_update_time).total_seconds()
        return age > max_age_seconds

    def get_stats(self) -> Dict:
        """Get data feed statistics."""
        return {
            'message_count': self.message_count,
            'bars_created': self.bars_created,
            'symbols_tracked': len(self.bars),
            'total_bars_in_memory': sum(len(b) for b in self.bars.values()),
            'last_update_time': self.last_update_time,
            'data_stale': self.is_data_stale(),
            'underlying_prices': self.underlying_prices.copy()
        }

    def clear(self):
        """Clear all data (for testing or reset)."""
        self.bars.clear()
        self.quote_buffer.clear()
        self.underlying_prices.clear()
        self.message_count = 0
        self.bars_created = 0
        self.last_update_time = None
        self.logger.info("Data feed cleared")
