"""Tests for symbol normalization utilities."""

from quant_vibe.utils.symbol_utils import normalize_option_ticker


class TestNormalizeOptionTicker:
    """Test option ticker normalization."""

    def test_schwab_streaming_format(self):
        """Test normalization of Schwab streaming format (with spaces)."""
        # Schwab streaming format has extra spaces
        ticker = "SPXW  260123P06860000"
        expected = "SPXW260123P06860000"
        assert normalize_option_ticker(ticker) == expected

    def test_schwab_poll_format(self):
        """Test normalization of Schwab poll format (already normalized)."""
        # Schwab poll format is already normalized
        ticker = "SPXW251226C06875000"
        expected = "SPXW251226C06875000"
        assert normalize_option_ticker(ticker) == expected

    def test_massive_format(self):
        """Test normalization of Massive API format (with O: prefix)."""
        # Massive format has O: prefix
        ticker = "O:SPXW251219C06945000"
        expected = "SPXW251219C06945000"
        assert normalize_option_ticker(ticker) == expected

    def test_massive_format_with_spaces(self):
        """Test normalization of Massive format with extra spaces."""
        # Edge case: Massive format with spaces (shouldn't happen but handle it)
        ticker = "O:SPXW  251219C06945000"
        expected = "SPXW251219C06945000"
        assert normalize_option_ticker(ticker) == expected

    def test_empty_string(self):
        """Test normalization of empty string."""
        assert normalize_option_ticker("") == ""

    def test_none_value(self):
        """Test normalization of None value."""
        assert normalize_option_ticker(None) is None

    def test_already_normalized(self):
        """Test normalization of already normalized ticker."""
        ticker = "SPXW251226C06875000"
        expected = "SPXW251226C06875000"
        assert normalize_option_ticker(ticker) == expected

    def test_multiple_spaces(self):
        """Test normalization with multiple spaces."""
        ticker = "SPXW    251226C06875000"
        expected = "SPXW251226C06875000"
        assert normalize_option_ticker(ticker) == expected

    def test_call_option(self):
        """Test normalization preserves call option indicator."""
        ticker = "SPXW  260123C06860000"
        result = normalize_option_ticker(ticker)
        assert "C" in result
        assert result == "SPXW260123C06860000"

    def test_put_option(self):
        """Test normalization preserves put option indicator."""
        ticker = "SPXW  260123P06860000"
        result = normalize_option_ticker(ticker)
        assert "P" in result
        assert result == "SPXW260123P06860000"

    def test_strike_price_preserved(self):
        """Test normalization preserves strike price digits."""
        ticker = "O:SPXW251226C06875000"
        result = normalize_option_ticker(ticker)
        # Strike should be last 8 digits
        assert result.endswith("06875000")

    def test_expiration_date_preserved(self):
        """Test normalization preserves expiration date."""
        ticker = "O:SPXW251226C06875000"
        result = normalize_option_ticker(ticker)
        # Expiration should be after underlying (SPXW)
        assert "251226" in result

    def test_multiple_normalizations_idempotent(self):
        """Test that normalizing multiple times gives same result."""
        ticker = "O:SPXW  251226C06875000"
        normalized_once = normalize_option_ticker(ticker)
        normalized_twice = normalize_option_ticker(normalized_once)
        assert normalized_once == normalized_twice
        assert normalized_once == "SPXW251226C06875000"
