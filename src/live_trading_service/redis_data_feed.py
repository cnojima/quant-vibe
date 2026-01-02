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
import math

import pandas as pd

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quant_vibe.messaging import RedisMessageBroker, Topic
from quant_vibe.utils import (
    parse_expiration_from_ticker,
    parse_contract_type_from_ticker,
    normalize_option_ticker,
)
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
            self.logger.warning(f"Option bar missing 'option_ticker': {list(bar.keys())[:10]}")
            return

        # Debug: Log first bar to see what fields we're getting
        if self.bars_received == 0:
            self.logger.info(f"First option bar received: {list(bar.keys())}")
            self.logger.info(f"  Symbol: {symbol}")
            self.logger.info(f"  Has expiration_date: {'expiration_date' in bar}")
            self.logger.info(f"  expiration_date value: {bar.get('expiration_date')}")
            self.logger.info(f"  Has contract_type: {'contract_type' in bar}")
            self.logger.info(f"  contract_type value: {bar.get('contract_type')}")
            self.logger.info(f"  Has strike_price: {'strike_price' in bar}")

        # Enrich bar with missing fields by parsing from symbol
        # This handles cases where remote streaming service doesn't enrich data
        needs_enrichment = False

        # Normalize symbol for parsing (remove spaces)
        normalized_symbol = normalize_option_ticker(symbol)

        # Check expiration_date (handle None, nan, and missing)
        exp_value = bar.get('expiration_date')

        # Log what we're checking
        if self.bars_received < 3:
            self.logger.info(f"Checking expiration_date: in_bar={'expiration_date' in bar}, value={exp_value}, type={type(exp_value)}")
            self.logger.info(f"  Normalized symbol: {normalized_symbol}")

        # Use pd.isna() which handles all types of missing values
        if 'expiration_date' not in bar or pd.isna(exp_value):
            expiration = parse_expiration_from_ticker(normalized_symbol)
            if expiration:
                # Convert to pd.Timestamp for consistency with strategy comparisons
                bar['expiration_date'] = pd.Timestamp(expiration)
                needs_enrichment = True
                if self.bars_received < 3:  # Log first few
                    self.logger.info(f"✓ Enriched expiration_date: {normalized_symbol} -> {expiration}")
            else:
                if self.bars_received < 3:
                    self.logger.warning(f"Failed to parse expiration_date from symbol: {normalized_symbol}")

        # Check contract_type (handle None, nan, and missing)
        ct_value = bar.get('contract_type')

        # Log what we're checking
        if self.bars_received < 3:
            self.logger.info(f"Checking contract_type: in_bar={'contract_type' in bar}, value={ct_value}, type={type(ct_value)}")

        # Use pd.isna() which handles all types of missing values
        if 'contract_type' not in bar or pd.isna(ct_value):
            contract_type = parse_contract_type_from_ticker(normalized_symbol)
            if contract_type:
                bar['contract_type'] = contract_type
                needs_enrichment = True
                if self.bars_received < 3:  # Log first few
                    self.logger.info(f"✓ Enriched contract_type: {normalized_symbol} -> {contract_type}")
            else:
                if self.bars_received < 3:
                    self.logger.warning(f"Failed to parse contract_type from symbol: {normalized_symbol}")

        if needs_enrichment and self.bars_received == 0:
            self.logger.info(f"Enriched bar now has: expiration_date={bar.get('expiration_date')}, contract_type={bar.get('contract_type')}")

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
            self.logger.debug("Data is stale: no updates received yet")
            return True

        elapsed = (datetime.now() - self.last_update_time).total_seconds()
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
