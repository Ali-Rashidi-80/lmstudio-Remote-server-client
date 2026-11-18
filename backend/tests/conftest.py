"""Shared fixtures — real Postgres/Redis required (no fakes that hide failures)."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Force local compose defaults unless caller overrides
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://aiws:change-me-db-password@127.0.0.1:55432/aiworkspace",
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:26379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-key-please-change-min-32-chars")
os.environ.setdefault("WORKER_TOKEN", "test-worker-token-min-16")
os.environ.setdefault("ADMIN_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "adminpass12")
os.environ.setdefault(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3010,http://127.0.0.1:3000,http://127.0.0.1:3010",
)
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("EMBED_DIRECT_URL", "http://127.0.0.1:1234")
os.environ.setdefault("DEFAULT_EMBED_MODEL", "text-embedding-embeddinggemma-300m")
os.environ.setdefault("EMBED_DIM", "768")
# Pytest uses inline ingest so a separate arq process is not required
os.environ.setdefault("RAG_INGEST_MODE", "inline")
os.environ.setdefault("APP_ENV", "test")

from app.core.config import get_settings

get_settings.cache_clear()

from app.main import app  # noqa: E402


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        # Clear login rate-limit counters so tests don't poison each other
        from app.db.redis import get_redis

        rds = await get_redis()
        for pattern in ("login_rl:*", "rl:*", "idem:*", "ws_ticket:*"):
            for key in await rds.keys(pattern):
                await rds.delete(key)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        for pattern in ("login_rl:*", "rl:*", "idem:*", "ws_ticket:*"):
            for key in await rds.keys(pattern):
                await rds.delete(key)
