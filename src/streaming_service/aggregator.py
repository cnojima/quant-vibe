"""Bar aggregation logic for streaming quotes."""

import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from quant_vibe.utils import normalize_option_ticker


def parse_expiration_from_ticker(ticker: str) -> Optional[datetime]:
    """Parse expiration date from SPXW option ticker.

    SPXW option tickers have the format: SPXW  YYMMDDX########
    Where:
    - YYMMDD = expiration date (year, month, day)
    - X = P (put) or C (call)
    - ######## = strike price

    Example: SPXW  260121P06200000 = Jan 21, 2026 Put at 6200 strike

    Args:
        ticker: Option ticker in format "SPXW  YYMMDDX########"

    Returns:
        Expiration date as datetime.date or None if parse fails
    """
    ticker = ticker.strip()
    pattern = r'SPXW\s*(\d{6})[PC]'
    match = re.search(pattern, ticker)

    if not match:
        return None

    date_str = match.group(1)  # YYMMDD

    try:
        yy = int(date_str[0:2])
        mm = int(date_str[2:4])
        dd = int(date_str[4:6])
        yyyy = 2000 + yy
        exp_date = datetime(yyyy, mm, dd).date()
        return exp_date
    except (ValueError, IndexError):
        return None


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
        self.last_flush_time = datetime.now()

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
        elapsed = (datetime.now() - self.last_flush_time).total_seconds()
        return elapsed >= self.aggregate_interval

    def flush(self) -> List[Dict]:
        """Aggregate buffered quotes into bars and clear buffer.

        Returns:
            List of bar dictionaries ready for database insertion
        """
        if not self.quote_buffer:
            self.last_flush_time = datetime.now()
            return []

        now = datetime.now()
        print(f"\n  💾 [{now.strftime('%Y-%m-%d %H:%M:%S')}] Flushing {len(self.quote_buffer)} symbols to database...")

        bars_to_insert = []
        flush_timestamp = self.last_flush_time

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

            bar = {
                'timestamp': flush_timestamp,
                'option_ticker': normalized_ticker,
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
                'bid_size': latest_quote.get('bid_size'),
                'ask_size': latest_quote.get('ask_size'),
                # Contract details
                'strike_price': latest_quote.get('strike'),
                'contract_type': contract_type,
                'expiration_date': exp_date,
                # Greeks
                'delta': latest_quote.get('delta'),
                'gamma': latest_quote.get('gamma'),
                'theta': latest_quote.get('theta'),
                'vega': latest_quote.get('vega'),
                'rho': latest_quote.get('rho'),
                'implied_volatility': latest_quote.get('iv'),
                'data_source': 'schwabdev_stream',
            }

            bars_to_insert.append(bar)

        # Clear buffer
        self.quote_buffer.clear()
        self.last_flush_time = datetime.now()

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
