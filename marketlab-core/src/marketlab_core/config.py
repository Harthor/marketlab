from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class MarketLabSettings(BaseSettings):
    """Application settings loaded from environment variables and .env."""

    cache_root: Path = "~/.cache/marketlab-core"
    default_timezone: str = "UTC"
    default_tolerance: str = "60s"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="MARKETLAB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> MarketLabSettings:
    """Return loaded configuration."""

    return MarketLabSettings()
