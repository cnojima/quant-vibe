"""Configuration for Token Management Service."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class TokenServiceConfig:
    """Configuration for token management service.

    Attributes:
        schwab_api_key: Schwab API key (consumer key)
        schwab_api_secret: Schwab app secret (consumer secret)
        schwab_callback_url: OAuth callback URL
        tokens_db_path: Path to schwabdev tokens database
        refresh_interval_minutes: Minutes between automatic token refreshes
        host: Service host address
        port: Service port number
        redis_host: Redis host for event publishing
        redis_port: Redis port
        redis_db: Redis database number
        enable_redis: Enable Redis event publishing
        log_dir: Directory for log files
        log_level: Logging level
    """

    # Schwab API credentials
    schwab_api_key: str
    schwab_api_secret: str
    schwab_callback_url: str
    tokens_db_path: str

    # Token refresh settings
    refresh_interval_minutes: int = 14

    # Service settings
    host: str = "0.0.0.0"
    port: int = 8100

    # Redis settings (for event publishing)
    redis_host: Optional[str] = None
    redis_port: int = 6379
    redis_db: int = 0
    enable_redis: bool = True

    # Logging
    log_dir: str = "logs/token_service"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "TokenServiceConfig":
        """Create configuration from environment variables.

        Returns:
            TokenServiceConfig instance

        Raises:
            ValueError: If required environment variables are missing
        """
        api_key = os.getenv("SCHWAB_API_KEY")
        api_secret = os.getenv("SCHWAB_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError(
                "Missing required Schwab API credentials. "
                "Set SCHWAB_API_KEY and SCHWAB_API_SECRET in .env file."
            )

        return cls(
            schwab_api_key=api_key,
            schwab_api_secret=api_secret,
            schwab_callback_url=os.getenv(
                "SCHWAB_CALLBACK_URL",
                "https://quantvibe.net:53430/"
            ),
            tokens_db_path=os.getenv(
                "SCHWAB_TOKENS_DB",
                "./tokens/schwabdev_tokens.db"
            ),
            refresh_interval_minutes=int(os.getenv(
                "TOKEN_REFRESH_INTERVAL_MINUTES",
                "14"
            )),
            host=os.getenv("TOKEN_SERVICE_HOST", "0.0.0.0"),
            port=int(os.getenv("TOKEN_SERVICE_PORT", "8100")),
            redis_host=os.getenv("REDIS_HOST"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            enable_redis=os.getenv("TOKEN_SERVICE_ENABLE_REDIS", "true").lower() == "true",
            log_dir=os.getenv("TOKEN_SERVICE_LOG_DIR", "logs/token_service"),
            log_level=os.getenv("TOKEN_SERVICE_LOG_LEVEL", "INFO"),
        )
