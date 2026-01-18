"""Bar aggregation logic for underlying asset (SPX) quotes."""

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, TYPE_CHECKING

from quant_vibe.utils import calculate_mark_price, now_utc, safe_decimal

if TYPE_CHECKING:
    from quant_vibe.models import UnderlyingBar


class UnderlyingBarAggregator:
    """Aggregates underlying asset (SPX) streaming quotes into OHLCV bars."""

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
            List of UnderlyingBar Pydantic models ready for database insertion
        """
        if not self.quote_buffer:
            self.last_flush_time = now_utc()
            return []

        now = now_utc()
        print(f"\n  [{now.strftime('%Y-%m-%d %H:%M:%S')}] Flushing {len(self.quote_buffer)} underlying symbols...")

        from quant_vibe.models import UnderlyingBar

        bars_to_insert = []
        flush_timestamp = self.last_flush_time

        for symbol, quotes in self.quote_buffer.items():
            bar = self._create_bar(symbol, quotes, flush_timestamp)
            if bar:
                bars_to_insert.append(bar)

        self.quote_buffer.clear()
        self.last_flush_time = now_utc()

        return bars_to_insert

    def _create_bar(self, symbol: str, quotes: List[Dict], timestamp) -> Optional["UnderlyingBar"]:
        """Create an UnderlyingBar from quotes.

        Args:
            symbol: Underlying symbol (normalized)
            quotes: List of quotes for this symbol
            timestamp: Bar timestamp

        Returns:
            UnderlyingBar or None if cannot create
        """
        if not quotes:
            return None

        prices = self._extract_prices(quotes)
        if not prices:
            return None

        from quant_vibe.models import UnderlyingBar

        volumes = [q.get('volume', 0) for q in quotes if q.get('volume') is not None]

        return UnderlyingBar(
            timestamp=timestamp,
            ticker=symbol,
            open=Decimal(str(prices[0])),
            high=Decimal(str(max(prices))),
            low=Decimal(str(min(prices))),
            close=Decimal(str(prices[-1])),
            volume=max(volumes) if volumes else 0,
            vwap=self._calculate_vwap(quotes),
            transactions=len(quotes),
            data_source='schwabdev_stream',
        )

    def _extract_prices(self, quotes: List[Dict]) -> List[float]:
        """Extract prices from quotes with fallbacks.

        Args:
            quotes: List of quote dictionaries

        Returns:
            List of prices
        """
        prices = []
        for quote in quotes:
            price = quote.get('last')

            if price is None:
                # Try to calculate mark price from bid/ask
                price = calculate_mark_price(quote.get('bid'), quote.get('ask'))
                # Fallback to bid or ask if mark is zero
                if price <= 0:
                    price = quote.get('bid') or quote.get('ask') or 0.0

            if price:
                prices.append(price)

        return prices

    def _calculate_vwap(self, quotes: List[Dict]) -> Optional[Decimal]:
        """Calculate Volume Weighted Average Price.

        Args:
            quotes: List of quote dictionaries

        Returns:
            VWAP as Decimal or None if cannot calculate
        """
        price_volume_sum = 0.0
        total_volume = 0.0

        for i, quote in enumerate(quotes):
            price = quote.get('last')
            if price is None:
                price = calculate_mark_price(quote.get('bid'), quote.get('ask'))

            volume = quote.get('volume', 0)

            if i > 0 and volume is not None:
                prev_volume = quotes[i-1].get('volume', 0) or 0
                incremental_volume = volume - prev_volume
            else:
                incremental_volume = volume if volume is not None else 0

            if price and incremental_volume > 0:
                price_volume_sum += price * incremental_volume
                total_volume += incremental_volume

        if total_volume > 0:
            return Decimal(str(price_volume_sum / total_volume))
        return None

    def get_buffered_symbol_count(self) -> int:
        """Get number of symbols currently buffered.

        Returns:
            Count of buffered symbols
        """
        return len(self.quote_buffer)