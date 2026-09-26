"""Environment-backed application settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_callback_url: str = "http://localhost:8000/api/v1/auth/callback"
    gemini_api_key: str | None = None
    jwt_secret: str | None = None
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings without opening network connections."""
    return Settings()
