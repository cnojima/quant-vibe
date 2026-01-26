"""Bar aggregation logic for streaming quotes."""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, TYPE_CHECKING

from quant_vibe.utils import (
    calculate_mark_price,
    normalize_option_ticker,
    now_utc,
    parse_expiration_from_ticker,
)

if TYPE_CHECKING:
    from quant_vibe.models import OptionsBar


class BarAggregator:
    """Aggregates streaming quotes into OHLCV bars."""

    def __init__(self, aggregate_interval_seconds: int = 60):
        """Initialize bar aggregator.

        Args:
            aggregate_interval_seconds: Seconds to aggregate into bars
        """
        self.aggregate_interval = aggregate_interval_seconds
        self.quote_buffer: Dict[str, List[Dict]] = defaultdict(list)
        self.last_flush_time = now_utc()

    def add_quote(self, quote: Dict):
        """Add a quote to the buffer.

        Args:
            quote: Quote dictionary with fields like symbol, bid, ask, last, etc.
        """
        symbol = quote.get('symbol')
        if symbol:
            self.quote_buffer[symbol].append(quote)

    def should_flush(self) -> bool:
        """Check if buffer should be flushed to create bars.

        Returns:
            True if aggregate interval has elapsed
        """
        elapsed = (now_utc() - self.last_flush_time).total_seconds()
        return elapsed >= self.aggregate_interval

    def flush(self) -> List["OptionsBar"]:
        """Aggregate buffered quotes into bars and clear buffer.

        Returns:
            List of OptionsBar Pydantic models ready for database insertion
        """
        if not self.quote_buffer:
            self.last_flush_time = now_utc()
            return []

        now = now_utc()
        print(f"\n  [{now.strftime('%Y-%m-%d %H:%M:%S')}] Flushing {len(self.quote_buffer)} symbols to database...")

        from quant_vibe.models import OptionsBar

        bars_to_insert = []
        flush_timestamp = self.last_flush_time

        for symbol, quotes in self.quote_buffer.items():
            bar = self._create_bar(symbol, quotes, flush_timestamp)
            if bar:
                bars_to_insert.append(bar)

        self.quote_buffer.clear()
        self.last_flush_time = now_utc()

        return bars_to_insert

    def _create_bar(self, symbol: str, quotes: List[Dict], timestamp: datetime) -> Optional["OptionsBar"]:
        """Create an OptionsBar from quotes.

        Args:
            symbol: Option symbol
            quotes: List of quotes for this symbol
            timestamp: Bar timestamp

        Returns:
            OptionsBar or None if cannot create
        """
        if not quotes:
            return None

        prices = self._extract_prices(quotes)
        if not prices:
            return None

        from quant_vibe.models import OptionsBar

        latest_quote = quotes[-1]

        strike_price = latest_quote.get('strike')
        if strike_price is None:
            return None

        exp_date = self._parse_expiration(latest_quote, symbol)
        contract_type = self._parse_contract_type(latest_quote)

        bid = latest_quote.get('bid')
        ask = latest_quote.get('ask')
        mark = calculate_mark_price(bid, ask)

        volumes = [q.get('volume', 0) for q in quotes if q.get('volume') is not None]

        return OptionsBar(
            timestamp=timestamp,
            option_ticker=normalize_option_ticker(symbol),
            underlying_ticker='SPX',
            strike_price=Decimal(str(strike_price)),
            contract_type=contract_type,
            expiration_date=exp_date,
            open=Decimal(str(prices[0])),
            high=Decimal(str(max(prices))),
            low=Decimal(str(min(prices))),
            close=Decimal(str(prices[-1])),
            volume=max(volumes) if volumes else 0,
            bid=Decimal(str(bid)) if bid is not None else None,
            ask=Decimal(str(ask)) if ask is not None else None,
            mark=Decimal(str(mark)) if mark is not None else None,
            bid_size=latest_quote.get('bid_size'),
            ask_size=latest_quote.get('ask_size'),
            vwap=self._calculate_vwap(quotes),
            transactions=len(quotes),
            implied_volatility=self._to_decimal_iv(latest_quote.get('iv')),
            delta=self._to_decimal_greek(latest_quote.get('delta')),
            gamma=self._to_decimal_greek(latest_quote.get('gamma')),
            theta=self._to_decimal_greek(latest_quote.get('theta')),
            vega=self._to_decimal_greek(latest_quote.get('vega')),
            rho=self._to_decimal_greek(latest_quote.get('rho')),
            data_source='schwabdev_stream',
        )

    def _extract_prices(self, quotes: List[Dict]) -> List[float]:
        """Extract prices from quotes.

        Args:
            quotes: List of quote dictionaries

        Returns:
            List of prices
        """
        prices = []
        for quote in quotes:
            price = quote.get('last')
            if price is None:
                price = calculate_mark_price(quote.get('bid'), quote.get('ask'))
            if price > 0:
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

    def _parse_expiration(self, quote: Dict, symbol: str) -> Optional[datetime]:
        """Parse expiration date from quote or symbol.

        Args:
            quote: Quote dictionary
            symbol: Option symbol

        Returns:
            Expiration date or None
        """
        try:
            exp_year = quote.get('exp_year')
            exp_month = quote.get('exp_month')
            exp_day = quote.get('exp_day')

            if exp_year and exp_month and exp_day:
                return datetime(int(exp_year), int(exp_month), int(exp_day)).date()
        except (ValueError, TypeError):
            pass

        return parse_expiration_from_ticker(symbol)

    def _parse_contract_type(self, quote: Dict) -> str:
        """Parse contract type from quote.

        Args:
            quote: Quote dictionary

        Returns:
            'call' or 'put'
        """
        contract_type_raw = quote.get('contract_type', '')
        return 'call' if str(contract_type_raw).upper().startswith('C') else 'put'

    def _to_decimal(self, value: any) -> Optional[Decimal]:
        """Convert value to Decimal or None.

        Args:
            value: Value to convert

        Returns:
            Decimal or None
        """
        return Decimal(str(value)) if value is not None else None

    def _to_decimal_iv(self, value: any) -> Optional[Decimal]:
        """Convert implied volatility value to Decimal or None.

        Handles Schwab API sentinel values:
        - -999.0 indicates unavailable/undefined IV

        Args:
            value: IV value to convert

        Returns:
            Decimal or None if sentinel value or None
        """
        if value is None:
            return None
        # Check for Schwab's sentinel value for unavailable IV
        if float(value) == -999.0:
            return None
        # IV should be non-negative
        if float(value) < 0:
            return None
        return Decimal(str(value))

    def _to_decimal_greek(self, value: any) -> Optional[Decimal]:
        """Convert Greek value to Decimal or None.

        Handles Schwab API sentinel values:
        - -999.0 or -999 indicates unavailable/undefined Greek value

        Args:
            value: Greek value to convert

        Returns:
            Decimal or None if sentinel value or None
        """
        if value is None:
            return None
        # Check for Schwab's sentinel value
        float_val = float(value)
        if float_val == -999.0 or float_val == -999:
            return None
        # Greeks can be negative (e.g., theta), so no sign check
        return Decimal(str(value))

    def get_buffered_symbol_count(self) -> int:
        """Get number of symbols currently buffered.

        Returns:
            Count of buffered symbols
        """
        return len(self.quote_buffer)