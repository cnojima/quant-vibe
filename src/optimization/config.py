"""
Configuration for optimization service.
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class OptimizationConfig:
    """Configuration for optimization service."""

    # Service mode
    service_mode: str = "worker"  # 'api' or 'worker'

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Database configuration
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "options_data"
    db_user: str = "quantvibe"
    db_password: str = "quantvibe_dev"

    # API configuration (when running in API mode)
    api_host: str = "0.0.0.0"
    api_port: int = 8200

    # Worker configuration
    worker_concurrency: int = 1
    max_memory_mb: int = 7000

    # Cache configuration
    data_cache_ttl: int = 3600  # 1 hour
    results_base_dir: str = "/app/results/optimization"

    # Logging
    log_level: str = "WARNING"

    @classmethod
    def from_environment(cls) -> "OptimizationConfig":
        """Create configuration from environment variables."""
        return cls(
            service_mode=os.getenv("SERVICE_MODE", "worker"),
            # Redis
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            # Database
            db_host=os.getenv("TIMESCALE_HOST", "localhost"),
            db_port=int(os.getenv("TIMESCALE_PORT", "5432")),
            db_name=os.getenv("TIMESCALE_DB", "options_data"),
            db_user=os.getenv("TIMESCALE_USER", "quantvibe"),
            db_password=os.getenv("TIMESCALE_PASSWORD", "quantvibe_dev"),
            # API
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("API_PORT", "8200")),
            # Worker
            worker_concurrency=int(os.getenv("WORKER_CONCURRENCY", "1")),
            max_memory_mb=int(os.getenv("MAX_MEMORY_MB", "7000")),
            # Cache
            data_cache_ttl=int(os.getenv("DATA_CACHE_TTL", "3600")),
            results_base_dir=os.getenv("RESULTS_BASE_DIR", "/app/results/optimization"),
            # Logging
            log_level=os.getenv("LOG_LEVEL", "WARNING"),
        )

    @property
    def db_connection_string(self) -> str:
        """Get database connection string."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_url(self) -> str:
        """Get Redis connection URL."""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def validate(self) -> None:
        """Validate configuration."""
        if self.service_mode not in ("api", "worker"):
            raise ValueError(f"Invalid service mode: {self.service_mode}")

        if self.worker_concurrency < 1:
            raise ValueError(f"Worker concurrency must be >= 1: {self.worker_concurrency}")

        if self.max_memory_mb < 100:
            raise ValueError(f"Max memory must be >= 100MB: {self.max_memory_mb}")

        if self.data_cache_ttl < 0:
            raise ValueError(f"Cache TTL must be >= 0: {self.data_cache_ttl}")

        # Ensure results directory exists
        results_path = Path(self.results_base_dir)
        results_path.mkdir(parents=True, exist_ok=True)