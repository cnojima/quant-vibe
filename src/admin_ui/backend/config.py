"""
Configuration management for Admin UI service.

Loads settings from environment variables with sensible defaults.
"""

from pathlib import Path
from typing import Optional, Union

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Admin UI application settings."""

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent.parent / ".env"),
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

    # Security - loaded from environment variables or .env file
    admin_username: str = ""
    admin_password: str = ""
    jwt_secret_key: str = ""
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
    def parse_cors(cls, data: dict) -> dict:
        """Parse CORS origins from comma-separated string to list."""
        if isinstance(data, dict) and "cors_origins" in data:
            origins = data["cors_origins"]
            if isinstance(origins, str):
                data["cors_origins"] = [o.strip() for o in origins.split(",") if o.strip()]
        return data

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        """Validate that required security settings are configured."""
        if not self.admin_username:
            raise ValueError("ADMIN_USERNAME must be set in environment or .env file")
        if not self.admin_password:
            raise ValueError("ADMIN_PASSWORD must be set in environment or .env file")
        if not self.jwt_secret_key:
            raise ValueError("JWT_SECRET_KEY must be set in environment or .env file")
        return self

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # TimescaleDB - respects USE_REMOTE_TIMESCALE flag
    use_remote_timescale: bool = False
    timescale_host: str = "localhost"
    timescale_port: int = 5432
    timescale_db: str = "options_data"
    timescale_user: str = "quantvibe"
    timescale_password: str = "quantvibe_dev"

    # Remote TimescaleDB credentials
    remote_timescale_host: Optional[str] = None
    remote_timescale_port: Optional[int] = None
    remote_timescale_db: Optional[str] = None
    remote_timescale_user: Optional[str] = None
    remote_timescale_password: Optional[str] = None

    @model_validator(mode="after")
    def select_timescale_config(self) -> "Settings":
        """Select TimescaleDB config based on USE_REMOTE_TIMESCALE flag."""
        if not self.use_remote_timescale or not self.remote_timescale_host:
            return self

        self.timescale_host = self.remote_timescale_host
        if self.remote_timescale_port:
            self.timescale_port = self.remote_timescale_port
        if self.remote_timescale_db:
            self.timescale_db = self.remote_timescale_db
        if self.remote_timescale_user:
            self.timescale_user = self.remote_timescale_user
        if self.remote_timescale_password:
            self.timescale_password = self.remote_timescale_password
        return self

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
