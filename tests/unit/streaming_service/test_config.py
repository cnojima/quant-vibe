"""Unit tests for StreamingConfig."""

import pytest
from streaming_service.config import StreamingConfig


class TestStreamingConfig:
    """Test cases for StreamingConfig dataclass."""

    def test_default_configuration(self):
        """Test that default configuration is created correctly."""
        config = StreamingConfig()

        assert config.max_dte == 45
        assert config.min_dte == 0
        assert config.strike_range_pct == 0.10
        assert config.aggregate_interval_seconds == 60
        assert config.token_refresh_minutes == 14
        assert config.max_symbols_per_subscription == 500
        assert config.tokens_db_path == "tokens/schwabdev_tokens.db"
        assert config.enrichment_refresh_minutes == 15

    def test_custom_configuration(self):
        """Test creating configuration with custom values."""
        config = StreamingConfig(
            max_dte=7,
            min_dte=0,
            strike_range_pct=0.05,
            aggregate_interval_seconds=300,
            token_refresh_minutes=10,
            max_symbols_per_subscription=200,
            tokens_db_path="/custom/path/tokens.db",
            enrichment_refresh_minutes=20,
        )

        assert config.max_dte == 7
        assert config.min_dte == 0
        assert config.strike_range_pct == 0.05
        assert config.aggregate_interval_seconds == 300
        assert config.token_refresh_minutes == 10
        assert config.max_symbols_per_subscription == 200
        assert config.tokens_db_path == "/custom/path/tokens.db"
        assert config.enrichment_refresh_minutes == 20

    def test_partial_custom_configuration(self):
        """Test creating configuration with some custom values."""
        config = StreamingConfig(
            max_dte=30,
            strike_range_pct=0.15,
        )

        # Custom values
        assert config.max_dte == 30
        assert config.strike_range_pct == 0.15

        # Default values
        assert config.min_dte == 0
        assert config.aggregate_interval_seconds == 60
        assert config.token_refresh_minutes == 14

    def test_validation_max_dte_less_than_min_dte(self):
        """Test that validation fails when max_dte < min_dte."""
        with pytest.raises(ValueError, match="max_dte.*must be >= min_dte"):
            StreamingConfig(max_dte=5, min_dte=10)

    def test_validation_strike_range_too_low(self):
        """Test that validation fails when strike_range_pct <= 0."""
        with pytest.raises(ValueError, match="strike_range_pct must be between 0 and 1.0"):
            StreamingConfig(strike_range_pct=0.0)

        with pytest.raises(ValueError, match="strike_range_pct must be between 0 and 1.0"):
            StreamingConfig(strike_range_pct=-0.1)

    def test_validation_strike_range_too_high(self):
        """Test that validation fails when strike_range_pct > 1.0."""
        with pytest.raises(ValueError, match="strike_range_pct must be between 0 and 1.0"):
            StreamingConfig(strike_range_pct=1.5)

    def test_validation_aggregate_interval_invalid(self):
        """Test that validation fails when aggregate_interval_seconds < 1."""
        with pytest.raises(ValueError, match="aggregate_interval_seconds must be >= 1"):
            StreamingConfig(aggregate_interval_seconds=0)

        with pytest.raises(ValueError, match="aggregate_interval_seconds must be >= 1"):
            StreamingConfig(aggregate_interval_seconds=-10)

    def test_validation_token_refresh_invalid(self):
        """Test that validation fails when token_refresh_minutes < 1."""
        with pytest.raises(ValueError, match="token_refresh_minutes must be >= 1"):
            StreamingConfig(token_refresh_minutes=0)

        with pytest.raises(ValueError, match="token_refresh_minutes must be >= 1"):
            StreamingConfig(token_refresh_minutes=-5)

    def test_edge_case_max_dte_equals_min_dte(self):
        """Test that max_dte == min_dte is valid."""
        config = StreamingConfig(max_dte=5, min_dte=5)
        assert config.max_dte == 5
        assert config.min_dte == 5

    def test_edge_case_strike_range_minimum(self):
        """Test strike_range_pct at minimum valid value."""
        config = StreamingConfig(strike_range_pct=0.01)
        assert config.strike_range_pct == 0.01

    def test_edge_case_strike_range_maximum(self):
        """Test strike_range_pct at maximum valid value."""
        config = StreamingConfig(strike_range_pct=1.0)
        assert config.strike_range_pct == 1.0

    def test_edge_case_aggregate_interval_minimum(self):
        """Test aggregate_interval_seconds at minimum valid value."""
        config = StreamingConfig(aggregate_interval_seconds=1)
        assert config.aggregate_interval_seconds == 1

    def test_dataclass_immutability(self):
        """Test that config can be modified (dataclass is not frozen)."""
        config = StreamingConfig()
        config.max_dte = 30  # Should not raise
        assert config.max_dte == 30

    def test_dataclass_equality(self):
        """Test that two configs with same values are equal."""
        config1 = StreamingConfig(max_dte=30, strike_range_pct=0.15)
        config2 = StreamingConfig(max_dte=30, strike_range_pct=0.15)

        assert config1 == config2

    def test_dataclass_inequality(self):
        """Test that two configs with different values are not equal."""
        config1 = StreamingConfig(max_dte=30)
        config2 = StreamingConfig(max_dte=45)

        assert config1 != config2

    def test_repr_output(self):
        """Test that repr provides useful output."""
        config = StreamingConfig(max_dte=7)
        repr_str = repr(config)

        assert "StreamingConfig" in repr_str
        assert "max_dte=7" in repr_str
