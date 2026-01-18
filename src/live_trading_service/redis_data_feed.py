"""Redis-based data feed consumer for live trading."""

import sys
import time
import threading
from pathlib import Path
from datetime import datetime
from collections import defaultdict, deque
from typing import Dict, List, Optional, Callable

import pandas as pd
from pydantic import ValidationError

from quant_vibe.logging.unified_logging import get_logger
from quant_vibe.messaging import RedisMessageBroker, Topic
from quant_vibe.models import OptionsBar
from quant_vibe.utils import calculate_mark_price, convert_string_columns_to_numeric, now_utc

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class RedisDataFeed:
    """Consumes market data from Redis pub/sub."""

    def __init__(
        self,
        window_size: int = 100,
        callbacks: Optional[List[Callable]] = None,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        redis_db: Optional[int] = None,
        mode: str = "live",
    ):
        """Initialize Redis data feed.

        Args:
            window_size: Number of bars to keep in memory
            callbacks: List of callback functions for new bars
            redis_host: Redis host
            redis_port: Redis port
            redis_db: Redis database
            mode: Data source mode ('live' or 'replay')
        """
        self.window_size = window_size
        self.callbacks = callbacks or []
        self.mode = mode
        self.logger = get_logger('live_trading')

        # Data storage
        self.option_bars: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self.underlying_bars: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
        self.underlying_prices: Dict[str, float] = {}

        # Statistics
        self.message_count = 0
        self.bars_received = 0
        self.last_update_time: Optional[datetime] = None

        # Message deduplication
        self._recent_messages_set: set = set()
        self._recent_messages_queue: deque = deque(maxlen=1000)

        # Batching for callbacks
        self._pending_bars: List[Dict] = []
        self._pending_bars_lock = threading.Lock()
        self._last_callback_time: Optional[datetime] = None
        self._callback_batch_size = 100
        self._callback_batch_interval_ms = 10

        # Message broker
        self.broker = RedisMessageBroker(
            host=redis_host,
            port=redis_port,
            db=redis_db,
        )

        # Subscription thread
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.logger.info(f"RedisDataFeed initialized (mode: {mode})")

    def start(self):
        """Start consuming messages from Redis."""
        if self._running:
            self.logger.warning("RedisDataFeed already running")
            return

        self._running = True

        # Select topics based on mode
        topics = self._get_topics()
        self.logger.info(f"Using {self.mode.upper()} topics: {topics}")

        # Subscribe to topics
        self.broker.subscribe(
            topics=topics,
            callback=self._handle_message
        )

        # Start listener thread
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

        self.logger.info(f"RedisDataFeed started - listening for messages (mode: {self.mode})")

    def stop(self):
        """Stop consuming messages."""
        if not self._running:
            return

        self._running = False
        self._flush_batch()

        if self._thread:
            self._thread.join(timeout=2.0)

        self.broker.close()
        self.logger.info("RedisDataFeed stopped")

    def _get_topics(self) -> List[Topic]:
        """Get topics based on mode."""
        if self.mode == "replay":
            return [Topic.REPLAY_OPTIONS_BARS, Topic.REPLAY_UNDERLYING_BARS]
        return [Topic.OPTIONS_BARS, Topic.UNDERLYING_BARS]

    def _listen_loop(self):
        """Main listening loop (runs in background thread)."""
        self.logger.info("Starting Redis listen loop...")
        message_poll_count = 0
        last_log_time = time.time()

        try:
            while self._running:
                # Non-blocking get_message with short timeout
                result = self.broker.get_message(timeout=0.01)
                message_poll_count += 1

                # Periodic status log
                current_time = time.time()
                if current_time - last_log_time >= 5.0:
                    self.logger.info(
                        f"Listen loop alive: {message_poll_count} polls, "
                        f"{self.message_count} messages received"
                    )
                    last_log_time = current_time

                # Check if we should flush batch
                with self._pending_bars_lock:
                    bar_count = len(self._pending_bars)

                should_flush = (
                    bar_count >= self._callback_batch_size or
                    (bar_count > 0 and not result)
                )

                if should_flush:
                    self._maybe_flush_batch()

        except Exception as e:
            self.logger.error(f"Error in Redis listener: {e}", exc_info=True)
            self._running = False
        finally:
            self.logger.info(
                f"Redis listen loop ended. Total polls: {message_poll_count}, "
                f"messages: {self.message_count}"
            )

    def _handle_message(self, topic: Topic, message_data: Dict):
        """Handle incoming message from Redis."""
        self.message_count += 1
        self.last_update_time = now_utc()

        try:
            if topic in [Topic.OPTIONS_BARS, Topic.REPLAY_OPTIONS_BARS]:
                self._handle_option_bar(message_data)
            elif topic in [Topic.UNDERLYING_BARS, Topic.REPLAY_UNDERLYING_BARS]:
                self._handle_underlying_bar(message_data)
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    def _handle_option_bar(self, bar_data: Dict):
        """Handle incoming option bar."""
        # Create message ID for deduplication
        msg_id = f"{bar_data.get('option_ticker', '')}@{bar_data.get('timestamp', '')}"

        # Skip duplicate messages
        if msg_id in self._recent_messages_set:
            self.logger.warning(f"Skipping duplicate option bar: {msg_id}")
            return

        # Track message for deduplication
        self._track_message(msg_id)

        try:
            # Clean NaN values
            for key, value in bar_data.items():
                if pd.isna(value):
                    bar_data[key] = None

            # Validate with Pydantic model
            validated_bar = OptionsBar(**bar_data)
            bar = validated_bar.model_dump(mode='python')

            symbol = bar['option_ticker']
            self.option_bars[symbol].append(bar)
            self.bars_received += 1

            # Add to pending batch
            with self._pending_bars_lock:
                self._pending_bars.append(bar)

        except ValidationError as e:
            self.logger.warning(f"Bar validation failed: {e}")
        except Exception as e:
            self.logger.error(f"Error handling option bar: {e}", exc_info=True)

    def _handle_underlying_bar(self, bar: Dict):
        """Handle incoming underlying bar."""
        symbol = bar.get('ticker')
        if not symbol:
            return

        # Create message ID for deduplication
        msg_id = f"{symbol}@{bar.get('timestamp', '')}"

        # Skip duplicate messages
        if msg_id in self._recent_messages_set:
            self.logger.warning(f"Skipping duplicate underlying bar: {msg_id}")
            return

        # Track message for deduplication
        self._track_message(msg_id)

        # Normalize symbol
        normalized_symbol = symbol.lstrip('$')

        # Store bar
        self.underlying_bars[normalized_symbol].append(bar)

        # Extract and store price
        price = self._extract_price(bar)
        if price:
            self.underlying_prices[normalized_symbol] = price

        self.bars_received += 1

        # Add to pending batch
        with self._pending_bars_lock:
            self._pending_bars.append(bar)

    def _track_message(self, msg_id: str):
        """Track message for deduplication."""
        self._recent_messages_set.add(msg_id)
        self._recent_messages_queue.append(msg_id)

        # Clean up old messages from set
        if len(self._recent_messages_queue) >= 1000:
            oldest_msg = self._recent_messages_queue[0]
            if oldest_msg in self._recent_messages_set and oldest_msg != msg_id:
                self._recent_messages_set.discard(oldest_msg)

    def _extract_price(self, bar: Dict) -> Optional[float]:
        """Extract price from bar data."""
        # Try close price first
        price = bar.get('close')
        if price:
            return float(price) if isinstance(price, str) else price

        # Fall back to bid/ask mid
        bid = bar.get('bid')
        ask = bar.get('ask')

        if bid:
            bid = float(bid) if isinstance(bid, str) else bid
        if ask:
            ask = float(ask) if isinstance(ask, str) else ask

        # Use utility function for mark calculation with fallback
        mark = calculate_mark_price(bid, ask)
        if mark > 0:
            return mark

        # Fallback to bid or ask if mark is zero
        if bid is not None and not pd.isna(bid):
            return bid
        if ask is not None and not pd.isna(ask):
            return ask
        return 0.0  # Always return a valid float

    def _maybe_flush_batch(self):
        """Flush pending bars if interval has elapsed."""
        if not self._pending_bars:
            return

        current_time = now_utc()
        should_flush = (
            self._last_callback_time is None or
            (current_time - self._last_callback_time).total_seconds() * 1000 >= self._callback_batch_interval_ms
        )

        if should_flush:
            self._flush_batch()

    def _flush_batch(self):
        """Flush all pending bars to callbacks."""
        with self._pending_bars_lock:
            if not self._pending_bars:
                return

            bars_to_send = self._pending_bars.copy()
            self._pending_bars.clear()
            self._last_callback_time = now_utc()

        self._notify_callbacks(bars_to_send)

    def _notify_callbacks(self, new_bars: List[Dict]):
        """Notify registered callbacks of new bars."""
        for callback in self.callbacks:
            try:
                callback(new_bars)
            except Exception as e:
                self.logger.error(f"Error in callback: {e}", exc_info=True)

    def get_bars(self, symbol: Optional[str] = None, num_bars: Optional[int] = None) -> pd.DataFrame:
        """Get recent bars for a symbol."""
        if symbol is None:
            # Return all bars
            all_bars = []
            for bars_deque in self.option_bars.values():
                all_bars.extend(list(bars_deque))
            for bars_deque in self.underlying_bars.values():
                all_bars.extend(list(bars_deque))

            if not all_bars:
                return pd.DataFrame()

            df = pd.DataFrame(all_bars)
            df = convert_string_columns_to_numeric(df)

            if num_bars and len(df) > num_bars:
                df = df.tail(num_bars)

            return df

        # Return bars for specific symbol
        if symbol in self.option_bars:
            bars = list(self.option_bars[symbol])
        elif symbol in self.underlying_bars:
            bars = list(self.underlying_bars[symbol])
        else:
            return pd.DataFrame()

        if num_bars:
            bars = bars[-num_bars:]

        df = pd.DataFrame(bars)
        return convert_string_columns_to_numeric(df)

    def get_underlying_price(self, ticker: str) -> Optional[float]:
        """Get current underlying price."""
        return self.underlying_prices.get(ticker)

    def is_data_stale(self, timeout_seconds: int = 300) -> bool:
        """Check if data is stale."""
        if not self.last_update_time:
            return True

        elapsed = (now_utc() - self.last_update_time).total_seconds()
        return elapsed > timeout_seconds

    def get_stats(self) -> Dict:
        """Get feed statistics."""
        return {
            'message_count': self.message_count,
            'bars_received': self.bars_received,
            'option_symbols_tracked': len(self.option_bars),
            'underlying_symbols_tracked': len(self.underlying_bars),
            'data_stale': self.is_data_stale(),
            'last_update': self.last_update_time.isoformat() if self.last_update_time else None,
        }