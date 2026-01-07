"""Bar aggregation logic for underlying asset (SPX) quotes."""

from collections import defaultdict
from typing import Dict, List, Optional, TYPE_CHECKING
from decimal import Decimal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from quant_vibe.utils import now_utc

if TYPE_CHECKING:
    from quant_vibe.models import UnderlyingBar


class UnderlyingBarAggregator:
    """Aggregates underlying asset (SPX) streaming quotes into OHLCV bars.

    Buffers incoming quote updates and periodically aggregates them into
    1-minute (or configurable interval) OHLCV bars for storage in underlying_bars table.
    """

    def __init__(self, aggregate_interval_seconds: int = 60):
        """Initialize underlying bar aggregator.

        Args:
            aggregate_interval_seconds: Seconds to aggregate into bars (default: 60 = 1-min)
        """
        self.aggregate_interval = aggregate_interval_seconds
        self.quote_buffer: Dict[str, List[Dict]] = defaultdict(list)
        self.last_flush_time = now_utc()

    def add_quote(self, quote: Dict):
        """Add an underlying asset quote to the buffer.

        Args:
            quote: Quote dictionary with fields like symbol, bid, ask, last, volume, etc.
        """
        symbol = quote.get('symbol')
        if symbol:
            # Normalize symbol (remove $ prefix if present)
            normalized_symbol = symbol.replace('$', '').replace('.X', '')
            self.quote_buffer[normalized_symbol].append(quote)

    def should_flush(self) -> bool:
        """Check if buffer should be flushed to create bars.

        Returns:
            True if aggregate interval has elapsed
        """
        elapsed = (now_utc() - self.last_flush_time).total_seconds()
        return elapsed >= self.aggregate_interval

    def flush(self) -> List["UnderlyingBar"]:
        """Aggregate buffered quotes into bars and clear buffer.

        Returns:
            List of UnderlyingBar Pydantic models ready for database insertion into underlying_bars
        """
        if not self.quote_buffer:
            self.last_flush_time = now_utc()
            return []

        now = now_utc()
        print(f"\n  💾 [{now.strftime('%Y-%m-%d %H:%M:%S')}] Flushing {len(self.quote_buffer)} underlying symbols...")

        bars_to_insert = []
        flush_timestamp = self.last_flush_time

        # Import Pydantic model at runtime
        from quant_vibe.models import UnderlyingBar

        for symbol, quotes in self.quote_buffer.items():
            if not quotes:
                continue

            # Aggregate quotes into OHLC bar
            prices = []
            for q in quotes:
                # Try last price first
                price = q.get('last')

                # Fallback to mid price
                if price is None and q.get('bid') and q.get('ask'):
                    price = (q['bid'] + q['ask']) / 2.0

                # Fallback to bid or ask alone
                if price is None:
                    price = q.get('bid') or q.get('ask')

                if price:
                    prices.append(price)

            if not prices:
                continue

            # Calculate volume metrics
            volumes = [q.get('volume', 0) for q in quotes if q.get('volume') is not None]
            max_volume = max(volumes) if volumes else 0

            # Calculate VWAP (Volume Weighted Average Price)
            vwap = self._calculate_vwap(quotes)

            # Get latest quote for other fields
            # latest_quote = quotes[-1]

            # Create UnderlyingBar Pydantic model
            bar = UnderlyingBar(
                timestamp=flush_timestamp,
                ticker=symbol,  # Normalized (no $ or .X)
                open=Decimal(str(prices[0])),
                high=Decimal(str(max(prices))),
                low=Decimal(str(min(prices))),
                close=Decimal(str(prices[-1])),
                volume=max_volume,
                vwap=Decimal(str(vwap)) if vwap is not None else None,
                transactions=len(quotes),
                data_source='schwabdev_stream',
            )

            bars_to_insert.append(bar)

        # Clear buffer
        self.quote_buffer.clear()
        self.last_flush_time = now_utc()

        return bars_to_insert

    def _calculate_vwap(self, quotes: List[Dict]) -> Optional[float]:
        """Calculate Volume Weighted Average Price.

        Args:
            quotes: List of quote dictionaries

        Returns:
            VWAP or None if cannot calculate
        """
        price_volume_sum = 0.0
        total_volume_for_vwap = 0.0

        for i, q in enumerate(quotes):
            price = q.get('last')
            if price is None and q.get('bid') and q.get('ask'):
                price = (q['bid'] + q['ask']) / 2.0

            volume = q.get('volume', 0)

            # For cumulative volume, calculate incremental volume
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
            return price_volume_sum / total_volume_for_vwap

        return None

    def get_buffered_symbol_count(self) -> int:
        """Get number of symbols currently buffered.

        Returns:
            Count of buffered symbols
        """
        return len(self.quote_buffer)
