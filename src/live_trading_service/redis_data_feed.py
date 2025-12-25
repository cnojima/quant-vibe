"""Redis-based data feed consumer for live trading.

Consumes streaming data from Redis pub/sub (published by StreamingService)
instead of creating a separate schwabdev connection.
"""

import sys
import threading
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque
from typing import Dict, List, Optional, Callable

import pandas as pd

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quant_vibe.messaging import RedisMessageBroker, Topic
from .utils import setup_logging


class RedisDataFeed:
    """
    Consumes market data from Redis pub/sub.

    Subscribes to StreamingService messages and maintains a sliding window
    of recent bars for strategy execution.
    """

    def __init__(
        self,
        window_size: int = 100,
        callbacks: Optional[List[Callable]] = None,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        redis_db: Optional[int] = None,
    ):
        """
        Initialize Redis data feed.

        Args:
            window_size: Number of bars to keep in memory
            callbacks: List of callback functions to call on new bars
            redis_host: Redis host (defaults to env var)
            redis_port: Redis port (defaults to env var)
            redis_db: Redis database (defaults to env var)
        """
        self.window_size = window_size
        self.callbacks = callbacks or []

        # Data storage
        # symbol -> deque of bars (most recent at end)
        self.option_bars: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self.underlying_bars: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))

        # Current prices
        self.underlying_prices: Dict[str, float] = {}  # ticker -> price

        # Statistics
        self.message_count = 0
        self.bars_received = 0
        self.last_update_time: Optional[datetime] = None

        # Logging
        self.logger = setup_logging()

        # Message broker
        self.broker = RedisMessageBroker(
            host=redis_host,
            port=redis_port,
            db=redis_db,
        )

        # Subscription thread
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.logger.info("RedisDataFeed initialized")

    def start(self):
        """Start consuming messages from Redis."""
        if self._running:
            self.logger.warning("RedisDataFeed already running")
            return

        self._running = True

        # Subscribe to topics
        self.broker.subscribe(
            topics=[Topic.OPTIONS_BARS, Topic.UNDERLYING_BARS],
            callback=self._handle_message
        )

        # Start listener thread
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        self.logger.info("RedisDataFeed started - listening for messages")

    def stop(self):
        """Stop consuming messages."""
        if not self._running:
            return

        self._running = False

        if self._thread:
            self._thread.join(timeout=2.0)

        self.broker.close()
        self.logger.info("RedisDataFeed stopped")

    def _listen_loop(self):
        """Main listening loop (runs in background thread)."""
        try:
            while self._running:
                # Non-blocking get_message with short timeout
                result = self.broker.get_message(timeout=0.1)

                if result:
                    topic, message_data = result
                    # Message already handled by callback in subscribe()
                    # This loop just keeps the thread alive

        except Exception as e:
            self.logger.error(f"Error in Redis listener: {e}", exc_info=True)
            self._running = False

    def _handle_message(self, topic: Topic, message_data: Dict):
        """Handle incoming message from Redis.

        Args:
            topic: Message topic
            message_data: Message payload
        """
        self.message_count += 1
        self.last_update_time = datetime.now()

        try:
            if topic == Topic.OPTIONS_BARS:
                self._handle_option_bar(message_data)
            elif topic == Topic.UNDERLYING_BARS:
                self._handle_underlying_bar(message_data)

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    def _handle_option_bar(self, bar: Dict):
        """Handle incoming option bar.

        Args:
            bar: Option bar data
        """
        symbol = bar.get('option_ticker')
        if not symbol:
            return

        # Add to deque
        self.option_bars[symbol].append(bar)
        self.bars_received += 1

        # Notify callbacks
        self._notify_callbacks([bar])

    def _handle_underlying_bar(self, bar: Dict):
        """Handle incoming underlying bar.

        Args:
            bar: Underlying bar data
        """
        symbol = bar.get('underlying_ticker')
        if not symbol:
            return

        # Add to deque
        self.underlying_bars[symbol].append(bar)

        # Update current price
        close_price = bar.get('close')
        if close_price:
            self.underlying_prices[symbol] = close_price

        self.bars_received += 1

        # Notify callbacks
        self._notify_callbacks([bar])

    def _notify_callbacks(self, new_bars: List[Dict]):
        """Notify registered callbacks of new bars.

        Args:
            new_bars: List of new bars
        """
        for callback in self.callbacks:
            try:
                callback(new_bars)
            except Exception as e:
                self.logger.error(f"Error in callback: {e}", exc_info=True)

    def get_bars(self, symbol: str, num_bars: Optional[int] = None) -> pd.DataFrame:
        """Get recent bars for a symbol.

        Args:
            symbol: Symbol to get bars for
            num_bars: Number of bars to return (None = all)

        Returns:
            DataFrame of bars
        """
        # Check option bars first
        if symbol in self.option_bars:
            bars = list(self.option_bars[symbol])
        elif symbol in self.underlying_bars:
            bars = list(self.underlying_bars[symbol])
        else:
            return pd.DataFrame()

        if num_bars:
            bars = bars[-num_bars:]

        return pd.DataFrame(bars)

    def get_underlying_price(self, ticker: str) -> Optional[float]:
        """Get current underlying price.

        Args:
            ticker: Underlying ticker (e.g., 'SPX')

        Returns:
            Current price or None
        """
        return self.underlying_prices.get(ticker)

    def is_data_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if data is stale.

        Args:
            timeout_seconds: Timeout threshold (default: 5 minutes)

        Returns:
            True if data hasn't been received in timeout_seconds
        """
        if not self.last_update_time:
            return True

        elapsed = (datetime.now() - self.last_update_time).total_seconds()
        return elapsed > timeout_seconds

    def get_stats(self) -> Dict:
        """Get feed statistics.

        Returns:
            Dictionary of statistics
        """
        return {
            'message_count': self.message_count,
            'bars_received': self.bars_received,
            'option_symbols_tracked': len(self.option_bars),
            'underlying_symbols_tracked': len(self.underlying_bars),
            'data_stale': self.is_data_stale(),
            'last_update': self.last_update_time.isoformat() if self.last_update_time else None,
        }
