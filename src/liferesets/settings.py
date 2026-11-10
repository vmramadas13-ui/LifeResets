"""Application settings loaded from environment variables or a local .env file."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the LifeResets API."""

    model_config = SettingsConfigDict(
        env_prefix="LIFERESETS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LifeResets API"
    database_url: str = "sqlite:///./liferesets.db"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    environment: Literal["development", "test", "staging", "production"] = "development"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
