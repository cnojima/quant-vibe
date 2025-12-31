"""Configuration for streaming service."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class StreamingConfig:
    """Configuration for SPXW options streaming service.

    Attributes:
        max_dte: Maximum days to expiration
        min_dte: Minimum days to expiration
        strike_range_pct: Strike range as % of underlying (e.g., 0.10 = ±10%)
        aggregate_interval_seconds: Seconds to aggregate into bars (60 = 1min)
        token_refresh_minutes: Minutes between token refreshes (default: 14)
        max_symbols_per_subscription: Max symbols per Schwab subscription (default: 500)
        tokens_db_path: Path to schwabdev token database (legacy - for fallback)
        enrichment_refresh_minutes: Minutes between contract cache refreshes (default: 15)
        enable_redis: Enable Redis pub/sub for real-time messaging (default: True)
        redis_host: Redis host (default: from env or 'localhost')
        redis_port: Redis port (default: from env or 6379)
        redis_db: Redis database number (default: from env or 0)
        token_service_url: Token service URL (default: from env or None for legacy mode)
        use_token_service: Use centralized token service instead of local tokens (default: True)
    """

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
        # Load token service URL from environment if not set
        if self.token_service_url is None:
            self.token_service_url = os.getenv("TOKEN_SERVICE_URL")

        # Disable token service if URL not provided
        if not self.token_service_url and self.use_token_service:
            self.use_token_service = False

        # Validate configuration
        if self.max_dte < self.min_dte:
            raise ValueError(f"max_dte ({self.max_dte}) must be >= min_dte ({self.min_dte})")

        if self.strike_range_pct <= 0 or self.strike_range_pct > 1.0:
            raise ValueError(f"strike_range_pct must be between 0 and 1.0, got {self.strike_range_pct}")

        if self.aggregate_interval_seconds < 1:
            raise ValueError(f"aggregate_interval_seconds must be >= 1, got {self.aggregate_interval_seconds}")

        if self.token_refresh_minutes < 1:
            raise ValueError(f"token_refresh_minutes must be >= 1, got {self.token_refresh_minutes}")
