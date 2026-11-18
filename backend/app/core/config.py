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
    APP_ENV: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    BRIDGE_INTERNAL_URL: str = "http://127.0.0.1:8010"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://aiws:change-me-db-password@127.0.0.1:5432/aiworkspace"
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    JWT_SECRET: str = "change-me-to-a-long-random-secret-min-32-chars"
    JWT_ACCESS_MINUTES: int = 30
    JWT_REFRESH_DAYS: int = 14
    WS_TICKET_SECONDS: int = 60

    ADMIN_BOOTSTRAP_USERNAME: str = "admin"
    ADMIN_BOOTSTRAP_PASSWORD: str = "change-me-admin-password-min-10"

    WORKER_TOKEN: str = "change-me-worker-token"
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3010,http://127.0.0.1:3000,http://127.0.0.1:3010"
    )
    ENCRYPTION_KEY: str = ""

    DEFAULT_CHAT_MODEL: str = "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q6_k"
    DEFAULT_EMBED_MODEL: str = "text-embedding-embeddinggemma-300m"
    EMBED_DIM: int = 768
    RAG_CHUNK_CHARS: int = 1800
    RAG_CHUNK_OVERLAP: int = 200
    RAG_CONTEXT_CHARS: int = 6000
    RAG_HNSW_EF_SEARCH: int = 40

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

    LOGIN_RATE_LIMIT: int = 10
    LOGIN_RATE_WINDOW_SEC: int = 300
    AUTH_MUTATION_RATE_LIMIT: int = 20
    AUTH_MUTATION_WINDOW_SEC: int = 300
    UPLOAD_RATE_LIMIT: int = 20
    UPLOAD_RATE_WINDOW_SEC: int = 300
    AUDIT_RETENTION_DAYS: int = 90
    WORKER_HEARTBEAT_TTL_SEC: int = 60
    TRUST_PROXY_HEADERS: bool = False

    LOG_FILE: str = ""
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def validate_production_secrets(self) -> None:
        """Fail fast if placeholder or weak secrets are used in production."""
        if self.APP_ENV.strip().lower() != "production" and not self.COOKIE_SECURE:
            return
        errors: list[str] = []
        if "change-me" in self.JWT_SECRET.lower() or len(self.JWT_SECRET.strip()) < 32:
            errors.append("JWT_SECRET must be >= 32 chars and not a placeholder")
        if "change-me" in self.WORKER_TOKEN.lower() or len(self.WORKER_TOKEN.strip()) < 16:
            errors.append("WORKER_TOKEN must be >= 16 chars and not a placeholder")
        if (
            "change-me" in self.ADMIN_BOOTSTRAP_PASSWORD.lower()
            or len(self.ADMIN_BOOTSTRAP_PASSWORD) < 10
        ):
            errors.append("ADMIN_BOOTSTRAP_PASSWORD must be >= 10 chars and not a placeholder")
        if errors:
            raise RuntimeError("Insecure production secrets: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
