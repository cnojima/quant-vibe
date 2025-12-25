"""Unit tests for BarAggregator."""

import sys
from pathlib import Path
import pytest
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from streaming_service.aggregator import BarAggregator, parse_expiration_from_ticker


class TestParseExpirationFromTicker:
    """Test cases for parse_expiration_from_ticker helper function."""

    def test_parse_valid_ticker(self):
        """Test parsing valid SPXW ticker."""
        ticker = "SPXW  260121P06200000"
        exp_date = parse_expiration_from_ticker(ticker)

        assert exp_date is not None
        assert exp_date.year == 2026
        assert exp_date.month == 1
        assert exp_date.day == 21

    def test_parse_ticker_no_spaces(self):
        """Test parsing ticker without spaces."""
        ticker = "SPXW260121C06000000"
        exp_date = parse_expiration_from_ticker(ticker)

        assert exp_date is not None
        assert exp_date.year == 2026
        assert exp_date.month == 1
        assert exp_date.day == 21

    def test_parse_ticker_call_option(self):
        """Test parsing call option ticker."""
        ticker = "SPXW  251220C05800000"
        exp_date = parse_expiration_from_ticker(ticker)

        assert exp_date is not None
        assert exp_date.year == 2025
        assert exp_date.month == 12
        assert exp_date.day == 20

    def test_parse_invalid_ticker(self):
        """Test parsing invalid ticker returns None."""
        ticker = "INVALID"
        exp_date = parse_expiration_from_ticker(ticker)

        assert exp_date is None

    def test_parse_malformed_date(self):
        """Test parsing ticker with malformed date."""
        ticker = "SPXW  999999P06200000"  # Invalid date
        exp_date = parse_expiration_from_ticker(ticker)

        assert exp_date is None

    def test_parse_empty_ticker(self):
        """Test parsing empty ticker."""
        ticker = ""
        exp_date = parse_expiration_from_ticker(ticker)

        assert exp_date is None


