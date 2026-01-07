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

        # Logging
        self.logger = setup_normalized_logging(
            app_name="redis_data_feed",
            log_dir="logs/live_trading",
        )

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
                # Non-blocking get_message with short timeout
                result = self.broker.get_message(timeout=0.1)
                message_poll_count += 1

                # Log every 5 seconds to show we're alive
                current_time = time.time()
                if current_time - last_log_time >= 5.0:
                    self.logger.info(f"📊 Listen loop alive: {message_poll_count} polls, {self.message_count} messages received")
                    last_log_time = current_time

                if result:
                    topic, message_data = result
                    # NOTE: get_message() already called the callback (line 267 in broker.py)
                    # But we call it again here to ensure it's processed
                    # TODO: Fix this double-call issue
                    self._handle_message(topic, message_data)

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
        self.message_count += 1
        self.last_update_time = now_utc()

        try:
            if topic == Topic.OPTIONS_BARS:
                self._handle_option_bar(message_data)
            elif topic == Topic.UNDERLYING_BARS:
                self._handle_underlying_bar(message_data)

        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    def _handle_option_bar(self, bar_data: Dict):
        """Handle incoming option bar using Pydantic validation.

        Args:
            bar_data: Raw option bar data from Redis
        """
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

            # Notify callbacks
            self._notify_callbacks([bar])

        except ValidationError as e:
            self.logger.warning(f"Bar validation failed: {e}")
        except Exception as e:
            self.logger.error(f"Error handling option bar: {e}", exc_info=True)

    def _handle_underlying_bar(self, bar: Dict):
        """Handle incoming underlying bar.

        Args:
            bar: Underlying bar data
        """
        symbol = bar.get('underlying_ticker')
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
        if not close_price:
            # Try to calculate from bid/ask
            bid = bar.get('bid')
            ask = bar.get('ask')
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
            self.logger.debug("Data is stale: no updates received yet")
            return True

        elapsed = (now_utc() - self.last_update_time).total_seconds()
        is_stale = elapsed > timeout_seconds
        self.logger.debug(f"Data staleness check: elapsed={elapsed:.1f}s, threshold={timeout_seconds}s, stale={is_stale}")
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
