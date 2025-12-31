"""
Configuration management for Admin UI service.

Loads settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Admin UI application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields from environment
    )

    # Application
    app_name: str = "Quant-Vibe Admin UI"
    debug: bool = False
    api_prefix: str = "/api"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Security
    admin_username: str = "admin"
    admin_password: str = "changeme"  # Should be set via environment
    jwt_secret_key: str = "change-this-secret-key"  # Must be set in production
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # CORS (can be comma-separated string or list)
    # Explicitly map to CORS_ORIGINS environment variable
    cors_origins: Union[str, list[str]] = Field(
        default="http://localhost:3000,http://localhost:8000",
        validation_alias="CORS_ORIGINS",
    )

    @model_validator(mode="before")
    @classmethod
    def parse_cors(cls, data: Any) -> Any:
        """Parse CORS origins from comma-separated string to list."""
        if isinstance(data, dict) and "cors_origins" in data:
            origins = data["cors_origins"]
            if isinstance(origins, str):
                data["cors_origins"] = [o.strip() for o in origins.split(",") if o.strip()]
        return data

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # TimescaleDB
    timescale_host: str = "localhost"
    timescale_port: int = 5432
    timescale_db: str = "options_data"
    timescale_user: str = "quantvibe"
    timescale_password: str = "quantvibe_dev"

    # Docker
    docker_host: Optional[str] = None  # Uses default docker socket if None

    # Project paths
    project_root: Path = Path(__file__).parent.parent.parent.parent
    config_dir: Path = project_root / "config"
    logs_dir: Path = project_root / "logs"
    tokens_dir: Path = project_root / "tokens"


# Singleton instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