class TestBarAggregator:
    """Test cases for BarAggregator class."""

    @pytest.fixture
    def aggregator(self):
        """Create a BarAggregator instance."""
        return BarAggregator(aggregate_interval_seconds=60)

    @pytest.fixture
    def sample_quote(self):
        """Create a sample quote."""
        return {
            'timestamp': datetime.now(),
            'symbol': 'SPXW  260121P06200000',
            'bid': 100.0,
            'ask': 101.0,
            'last': 100.5,
            'high': 102.0,
            'low': 99.0,
            'close': 100.5,
            'volume': 1000,
            'open': 100.0,
            'bid_size': 10,
            'ask_size': 15,
            'strike': 6200.0,
            'contract_type': 'P',
            'exp_year': 2026,
            'exp_month': 1,
            'exp_day': 21,
            'iv': 0.15,
            'delta': -0.5,
            'gamma': 0.001,
            'theta': -0.05,
            'vega': 0.10,
            'rho': -0.02,
        }

    def test_initialization(self):
        """Test BarAggregator initialization."""
        agg = BarAggregator(aggregate_interval_seconds=120)

        assert agg.aggregate_interval == 120
        assert len(agg.quote_buffer) == 0
        assert agg.last_flush_time is not None

    def test_initialization_default_interval(self):
        """Test BarAggregator initialization with default interval."""
        agg = BarAggregator()

        assert agg.aggregate_interval == 60

    def test_add_quote(self, aggregator, sample_quote):
        """Test adding a quote to buffer."""
        aggregator.add_quote(sample_quote)

        assert len(aggregator.quote_buffer) == 1
        assert 'SPXW  260121P06200000' in aggregator.quote_buffer
        assert len(aggregator.quote_buffer['SPXW  260121P06200000']) == 1

    def test_add_multiple_quotes_same_symbol(self, aggregator, sample_quote):
        """Test adding multiple quotes for same symbol."""
        aggregator.add_quote(sample_quote)
        aggregator.add_quote(sample_quote)
        aggregator.add_quote(sample_quote)

        assert len(aggregator.quote_buffer) == 1
        assert len(aggregator.quote_buffer['SPXW  260121P06200000']) == 3

    def test_add_quotes_different_symbols(self, aggregator, sample_quote):
        """Test adding quotes for different symbols."""
        quote1 = sample_quote.copy()
        quote1['symbol'] = 'SPXW  260121P06200000'

        quote2 = sample_quote.copy()
        quote2['symbol'] = 'SPXW  260121C06000000'

        aggregator.add_quote(quote1)
        aggregator.add_quote(quote2)

        assert len(aggregator.quote_buffer) == 2
        assert 'SPXW  260121P06200000' in aggregator.quote_buffer
        assert 'SPXW  260121C06000000' in aggregator.quote_buffer

    def test_add_quote_without_symbol(self, aggregator):
        """Test adding quote without symbol is ignored."""
        quote = {'bid': 100.0, 'ask': 101.0}  # No symbol
        aggregator.add_quote(quote)

        assert len(aggregator.quote_buffer) == 0

    def test_should_flush_not_ready(self, aggregator):
        """Test should_flush returns False when not ready."""
        aggregator.last_flush_time = datetime.now()

        assert aggregator.should_flush() is False

    def test_should_flush_ready(self, aggregator):
        """Test should_flush returns True when ready."""
        # Simulate 61 seconds ago
        aggregator.last_flush_time = datetime.now() - timedelta(seconds=61)

        assert aggregator.should_flush() is True

    def test_should_flush_exact_threshold(self, aggregator):
        """Test should_flush at exact threshold."""
        # Simulate exactly 60 seconds ago
        aggregator.last_flush_time = datetime.now() - timedelta(seconds=60)

        # Should return True (>= threshold)
        assert aggregator.should_flush() is True

    def test_flush_empty_buffer(self, aggregator):
        """Test flushing empty buffer."""
        bars = aggregator.flush()

        assert bars == []
        assert len(aggregator.quote_buffer) == 0

    def test_flush_single_quote(self, aggregator, sample_quote):
        """Test flushing buffer with single quote."""
        aggregator.add_quote(sample_quote)

        bars = aggregator.flush()

        assert len(bars) == 1
        assert len(aggregator.quote_buffer) == 0  # Buffer cleared

        bar = bars[0]
        assert bar['option_ticker'] == 'SPXW  260121P06200000'
        assert bar['underlying_ticker'] == 'SPX'
        assert bar['open'] == 100.5
        assert bar['high'] == 100.5
        assert bar['low'] == 100.5
        assert bar['close'] == 100.5
        assert bar['volume'] == 1000
        assert bar['transactions'] == 1
        assert bar['bid'] == 100.0
        assert bar['ask'] == 101.0
        assert bar['strike_price'] == 6200.0
        assert bar['contract_type'] == 'put'
        assert bar['delta'] == -0.5
        assert bar['implied_volatility'] == 0.15

    def test_flush_multiple_quotes_ohlc(self, aggregator, sample_quote):
        """Test OHLC calculation with multiple quotes."""
        # Add 4 quotes with different prices
        quote1 = sample_quote.copy()
        quote1['last'] = 100.0  # Open

        quote2 = sample_quote.copy()
        quote2['last'] = 105.0  # High

        quote3 = sample_quote.copy()
        quote3['last'] = 98.0   # Low

        quote4 = sample_quote.copy()
        quote4['last'] = 102.0  # Close

        aggregator.add_quote(quote1)
        aggregator.add_quote(quote2)
        aggregator.add_quote(quote3)
        aggregator.add_quote(quote4)

        bars = aggregator.flush()

        assert len(bars) == 1
        bar = bars[0]

        assert bar['open'] == 100.0
        assert bar['high'] == 105.0
        assert bar['low'] == 98.0
        assert bar['close'] == 102.0
        assert bar['transactions'] == 4

    def test_flush_quote_without_last_price(self, aggregator, sample_quote):
        """Test quote without last price uses bid/ask midpoint."""
        quote = sample_quote.copy()
        quote['last'] = None
        quote['bid'] = 100.0
        quote['ask'] = 102.0

        aggregator.add_quote(quote)

        bars = aggregator.flush()

        assert len(bars) == 1
        bar = bars[0]

        # Should use midpoint (100 + 102) / 2 = 101
        assert bar['open'] == 101.0
        assert bar['close'] == 101.0

    def test_flush_quote_without_price_data(self, aggregator, sample_quote):
        """Test quote without any price data is skipped."""
        quote = sample_quote.copy()
        quote['last'] = None
        quote['bid'] = None
        quote['ask'] = None

        aggregator.add_quote(quote)

        bars = aggregator.flush()

        # Should be skipped (no bars generated)
        assert len(bars) == 0

    def test_flush_vwap_calculation(self, aggregator, sample_quote):
        """Test VWAP calculation."""
        # Add quotes with different prices and volumes
        quote1 = sample_quote.copy()
        quote1['last'] = 100.0
        quote1['volume'] = 100

        quote2 = sample_quote.copy()
        quote2['last'] = 110.0
        quote2['volume'] = 200  # Incremental: 100

        quote3 = sample_quote.copy()
        quote3['last'] = 120.0
        quote3['volume'] = 350  # Incremental: 150

        aggregator.add_quote(quote1)
        aggregator.add_quote(quote2)
        aggregator.add_quote(quote3)

        bars = aggregator.flush()

        assert len(bars) == 1
        bar = bars[0]

        # VWAP = (100*100 + 110*100 + 120*150) / (100 + 100 + 150)
        #      = (10000 + 11000 + 18000) / 350
        #      = 39000 / 350 = 111.43
        assert bar['vwap'] is not None
        assert abs(bar['vwap'] - 111.43) < 0.01

    def test_flush_vwap_with_no_volume(self, aggregator, sample_quote):
        """Test VWAP when no volume available."""
        quote = sample_quote.copy()
        quote['last'] = 100.0
        quote['volume'] = None

        aggregator.add_quote(quote)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['vwap'] is None

    def test_flush_expiration_from_quote_fields(self, aggregator, sample_quote):
        """Test expiration date parsed from quote fields."""
        aggregator.add_quote(sample_quote)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['expiration_date'] is not None
        assert bar['expiration_date'].year == 2026
        assert bar['expiration_date'].month == 1
        assert bar['expiration_date'].day == 21

    def test_flush_expiration_from_ticker(self, aggregator, sample_quote):
        """Test expiration date parsed from ticker when quote fields missing."""
        quote = sample_quote.copy()
        quote['exp_year'] = None
        quote['exp_month'] = None
        quote['exp_day'] = None

        aggregator.add_quote(quote)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['expiration_date'] is not None
        assert bar['expiration_date'].year == 2026

    def test_flush_contract_type_call(self, aggregator, sample_quote):
        """Test contract type parsing for call."""
        quote = sample_quote.copy()
        quote['symbol'] = 'SPXW  260121C06000000'
        quote['contract_type'] = 'C'

        aggregator.add_quote(quote)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['contract_type'] == 'call'

    def test_flush_contract_type_put(self, aggregator, sample_quote):
        """Test contract type parsing for put."""
        aggregator.add_quote(sample_quote)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['contract_type'] == 'put'

    def test_flush_contract_type_from_symbol(self, aggregator, sample_quote):
        """Test contract type fallback to symbol parsing."""
        quote = sample_quote.copy()
        quote['contract_type'] = None
        quote['symbol'] = 'SPXW  260121C06000000'  # Has 'C' for call

        aggregator.add_quote(quote)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['contract_type'] == 'call'

    def test_flush_updates_last_flush_time(self, aggregator, sample_quote):
        """Test that flush updates last_flush_time."""
        old_flush_time = aggregator.last_flush_time

        aggregator.add_quote(sample_quote)
        aggregator.flush()

        assert aggregator.last_flush_time > old_flush_time

    def test_flush_clears_buffer(self, aggregator, sample_quote):
        """Test that flush clears the buffer."""
        aggregator.add_quote(sample_quote)
        aggregator.add_quote(sample_quote)

        assert len(aggregator.quote_buffer) == 1

        aggregator.flush()

        assert len(aggregator.quote_buffer) == 0

    def test_flush_multiple_symbols(self, aggregator, sample_quote):
        """Test flushing multiple symbols."""
        quote1 = sample_quote.copy()
        quote1['symbol'] = 'SPXW  260121P06200000'

        quote2 = sample_quote.copy()
        quote2['symbol'] = 'SPXW  260121C06000000'
        quote2['contract_type'] = 'C'

        quote3 = sample_quote.copy()
        quote3['symbol'] = 'SPXW  260121P06100000'

        aggregator.add_quote(quote1)
        aggregator.add_quote(quote2)
        aggregator.add_quote(quote3)

        bars = aggregator.flush()

        assert len(bars) == 3

        symbols = [bar['option_ticker'] for bar in bars]
        assert 'SPXW  260121P06200000' in symbols
        assert 'SPXW  260121C06000000' in symbols
        assert 'SPXW  260121P06100000' in symbols

    def test_flush_preserves_latest_quote_data(self, aggregator, sample_quote):
        """Test that flush uses latest quote for bid/ask/Greeks."""
        quote1 = sample_quote.copy()
        quote1['bid'] = 100.0
        quote1['delta'] = -0.4

        quote2 = sample_quote.copy()
        quote2['bid'] = 101.0
        quote2['delta'] = -0.5

        quote3 = sample_quote.copy()
        quote3['bid'] = 102.0
        quote3['delta'] = -0.6

        aggregator.add_quote(quote1)
        aggregator.add_quote(quote2)
        aggregator.add_quote(quote3)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['bid'] == 102.0  # Latest
        assert bar['delta'] == -0.6  # Latest

    def test_get_buffered_symbol_count_empty(self, aggregator):
        """Test get_buffered_symbol_count with empty buffer."""
        assert aggregator.get_buffered_symbol_count() == 0

    def test_get_buffered_symbol_count_single_symbol(self, aggregator, sample_quote):
        """Test get_buffered_symbol_count with single symbol."""
        aggregator.add_quote(sample_quote)
        aggregator.add_quote(sample_quote)

        assert aggregator.get_buffered_symbol_count() == 1

    def test_get_buffered_symbol_count_multiple_symbols(self, aggregator, sample_quote):
        """Test get_buffered_symbol_count with multiple symbols."""
        quote1 = sample_quote.copy()
        quote1['symbol'] = 'SPXW  260121P06200000'

        quote2 = sample_quote.copy()
        quote2['symbol'] = 'SPXW  260121C06000000'

        quote3 = sample_quote.copy()
        quote3['symbol'] = 'SPXW  260121P06100000'

        aggregator.add_quote(quote1)
        aggregator.add_quote(quote2)
        aggregator.add_quote(quote3)

        assert aggregator.get_buffered_symbol_count() == 3

    def test_flush_timestamp_uses_last_flush_time(self, aggregator, sample_quote):
        """Test that bar timestamp uses last_flush_time."""
        flush_time = datetime.now() - timedelta(minutes=1)
        aggregator.last_flush_time = flush_time

        aggregator.add_quote(sample_quote)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['timestamp'] == flush_time

    def test_flush_data_source_field(self, aggregator, sample_quote):
        """Test that bars have correct data_source field."""
        aggregator.add_quote(sample_quote)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['data_source'] == 'schwabdev_stream'

    def test_custom_aggregate_interval(self):
        """Test BarAggregator with custom interval."""
        agg = BarAggregator(aggregate_interval_seconds=300)

        agg.last_flush_time = datetime.now() - timedelta(seconds=301)

        assert agg.should_flush() is True

    def test_volume_max_selection(self, aggregator, sample_quote):
        """Test that volume field uses max volume from quotes."""
        quote1 = sample_quote.copy()
        quote1['volume'] = 100

        quote2 = sample_quote.copy()
        quote2['volume'] = 500

        quote3 = sample_quote.copy()
        quote3['volume'] = 300

        aggregator.add_quote(quote1)
        aggregator.add_quote(quote2)
        aggregator.add_quote(quote3)

        bars = aggregator.flush()

        bar = bars[0]
        assert bar['volume'] == 500  # Max volume
