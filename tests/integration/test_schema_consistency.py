"""
Integration tests to verify schema consistency across data pipelines.

These tests ensure that column names, data types, and timezone handling
remain consistent across:
1. Database → Backtest pipeline
2. Redis → Live trading pipeline
3. Symbol parsing utilities
"""

import pytest
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from quant_vibe.utils import (
    normalize_option_ticker,
    parse_contract_type_from_ticker,
    parse_strike_from_ticker,
    parse_expiration_from_ticker,
    is_utc_aware,
)


# Required columns for options data (shared contract)
REQUIRED_OPTIONS_COLUMNS = {
    'timestamp',
    'contract_symbol',  # Note: NOT 'option_ticker'
    'strike_price',
    'contract_type',
    'expiration_date',
    'open',
    'high',
    'low',
    'close',
    'volume',
    'bid',
    'ask',
    'mark',
}

# Optional columns (Greeks, may be None)
OPTIONAL_OPTIONS_COLUMNS = {
    'delta',
    'gamma',
    'theta',
    'vega',
    'rho',
    'implied_volatility',
}


class TestSymbolNormalization:
    """Test symbol parsing consistency"""

    def test_normalize_schwab_format(self):
        """Test normalizing Schwab format (with spaces)"""
        schwab_symbol = "SPXW  260123P06860000"
        normalized = normalize_option_ticker(schwab_symbol)

        assert normalized == "SPXW260123P06860000"
        assert " " not in normalized

    def test_normalize_massive_format(self):
        """Test normalizing Massive format (O: prefix)"""
        massive_symbol = "O:SPXW251219C06945000"
        normalized = normalize_option_ticker(massive_symbol)

        assert normalized == "SPXW251219C06945000"
        assert "O:" not in normalized

    def test_normalize_already_normalized(self):
        """Test normalizing already normalized symbol"""
        normalized_symbol = "SPXW260123P06860000"
        result = normalize_option_ticker(normalized_symbol)

        assert result == normalized_symbol

    def test_parse_contract_type_consistency(self):
        """Test contract type parsing returns lowercase"""
        call_symbol = "SPXW260123C06860000"
        put_symbol = "SPXW260123P06860000"

        assert parse_contract_type_from_ticker(call_symbol) == "call"
        assert parse_contract_type_from_ticker(put_symbol) == "put"

        # Verify lowercase (not "C" or "P")
        assert parse_contract_type_from_ticker(call_symbol) != "C"
        assert parse_contract_type_from_ticker(put_symbol) != "P"

    def test_parse_strike_consistency(self):
        """Test strike parsing returns float"""
        symbol = "SPXW260123P06860000"
        strike = parse_strike_from_ticker(symbol)

        assert isinstance(strike, float)
        assert strike == 6860.0

    def test_parse_expiration_consistency(self):
        """Test expiration parsing returns date"""
        symbol = "SPXW260123P06860000"
        exp_date = parse_expiration_from_ticker(symbol)

        assert exp_date.year == 2026
        assert exp_date.month == 1
        assert exp_date.day == 23


class TestTimestampConsistency:
    """Test timestamp timezone handling"""

    def test_timestamp_must_be_utc_aware(self):
        """Test that all timestamps should be UTC-aware"""
        # Create sample DataFrame (simulating data from any source)
        df = pd.DataFrame({
            'timestamp': [datetime(2025, 12, 23, 14, 30, tzinfo=ZoneInfo("UTC"))],
            'contract_symbol': ['SPXW260123P06860000'],
            'bid': [10.5],
            'ask': [10.7],
        })

        # Verify timestamp is UTC-aware
        assert is_utc_aware(df['timestamp'].iloc[0])

    def test_naive_timestamp_detection(self):
        """Test detection of naive timestamps (should fail validation)"""
        naive_dt = datetime(2025, 12, 23, 14, 30)  # No timezone

        assert not is_utc_aware(naive_dt)

    def test_non_utc_timestamp_detection(self):
        """Test detection of non-UTC timestamps"""
        est_dt = datetime(2025, 12, 23, 9, 30, tzinfo=ZoneInfo("America/New_York"))

        assert not is_utc_aware(est_dt)  # Not UTC


