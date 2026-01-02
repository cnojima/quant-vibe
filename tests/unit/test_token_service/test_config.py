"""Unit tests for TokenServiceConfig."""

import pytest
import os
from unittest.mock import patch
from token_service.config import TokenServiceConfig


class TestTokenServiceConfig:
    """Test cases for TokenServiceConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TokenServiceConfig(
            schwab_api_key="test_key",
            schwab_api_secret="test_secret",
            schwab_callback_url="https://test.com",
            tokens_db_path="/path/to/tokens.db"
        )

        assert config.schwab_api_key == "test_key"
        assert config.schwab_api_secret == "test_secret"
        assert config.schwab_callback_url == "https://test.com"
        assert config.tokens_db_path == "/path/to/tokens.db"
        assert config.refresh_interval_minutes == 14
        assert config.host == "0.0.0.0"
        assert config.port == 8100
        assert config.redis_host is None
        assert config.redis_port == 6379
        assert config.redis_db == 0
        assert config.enable_redis is True
        assert config.log_dir == "logs/token_service"
        assert config.log_level == "INFO"

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = TokenServiceConfig(
            schwab_api_key="custom_key",
            schwab_api_secret="custom_secret",
            schwab_callback_url="https://custom.com",
            tokens_db_path="/custom/tokens.db",
            refresh_interval_minutes=10,
            host="127.0.0.1",
            port=9000,
            redis_host="redis.local",
            redis_port=6380,
            redis_db=1,
            enable_redis=False,
            log_dir="/var/log/token_service",
            log_level="DEBUG"
        )

        assert config.schwab_api_key == "custom_key"
        assert config.schwab_api_secret == "custom_secret"
        assert config.schwab_callback_url == "https://custom.com"
        assert config.tokens_db_path == "/custom/tokens.db"
        assert config.refresh_interval_minutes == 10
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.redis_host == "redis.local"
        assert config.redis_port == 6380
        assert config.redis_db == 1
        assert config.enable_redis is False
        assert config.log_dir == "/var/log/token_service"
        assert config.log_level == "DEBUG"

    @patch.dict(os.environ, {
        "SCHWAB_API_KEY": "env_key",
        "SCHWAB_API_SECRET": "env_secret",
        "SCHWAB_CALLBACK_URL": "https://env.com",
        "SCHWAB_TOKENS_DB": "/env/tokens.db",
        "TOKEN_REFRESH_INTERVAL_MINUTES": "20",
        "TOKEN_SERVICE_HOST": "0.0.0.0",
        "TOKEN_SERVICE_PORT": "8100",
        "REDIS_HOST": "redis.env",
        "REDIS_PORT": "6380",
        "REDIS_DB": "2",
        "TOKEN_SERVICE_ENABLE_REDIS": "false",
        "TOKEN_SERVICE_LOG_DIR": "/env/logs",
        "TOKEN_SERVICE_LOG_LEVEL": "WARNING"
    })
    def test_from_env(self):
        """Test configuration from environment variables."""
        config = TokenServiceConfig.from_env()

        assert config.schwab_api_key == "env_key"
        assert config.schwab_api_secret == "env_secret"
        assert config.schwab_callback_url == "https://env.com"
        assert config.tokens_db_path == "/env/tokens.db"
        assert config.refresh_interval_minutes == 20
        assert config.host == "0.0.0.0"
        assert config.port == 8100
        assert config.redis_host == "redis.env"
        assert config.redis_port == 6380
        assert config.redis_db == 2
        assert config.enable_redis is False
        assert config.log_dir == "/env/logs"
        assert config.log_level == "WARNING"

    @patch.dict(os.environ, {
        "SCHWAB_API_KEY": "key",
        "SCHWAB_API_SECRET": "secret"
    })
    def test_from_env_with_defaults(self):
        """Test from_env uses defaults when env vars not set."""
        config = TokenServiceConfig.from_env()

        assert config.schwab_callback_url == "https://127.0.0.1:8182/"
        assert config.tokens_db_path == "./tokens/schwabdev_tokens.db"
        assert config.refresh_interval_minutes == 14
        assert config.port == 8100

    @patch.dict(os.environ, {}, clear=True)
    def test_from_env_missing_api_key(self):
        """Test from_env raises error when API key missing."""
        with pytest.raises(ValueError, match="Missing required Schwab API credentials"):
            TokenServiceConfig.from_env()

    @patch.dict(os.environ, {"SCHWAB_API_KEY": "key"}, clear=True)
    def test_from_env_missing_api_secret(self):
        """Test from_env raises error when API secret missing."""
        with pytest.raises(ValueError, match="Missing required Schwab API credentials"):
            TokenServiceConfig.from_env()

    @patch.dict(os.environ, {
        "SCHWAB_API_KEY": "key",
        "SCHWAB_API_SECRET": "secret",
        "TOKEN_SERVICE_ENABLE_REDIS": "TRUE"
    })
    def test_from_env_redis_enable_case_insensitive(self):
        """Test that enable_redis handles case-insensitive values."""
        config = TokenServiceConfig.from_env()
        assert config.enable_redis is True

    @patch.dict(os.environ, {
        "SCHWAB_API_KEY": "key",
        "SCHWAB_API_SECRET": "secret",
        "TOKEN_SERVICE_ENABLE_REDIS": "False"
    })
    def test_from_env_redis_disable(self):
        """Test that enable_redis correctly parses 'false'."""
        config = TokenServiceConfig.from_env()
        assert config.enable_redis is False

    @patch.dict(os.environ, {
        "SCHWAB_API_KEY": "key",
        "SCHWAB_API_SECRET": "secret",
        "TOKEN_REFRESH_INTERVAL_MINUTES": "invalid"
    })
    def test_from_env_invalid_refresh_interval(self):
        """Test from_env with invalid refresh interval."""
        with pytest.raises(ValueError):
            TokenServiceConfig.from_env()

    @patch.dict(os.environ, {
        "SCHWAB_API_KEY": "key",
        "SCHWAB_API_SECRET": "secret",
        "TOKEN_SERVICE_PORT": "invalid"
    })
    def test_from_env_invalid_port(self):
        """Test from_env with invalid port."""
        with pytest.raises(ValueError):
            TokenServiceConfig.from_env()

    def test_dataclass_equality(self):
        """Test that configs with same values are equal."""
        config1 = TokenServiceConfig(
            schwab_api_key="key",
            schwab_api_secret="secret",
            schwab_callback_url="https://test.com",
            tokens_db_path="/path/tokens.db"
        )
        config2 = TokenServiceConfig(
            schwab_api_key="key",
            schwab_api_secret="secret",
            schwab_callback_url="https://test.com",
            tokens_db_path="/path/tokens.db"
        )

        assert config1 == config2

    def test_dataclass_inequality(self):
        """Test that configs with different values are not equal."""
        config1 = TokenServiceConfig(
            schwab_api_key="key1",
            schwab_api_secret="secret",
            schwab_callback_url="https://test.com",
            tokens_db_path="/path/tokens.db"
        )
        config2 = TokenServiceConfig(
            schwab_api_key="key2",
            schwab_api_secret="secret",
            schwab_callback_url="https://test.com",
            tokens_db_path="/path/tokens.db"
        )

        assert config1 != config2
