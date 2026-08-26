"""Legacy settings shim — prefer backend.app.core.config.Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENCRYPTION_KEY: str = ""
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


try:
    settings = Settings()
except Exception:  # pylint: disable=broad-exception-caught
    settings = None