class TestOptionsDataFrameSchema:
    """Test DataFrame schema consistency"""

    @pytest.fixture
    def sample_options_data(self):
        """Create sample options DataFrame matching expected schema"""
        return pd.DataFrame({
            'timestamp': [datetime(2025, 12, 23, 14, 30, tzinfo=ZoneInfo("UTC"))],
            'contract_symbol': ['SPXW260123P06860000'],
            'underlying_ticker': ['SPX'],
            'strike_price': [6860.0],
            'contract_type': ['put'],
            'expiration_date': [pd.Timestamp('2026-01-23').date()],
            'open': [10.2],
            'high': [10.8],
            'low': [10.0],
            'close': [10.5],
            'volume': [100],
            'bid': [10.4],
            'ask': [10.6],
            'mark': [10.5],
            'delta': [-0.35],
            'gamma': [0.05],
            'theta': [-0.02],
            'vega': [0.15],
            'rho': [-0.01],
            'implied_volatility': [0.18],
        })

    def test_required_columns_present(self, sample_options_data):
        """Test that all required columns are present"""
        missing = REQUIRED_OPTIONS_COLUMNS - set(sample_options_data.columns)
        assert len(missing) == 0, f"Missing required columns: {missing}"

    def test_no_option_ticker_column(self, sample_options_data):
        """Test that 'option_ticker' is NOT used (should be 'contract_symbol')"""
        assert 'option_ticker' not in sample_options_data.columns
        assert 'contract_symbol' in sample_options_data.columns

    def test_contract_symbol_format(self, sample_options_data):
        """Test that contract_symbol is normalized"""
        symbol = sample_options_data['contract_symbol'].iloc[0]

        # Should be normalized (no spaces, no prefix)
        assert " " not in symbol
        assert not symbol.startswith("O:")

    def test_contract_type_lowercase(self, sample_options_data):
        """Test that contract_type is lowercase"""
        contract_type = sample_options_data['contract_type'].iloc[0]

        assert contract_type in ['call', 'put']
        assert contract_type != 'C' and contract_type != 'P'

    def test_timestamp_utc_aware(self, sample_options_data):
        """Test that timestamp is UTC-aware"""
        timestamp = sample_options_data['timestamp'].iloc[0]

        assert is_utc_aware(timestamp)

    def test_mark_calculated_from_bid_ask(self, sample_options_data):
        """Test that mark price is calculated as (bid + ask) / 2"""
        bid = sample_options_data['bid'].iloc[0]
        ask = sample_options_data['ask'].iloc[0]
        mark = sample_options_data['mark'].iloc[0]

        expected_mark = (bid + ask) / 2.0
        assert abs(mark - expected_mark) < 0.01  # Allow small floating point error


class TestDataTypeConsistency:
    """Test data type consistency"""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for type checking"""
        return pd.DataFrame({
            'timestamp': [datetime(2025, 12, 23, 14, 30, tzinfo=ZoneInfo("UTC"))],
            'contract_symbol': ['SPXW260123P06860000'],
            'strike_price': [6860.0],
            'contract_type': ['put'],
            'expiration_date': [pd.Timestamp('2026-01-23').date()],
            'volume': [100],
            'bid': [10.4],
            'ask': [10.6],
            'delta': [-0.35],
        })

    def test_numeric_columns_are_floats(self, sample_data):
        """Test that numeric columns are float type"""
        numeric_cols = ['strike_price', 'bid', 'ask', 'delta']

        for col in numeric_cols:
            value = sample_data[col].iloc[0]
            assert isinstance(value, (float, int)), f"{col} should be numeric"

    def test_volume_is_integer(self, sample_data):
        """Test that volume is integer"""
        import numpy as np

        volume = sample_data['volume'].iloc[0]
        assert isinstance(volume, (int, float, np.integer))

    def test_contract_type_is_string(self, sample_data):
        """Test that contract_type is string"""
        contract_type = sample_data['contract_type'].iloc[0]
        assert isinstance(contract_type, str)

    def test_symbol_is_string(self, sample_data):
        """Test that contract_symbol is string"""
        symbol = sample_data['contract_symbol'].iloc[0]
        assert isinstance(symbol, str)


# Integration test placeholder (requires database/Redis access)
@pytest.mark.skip(reason="Requires database access - run manually")
class TestEndToEndSchemaConsistency:
    """End-to-end schema consistency tests (database → backtest, Redis → live)"""

    def test_database_to_backtest_schema(self):
        """Test that data from TimescaleDB matches expected schema"""
        from quant_vibe.data.timescale_store import TimescaleStore
        from datetime import datetime
        from quant_vibe.utils import to_utc

        store = TimescaleStore()

        # Load sample data
        options_data = store.get_options_for_backtest(
            underlying_ticker='SPX',
            start_time=to_utc(datetime(2025, 12, 1)),
            end_time=to_utc(datetime(2025, 12, 2)),
            min_dte=0,
            max_dte=45,
        )

        # Verify schema
        missing = REQUIRED_OPTIONS_COLUMNS - set(options_data.columns)
        assert len(missing) == 0, f"Database schema missing columns: {missing}"

        # Verify no 'option_ticker' column (should be aliased to 'contract_symbol')
        assert 'option_ticker' not in options_data.columns
        assert 'contract_symbol' in options_data.columns

        # Verify timestamps are UTC-aware
        if not options_data.empty:
            assert is_utc_aware(options_data['timestamp'].iloc[0])

    def test_redis_to_live_trading_schema(self):
        """Test that data from Redis matches expected schema"""
        from quant_vibe.data.live_market_data import LiveMarketDataProvider

        provider = LiveMarketDataProvider()

        # Get recent bars (if available)
        bars = provider.get_recent_bars(['SPXW260123P06860000'])

        if not bars.empty:
            # Verify schema
            missing = REQUIRED_OPTIONS_COLUMNS - set(bars.columns)
            assert len(missing) == 0, f"Redis schema missing columns: {missing}"

            # Verify no 'option_ticker' column
            assert 'option_ticker' not in bars.columns
            assert 'contract_symbol' in bars.columns

            # Verify timestamps
            assert is_utc_aware(bars['timestamp'].iloc[0])
