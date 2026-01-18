"""Configuration for streaming service."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class StreamingConfig:
    """Configuration for SPXW options streaming service."""

    max_dte: int = 7
    min_dte: int = 0
    strike_range_pct: float = 0.10
    aggregate_interval_seconds: int = 60
    token_refresh_minutes: int = 14
    max_symbols_per_subscription: int = 500
    tokens_db_path: str = "tokens/schwabdev_tokens.db"
    enrichment_refresh_minutes: int = 15
    enable_redis: bool = True
    redis_host: Optional[str] = None
    redis_port: Optional[int] = None
    redis_db: Optional[int] = None
    token_service_url: Optional[str] = None
    use_token_service: bool = True

    def __post_init__(self):
        """Validate configuration and load from environment."""
        if not self.token_service_url:
            self.token_service_url = os.getenv("TOKEN_SERVICE_URL")

        if not self.token_service_url and self.use_token_service:
            self.use_token_service = False

        self._validate()

    def _validate(self):
        """Validate configuration values."""
        if self.max_dte < self.min_dte:
            raise ValueError(f"max_dte ({self.max_dte}) must be >= min_dte ({self.min_dte})")

        if not 0 < self.strike_range_pct <= 1.0:
            raise ValueError(f"strike_range_pct must be between 0 and 1.0, got {self.strike_range_pct}")

        if self.aggregate_interval_seconds < 1:
            raise ValueError(f"aggregate_interval_seconds must be >= 1, got {self.aggregate_interval_seconds}")

        if self.token_refresh_minutes < 1:
            raise ValueError(f"token_refresh_minutes must be >= 1, got {self.token_refresh_minutes}")
