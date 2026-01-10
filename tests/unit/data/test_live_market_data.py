"""Tests for LiveMarketDataProvider."""

import pytest
import pandas as pd
from datetime import datetime

from quant_vibe.data.live_market_data import LiveMarketDataProvider
from quant_vibe.live.data_feed import RealtimeDataFeed


class TestLiveMarketDataProvider:
    """Test suite for LiveMarketDataProvider."""

    @pytest.fixture
    def data_feed(self):
        """Create a mock data feed with sample data."""
        feed = RealtimeDataFeed(window_size=100, aggregate_interval_seconds=60)

        # Add some sample bars
        bar1 = {
            'timestamp': datetime(2025, 12, 22, 9, 30),
            'contract_symbol': 'SPXW251222C06875000',
            'underlying_ticker': 'SPX',
            'open': 10.0,
            'high': 12.0,
            'low': 9.5,
            'close': 11.0,
            'volume': 100,
            'vwap': 10.5,
            'bid': 10.8,
            'ask': 11.2,
            'mark': 11.0,
            'strike_price': 6875.0,
            'option_type': 'C',
            'expiration_date': datetime(2025, 12, 22).date(),
            'delta': 0.50,
            'gamma': 0.01,
            'theta': -0.5,
            'vega': 0.2,
            'rho': 0.1,
            'implied_volatility': 0.15,
        }

        bar2 = {
            'timestamp': datetime(2025, 12, 22, 9, 31),
            'contract_symbol': 'SPXW251222P06850000',
            'underlying_ticker': 'SPX',
            'open': 8.0,
            'high': 9.0,
            'low': 7.5,
            'close': 8.5,
            'volume': 80,
            'vwap': 8.2,
            'bid': 8.3,
            'ask': 8.7,
            'mark': 8.5,
            'strike_price': 6850.0,
            'option_type': 'P',
            'expiration_date': datetime(2025, 12, 22).date(),
            'delta': -0.45,
            'gamma': 0.01,
            'theta': -0.4,
            'vega': 0.18,
            'rho': -0.08,
            'implied_volatility': 0.14,
        }

        # Add bars to feed
        feed.bars['SPXW251222C06875000'].append(bar1)
        feed.bars['SPXW251222P06850000'].append(bar2)

        # Add underlying price
        feed.underlying_prices['SPX'] = 6860.0
        feed.last_update_time = datetime(2025, 12, 22, 9, 31)

        return feed

    @pytest.fixture
    def provider(self, data_feed):
        """Create provider with sample data."""
        return LiveMarketDataProvider(data_feed)

    def test_initialization(self, data_feed):
        """Test provider initialization."""
        provider = LiveMarketDataProvider(data_feed)

        assert provider.data_feed is data_feed
        assert isinstance(provider.underlying_bars, dict)

    def test_get_underlying_history_with_price(self, provider):
        """Test getting underlying history when price is available."""
        df = provider.get_underlying_history("SPX")

        assert not df.empty
        assert 'timestamp' in df.columns
        assert 'open' in df.columns
        assert 'high' in df.columns
        assert 'low' in df.columns
        assert 'close' in df.columns
        assert 'volume' in df.columns

        # Should have current price as OHLC
        assert df.iloc[0]['open'] == 6860.0
        assert df.iloc[0]['close'] == 6860.0

    def test_get_underlying_history_with_lookback(self, provider):
        """Test lookback limit on underlying history."""
        # Add multiple bars to data feed
        for i in range(10):
            bar = {
                'timestamp': datetime(2025, 12, 22, 9, 30 + i),
                'contract_symbol': 'SPXW251222C06875000',
                'underlying_ticker': 'SPX',
                'open': 10.0 + i,
                'high': 12.0 + i,
                'low': 9.5 + i,
                'close': 11.0 + i,
                'volume': 100,
                'vwap': 10.5 + i,
            }
            provider.data_feed.bars['SPXW251222C06875000'].append(bar)

        # Update underlying price tracking
        provider.data_feed.underlying_prices['SPX'] = 6870.0

        df = provider.get_underlying_history("SPX", lookback_bars=5)

        # Should only return 1 bar (current price)
        # Since we're using current price, not historical bars
        assert len(df) == 1

    def test_get_current_options_snapshot(self, provider):
        """Test getting current options snapshot."""
        df = provider.get_current_options_snapshot("SPX")

        assert not df.empty
        assert len(df) == 2  # Two contracts

        # Check columns
        expected_columns = [
            'timestamp', 'contract_symbol', 'underlying_ticker',
            'strike_price', 'option_type', 'expiration_date',
            'open', 'high', 'low', 'close', 'volume', 'vwap',
            'bid', 'ask', 'mark',
            'delta', 'gamma', 'theta', 'vega', 'rho',
            'implied_volatility'
        ]

        for col in expected_columns:
            assert col in df.columns

        # Check data
        call = df[df['option_type'] == 'C'].iloc[0]
        assert call['contract_symbol'] == 'SPXW251222C06875000'
        assert call['strike_price'] == 6875.0
        assert call['delta'] == 0.50

        put = df[df['option_type'] == 'P'].iloc[0]
        assert put['contract_symbol'] == 'SPXW251222P06850000'
        assert put['strike_price'] == 6850.0
        assert put['delta'] == -0.45

    def test_get_options_snapshot_empty(self):
        """Test getting options snapshot when no data available."""
        feed = RealtimeDataFeed(window_size=100, aggregate_interval_seconds=60)
        provider = LiveMarketDataProvider(feed)

        df = provider.get_current_options_snapshot("SPX")

        # Should return empty DataFrame with expected columns
        assert df.empty
        assert 'contract_symbol' in df.columns
        assert 'strike_price' in df.columns

    def test_get_underlying_history_empty(self):
        """Test getting underlying history when no data available."""
        feed = RealtimeDataFeed(window_size=100, aggregate_interval_seconds=60)
        provider = LiveMarketDataProvider(feed)

        df = provider.get_underlying_history("SPX")

        # Should return empty DataFrame with expected columns
        assert df.empty
        assert 'timestamp' in df.columns
        assert 'close' in df.columns

    def test_timestamp_conversion(self, provider):
        """Test that timestamps are properly converted to datetime."""
        df = provider.get_current_options_snapshot("SPX")

        assert not df.empty
        assert pd.api.types.is_datetime64_any_dtype(df['timestamp'])

    def test_snapshot_gets_latest_bar_per_contract(self, provider):
        """Test that snapshot returns only the latest bar for each contract."""
        # Add another bar for same contract
        bar3 = {
            'timestamp': datetime(2025, 12, 22, 9, 32),
            'contract_symbol': 'SPXW251222C06875000',
            'underlying_ticker': 'SPX',
            'open': 11.0,
            'high': 13.0,
            'low': 10.5,
            'close': 12.0,
            'volume': 120,
            'vwap': 11.5,
            'bid': 11.8,
            'ask': 12.2,
            'mark': 12.0,
            'strike_price': 6875.0,
            'option_type': 'C',
            'expiration_date': datetime(2025, 12, 22).date(),
            'delta': 0.52,
            'gamma': 0.01,
            'theta': -0.5,
            'vega': 0.2,
            'rho': 0.1,
            'implied_volatility': 0.15,
        }

        provider.data_feed.bars['SPXW251222C06875000'].append(bar3)

        df = provider.get_current_options_snapshot("SPX")

        # Should still have 2 contracts (latest bar for each)
        assert len(df) == 2

        # Call contract should have the newer bar
        call = df[df['contract_symbol'] == 'SPXW251222C06875000'].iloc[0]
        assert call['close'] == 12.0
        assert call['delta'] == 0.52
        assert call['timestamp'] == datetime(2025, 12, 22, 9, 32)
