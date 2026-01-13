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
from pydantic import ValidationError

from quant_vibe.logging.unified_logging import get_logger

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quant_vibe.logging import setup_normalized_logging
from quant_vibe.messaging import RedisMessageBroker, Topic
from quant_vibe.models import OptionsBar
from quant_vibe.utils import (
    convert_string_columns_to_numeric,
    now_utc,
)


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
        mode: str = "live",
    ):
        """
        Initialize Redis data feed.

        Args:
            window_size: Number of bars to keep in memory
            callbacks: List of callback functions to call on new bars
            redis_host: Redis host (defaults to env var)
            redis_port: Redis port (defaults to env var)
            redis_db: Redis database (defaults to env var)
            mode: Data source mode - "live" for streaming, "replay" for testing
        """
        self.window_size = window_size
        self.callbacks = callbacks or []
        self.mode = mode

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

        # Message deduplication (track recent message IDs to avoid re-processing)
        # Use a set for O(1) lookup, paired with deque for FIFO cleanup
        self._recent_messages_set: set = set()
        self._recent_messages_queue: deque = deque(maxlen=1000)  # Keep last 1000 message IDs

        # Batching for callbacks (to avoid calling callback for every single bar)
        self._pending_bars: List[Dict] = []
        self._pending_bars_lock = threading.Lock()  # Thread safety for _pending_bars
        self._last_callback_time: Optional[datetime] = None
        # Optimized for replay: larger batches, no artificial delays
        # For replay at 100x speed, we want to process bars as fast as they arrive
        self._callback_batch_size = 100  # Flush after this many bars (increased for replay efficiency)
        self._callback_batch_interval_ms = 10  # Minimal delay to allow batching (reduced from 100ms)

        # Logging
        self.logger = get_logger('live_trading')

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
        if self.mode == "replay":
            topics = [Topic.REPLAY_OPTIONS_BARS, Topic.REPLAY_UNDERLYING_BARS]
            self.logger.info("Using REPLAY topics (replay.options_bars, replay.underlying_bars)")
        else:
            topics = [Topic.OPTIONS_BARS, Topic.UNDERLYING_BARS]
            self.logger.info("Using LIVE topics (streaming.options_bars, streaming.underlying_bars)")

        # Subscribe to topics with callback
        # The callback will be invoked by broker.get_message() automatically (broker.py:366-367)
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

        # Flush any remaining pending bars
        self._flush_batch()

        if self._thread:
            self._thread.join(timeout=2.0)

        self.broker.close()
        self.logger.info("RedisDataFeed stopped")

    def _listen_loop(self):
        """Main listening loop (runs in background thread)."""
        self.logger.info("Starting Redis listen loop...")
        message_poll_count = 0

        # Log every 5 seconds to prove loop is running
        import time
        last_log_time = time.time()

        try:
            while self._running:
                # Non-blocking get_message with very short timeout for replay speed
                # At 100x replay speed, we need to poll frequently to avoid delays
                result = self.broker.get_message(timeout=0.01)
                message_poll_count += 1

                # Log every 5 seconds to show we're alive
                current_time = time.time()
                if current_time - last_log_time >= 5.0:
                    self.logger.info(f"📊 Listen loop alive: {message_poll_count} polls, {self.message_count} messages received")
                    last_log_time = current_time

                # Check if we should flush (either got message or timeout with pending bars)
                with self._pending_bars_lock:
                    bar_count = len(self._pending_bars)

                # Flush if:
                # 1. Batch size reached (5 bars), OR
                # 2. Have pending bars and timeout elapsed
                should_flush_now = (
                    bar_count >= self._callback_batch_size or
                    (bar_count > 0 and not result)  # No new message, but have pending
                )

                if should_flush_now:
                    self._maybe_flush_batch()

        except Exception as e:
            self.logger.error(f"Error in Redis listener: {e}", exc_info=True)
            self._running = False
        finally:
            self.logger.info(f"Redis listen loop ended. Total polls: {message_poll_count}, messages: {self.message_count}")

    def _handle_message(self, topic: Topic, message_data: Dict):
        """Handle incoming message from Redis.

        Args:
            topic: Message topic
            message_data: Message payload
        """
        import threading

        self.message_count += 1
        self.last_update_time = now_utc()

        # Debug: Track which thread is calling this
        thread_name = threading.current_thread().name
        if self.message_count % 100 == 0:
            self.logger.debug(f"_handle_message called from thread '{thread_name}', total messages: {self.message_count}")

        try:
            if topic == Topic.OPTIONS_BARS or topic == Topic.REPLAY_OPTIONS_BARS:
                self._handle_option_bar(message_data)
            elif topic == Topic.UNDERLYING_BARS or topic == Topic.REPLAY_UNDERLYING_BARS:
                self._handle_underlying_bar(message_data)

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    def _handle_option_bar(self, bar_data: Dict):
        """Handle incoming option bar using Pydantic validation.

        Args:
            bar_data: Raw option bar data from Redis
        """
        # Create message ID for deduplication
        msg_id = f"{bar_data.get('contract_symbol', '')}@{bar_data.get('timestamp', '')}"

        # Debug: Show first few message IDs to verify deduplication
        if len(self._recent_messages_set) < 20:
            self.logger.info(f"📝 New message ID: {msg_id} (total unique: {len(self._recent_messages_set)})")

        # Skip if we've already processed this message recently
        if msg_id in self._recent_messages_set:
            self.logger.warning(f"⚠️  Skipping DUPLICATE option bar: {msg_id}")
            return

        # Add to both set (for fast lookup) and queue (for FIFO cleanup)
        self._recent_messages_set.add(msg_id)
        self._recent_messages_queue.append(msg_id)

        # Clean up set when queue evicts old items (queue is maxlen=1000)
        if len(self._recent_messages_queue) >= 1000:
            # Remove oldest items from set that are no longer in queue
            oldest_msg = self._recent_messages_queue[0]
            if oldest_msg in self._recent_messages_set and oldest_msg != msg_id:
                self._recent_messages_set.discard(oldest_msg)

        try:
            # Convert NaN values to None (pandas serialization issue)
            for key, value in bar_data.items():
                if pd.isna(value):
                    bar_data[key] = None

            # Validate with Pydantic model
            # This automatically:
            # - Enriches missing fields from contract_symbol
            # - Converts expiration_date to date object
            # - Normalizes contract_type to lowercase
            # - Ensures UTC-aware timestamps
            # - Validates OHLC constraints
            validated_bar = OptionsBar(**bar_data)

            # Convert back to dict for storage
            # Use mode='python' to convert Decimals to float for pandas compatibility
            bar = validated_bar.model_dump(mode='python')

            symbol = bar['contract_symbol']

            # Log first few bars
            if self.bars_received < 3:
                self.logger.info(f"✓ Validated bar: {symbol}")
                self.logger.info(f"  expiration_date: {bar['expiration_date']} (type: {type(bar['expiration_date'])})")
                self.logger.info(f"  contract_type: {bar['contract_type']}")
                self.logger.info(f"  strike_price: {bar['strike_price']}")
                if bar.get('mark'):
                    self.logger.info(f"  mark: ${float(bar['mark']):.2f}")

            # Add to deque
            self.option_bars[symbol].append(bar)
            self.bars_received += 1

            # Add to pending batch instead of calling callback immediately
            import traceback
            import threading

            bar_id = f"{bar.get('contract_symbol', 'unknown')}@{bar.get('timestamp', 'unknown')}"

            with self._pending_bars_lock:
                self._pending_bars.append(bar)
                # Don't flush immediately - let the listen loop handle flushing
                # to avoid recursive flushes while bars are still arriving

        except ValidationError as e:
            self.logger.warning(f"Bar validation failed: {e}")
        except Exception as e:
            self.logger.error(f"Error handling option bar: {e}", exc_info=True)

    def _handle_underlying_bar(self, bar: Dict):
        """Handle incoming underlying bar.

        Args:
            bar: Underlying bar data
        """
        # Get symbol (underlying bars use 'ticker' field)
        symbol = bar.get('ticker')

        # Create message ID for deduplication
        msg_id = f"{symbol or ''}@{bar.get('timestamp', '')}"

        # Skip if we've already processed this message recently
        if msg_id in self._recent_messages_set:
            self.logger.warning(f"⚠️  Skipping DUPLICATE underlying bar: {msg_id}")
            return

        # Add to both set (for fast lookup) and queue (for FIFO cleanup)
        self._recent_messages_set.add(msg_id)
        self._recent_messages_queue.append(msg_id)

        # Clean up set when queue evicts old items
        if len(self._recent_messages_queue) >= 1000:
            oldest_msg = self._recent_messages_queue[0]
            if oldest_msg in self._recent_messages_set and oldest_msg != msg_id:
                self._recent_messages_set.discard(oldest_msg)
        print(f"DEBUG [_handle_underlying_bar] Received bar for symbol: '{symbol}'")
        print(f"DEBUG   Bar data: {bar}")

        if not symbol:
            print("DEBUG   No symbol in bar, skipping")
            return

        # Normalize symbol (remove $ prefix if present)
        normalized_symbol = symbol.lstrip('$')
        if normalized_symbol != symbol:
            print(f"DEBUG   Normalized symbol: '{symbol}' -> '{normalized_symbol}'")

        # Add to deque (use normalized symbol)
        self.underlying_bars[normalized_symbol].append(bar)

        # Extract price from bar (prioritize close, fallback to bid/ask mid)
        close_price = bar.get('close')
        if close_price:
            # Convert to float if it's a string
            close_price = float(close_price) if isinstance(close_price, str) else close_price

        if not close_price:
            # Try to calculate from bid/ask
            bid = bar.get('bid')
            ask = bar.get('ask')
            # Convert to float if strings
            if bid:
                bid = float(bid) if isinstance(bid, str) else bid
            if ask:
                ask = float(ask) if isinstance(ask, str) else ask

            if bid and ask:
                close_price = (bid + ask) / 2
                print(f"DEBUG   Using bid/ask mid: ({bid} + {ask}) / 2 = {close_price:.2f}")
            elif bid:
                close_price = bid
                print(f"DEBUG   Using bid price: {bid:.2f}")
            elif ask:
                close_price = ask
                print(f"DEBUG   Using ask price: {ask:.2f}")

        # Update current price
        if close_price:
            self.underlying_prices[normalized_symbol] = close_price
            print(f"DEBUG   Updated underlying_prices['{normalized_symbol}'] = ${close_price:.2f}")
            print(f"DEBUG   All underlying_prices keys: {list(self.underlying_prices.keys())}")
        else:
            print("DEBUG   No price available in bar (close, bid, ask all None)")

        self.bars_received += 1

        # Add to pending batch instead of calling callback immediately
        with self._pending_bars_lock:
            self._pending_bars.append(bar)
            # Don't flush immediately - let the listen loop handle flushing

    def _maybe_flush_batch(self):
        """Flush pending bars to callbacks if batch interval has elapsed."""
        if not self._pending_bars:
            return

        current_time = now_utc()

        # Flush if: no previous callback, or interval elapsed
        should_flush = (
            self._last_callback_time is None or
            (current_time - self._last_callback_time).total_seconds() * 1000 >= self._callback_batch_interval_ms
        )

        if should_flush:
            self._flush_batch()

    def _flush_batch(self):
        """Flush all pending bars to callbacks."""
        # Acquire lock to safely copy and clear pending bars
        with self._pending_bars_lock:
            if not self._pending_bars:
                return

            bar_count = len(self._pending_bars)
            bars_to_send = self._pending_bars.copy()
            self._pending_bars.clear()
            self._last_callback_time = now_utc()

        if bar_count > 0:
            # Extract timestamps from batch for debugging
            timestamps = set()
            for bar in bars_to_send[:10]:  # Check first 10 bars
                ts = bar.get('timestamp')
                if ts:
                    # Convert to string for consistent comparison
                    timestamps.add(str(ts))

            if timestamps:
                sample_ts = sorted(timestamps)[0] if timestamps else "unknown"
                # self.logger.info(
                #     f"Flushing batch: {bar_count} bars, "
                #     f"{len(timestamps)} unique timestamps (first: {sample_ts})"
                # )
            else:
                self.logger.debug(f"Flushing batch of {bar_count} bars to callbacks")

        # Debug: Check if bars are re-added during callback (lock not needed for read)
        self._notify_callbacks(bars_to_send)

        with self._pending_bars_lock:
            pending_after = len(self._pending_bars)

        if pending_after > 0:
            self.logger.warning(
                f"⚠️  New bars arrived during callback processing: {pending_after} bars"
            )

    def _notify_callbacks(self, new_bars: List[Dict]):
        """Notify registered callbacks of new bars.

        Args:
            new_bars: List of new bars
        """
        # self.logger.debug(f"Notifying {len(self.callbacks)} callback(s) with {len(new_bars)} bars")

        for i, callback in enumerate(self.callbacks):
            try:
                # self.logger.debug(f"  Calling callback #{i+1}: {callback.__name__}")
                callback(new_bars)
                # self.logger.debug(f"  Callback #{i+1} completed")
            except Exception as e:
                self.logger.error(f"Error in callback #{i+1}: {e}", exc_info=True)

    def get_bars(self, symbol: Optional[str] = None, num_bars: Optional[int] = None) -> pd.DataFrame:
        """Get recent bars for a symbol.

        Args:
            symbol: Symbol to get bars for (None = all symbols)
            num_bars: Number of bars to return (None = all)

        Returns:
            DataFrame of bars
        """
        # If symbol is None, return all bars (options + underlying)
        if symbol is None:
            all_bars = []

            # Collect all option bars
            for sym, bars_deque in self.option_bars.items():
                all_bars.extend(list(bars_deque))

            # Collect all underlying bars
            for sym, bars_deque in self.underlying_bars.items():
                all_bars.extend(list(bars_deque))

            if not all_bars:
                return pd.DataFrame()

            df = pd.DataFrame(all_bars)

            # Convert string columns to numeric types (from Redis JSON deserialization)
            df = convert_string_columns_to_numeric(df)

            if num_bars and len(df) > num_bars:
                df = df.tail(num_bars)

            return df

        # Symbol specified - return bars for that symbol
        if symbol in self.option_bars:
            bars = list(self.option_bars[symbol])
        elif symbol in self.underlying_bars:
            bars = list(self.underlying_bars[symbol])
        else:
            return pd.DataFrame()

        if num_bars:
            bars = bars[-num_bars:]

        df = pd.DataFrame(bars)

        # Convert string columns to numeric types (from Redis JSON deserialization)
        df = convert_string_columns_to_numeric(df)

        return df

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
            # self.logger.debug("Data is stale: no updates received yet")
            return True

        elapsed = (now_utc() - self.last_update_time).total_seconds()
        is_stale = elapsed > timeout_seconds
        # self.logger.debug(f"Data staleness check: elapsed={elapsed:.1f}s, threshold={timeout_seconds}s, stale={is_stale}")
        return is_stale

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
