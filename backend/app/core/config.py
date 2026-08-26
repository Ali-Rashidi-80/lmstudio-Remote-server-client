"""Application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
VERSION_FILE = ROOT / "VERSION"


def _read_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip() or "20.0.0"
    return "20.0.0"


class Settings(BaseSettings):
    APP_VERSION: str = Field(default_factory=_read_version)
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://aiws:change-me-db-password@localhost:5432/aiworkspace"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "change-me-to-a-long-random-secret"
    JWT_ACCESS_MINUTES: int = 30
    JWT_REFRESH_DAYS: int = 14
    WS_TICKET_SECONDS: int = 60

    ADMIN_BOOTSTRAP_USERNAME: str = "admin"
    ADMIN_BOOTSTRAP_PASSWORD: str = "change-me-admin-password-min-10"

    WORKER_TOKEN: str = "change-me-worker-token"
    CORS_ORIGINS: str = "http://localhost:3000"
    ENCRYPTION_KEY: str = ""

    DEFAULT_CHAT_MODEL: str = "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q6_k"
    DEFAULT_EMBED_MODEL: str = "text-embedding-embeddinggemma-300m"
    EMBED_DIM: int = 768

    COOKIE_SECURE: bool = False
    # If set, Bridge embeds directly against LM Studio (local lab only).
    # Leave empty in production so embeddings go through the PC Worker.
    EMBED_DIRECT_URL: str = ""
    # arq (default) | inline (pytest / no rag-worker process)
    RAG_INGEST_MODE: str = "arq"
    UPLOAD_DIR: str = "storage/uploads"
    MAX_DOC_BYTES: int = 10 * 1024 * 1024
    MAX_IMAGE_BYTES: int = 2 * 1024 * 1024
    INVITE_DAYS: int = 7

    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
