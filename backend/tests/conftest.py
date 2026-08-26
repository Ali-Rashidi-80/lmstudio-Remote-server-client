"""Shared fixtures — real Postgres/Redis required (no fakes that hide failures)."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Force local compose defaults unless caller overrides
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://aiws:change-me-db-password@localhost:55432/aiworkspace",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:26379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-key-please-change")
os.environ.setdefault("WORKER_TOKEN", "test-worker-token")
os.environ.setdefault("ADMIN_BOOTSTRAP_USERNAME", "admin")
os.environ.setdefault("ADMIN_BOOTSTRAP_PASSWORD", "adminpass12")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("EMBED_DIRECT_URL", "http://127.0.0.1:1234")
os.environ.setdefault("DEFAULT_EMBED_MODEL", "text-embedding-embeddinggemma-300m")
os.environ.setdefault("EMBED_DIM", "768")
# Pytest uses inline ingest so a separate arq process is not required
os.environ.setdefault("RAG_INGEST_MODE", "inline")

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
        for key in await rds.keys("login_rl:*"):
            await rds.delete(key)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        for key in await rds.keys("login_rl:*"):
            await rds.delete(key)
