"""Bar aggregation logic for streaming quotes."""

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, TYPE_CHECKING
from decimal import Decimal

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from quant_vibe.utils import (
    normalize_option_ticker,
    parse_expiration_from_ticker,  # Import from canonical location
    now_utc,
)

if TYPE_CHECKING:
    from quant_vibe.models import OptionsBar


class BarAggregator:
    """Aggregates streaming quotes into OHLCV bars.

    Buffers incoming quote updates and periodically aggregates them into
    1-minute (or configurable interval) OHLCV bars.
    """

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
        print(f"\n  💾 [{now.strftime('%Y-%m-%d %H:%M:%S')}] Flushing {len(self.quote_buffer)} symbols to database...")

        bars_to_insert = []
        flush_timestamp = self.last_flush_time

        # Import Pydantic model at runtime
        from quant_vibe.models import OptionsBar

        for symbol, quotes in self.quote_buffer.items():
            if not quotes:
                continue

            # Aggregate quotes into OHLC bar
            prices = []
            for q in quotes:
                price = q.get('last')
                if price is None and q.get('bid') and q.get('ask'):
                    price = (q['bid'] + q['ask']) / 2.0
                if price:
                    prices.append(price)

            if not prices:
                continue

            # Calculate volume metrics
            volumes = [q.get('volume', 0) for q in quotes if q.get('volume') is not None]
            max_volume = max(volumes) if volumes else 0

            # Calculate VWAP (Volume Weighted Average Price)
            vwap = self._calculate_vwap(quotes)

            # Get latest quote for contract details
            latest_quote = quotes[-1]

            # Build expiration date from year, month, day fields
            exp_date = self._parse_expiration_date(latest_quote, symbol)

            # Get contract type
            contract_type = self._parse_contract_type(latest_quote, symbol)

            # Normalize option ticker (remove spaces and O: prefix)
            normalized_ticker = normalize_option_ticker(symbol)

            # Get strike price
            strike_price = latest_quote.get('strike')
            if strike_price is None:
                continue  # Skip if no strike price

            # Calculate mark price
            bid = latest_quote.get('bid')
            ask = latest_quote.get('ask')
            mark = None
            if bid is not None and ask is not None:
                mark = (bid + ask) / 2.0

            # Create OptionsBar Pydantic model
            bar = OptionsBar(
                timestamp=flush_timestamp,
                contract_symbol=normalized_ticker,
                underlying_ticker='SPX',
                strike_price=Decimal(str(strike_price)),
                contract_type=contract_type,
                expiration_date=exp_date,
                open=Decimal(str(prices[0])),
                high=Decimal(str(max(prices))),
                low=Decimal(str(min(prices))),
                close=Decimal(str(prices[-1])),
                volume=max_volume,
                bid=Decimal(str(bid)) if bid is not None else None,
                ask=Decimal(str(ask)) if ask is not None else None,
                mark=Decimal(str(mark)) if mark is not None else None,
                bid_size=latest_quote.get('bid_size'),
                ask_size=latest_quote.get('ask_size'),
                vwap=Decimal(str(vwap)) if vwap is not None else None,
                transactions=len(quotes),
                implied_volatility=Decimal(str(latest_quote.get('iv'))) if latest_quote.get('iv') is not None else None,
                delta=Decimal(str(latest_quote.get('delta'))) if latest_quote.get('delta') is not None else None,
                gamma=Decimal(str(latest_quote.get('gamma'))) if latest_quote.get('gamma') is not None else None,
                theta=Decimal(str(latest_quote.get('theta'))) if latest_quote.get('theta') is not None else None,
                vega=Decimal(str(latest_quote.get('vega'))) if latest_quote.get('vega') is not None else None,
                rho=Decimal(str(latest_quote.get('rho'))) if latest_quote.get('rho') is not None else None,
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

    def _parse_expiration_date(self, quote: Dict, symbol: str) -> Optional[datetime]:
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

        # Fallback: parse from ticker symbol
        return parse_expiration_from_ticker(symbol)

    def _parse_contract_type(self, quote: Dict, symbol: str) -> str:
        """Parse contract type from quote or symbol.

        Args:
            quote: Quote dictionary
            symbol: Option symbol

        Returns:
            'call' or 'put'
        """
        contract_type_raw = quote.get('contract_type')
        if contract_type_raw:
            return 'call' if str(contract_type_raw).upper().startswith('C') else 'put'

        # Fallback: parse from symbol
        return 'call' if 'C' in symbol else 'put'

    def get_buffered_symbol_count(self) -> int:
        """Get number of symbols currently buffered.

        Returns:
            Count of buffered symbols
        """
        return len(self.quote_buffer)
