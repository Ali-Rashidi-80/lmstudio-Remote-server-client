"""Bootstrap admin and settings on startup."""

from __future__ import annotations

import logging

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.entities import AppSetting, User, UserRole

logger = logging.getLogger("bootstrap")


async def ensure_pgvector(session: AsyncSession) -> None:
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    await session.commit()


async def ensure_hnsw_index(session: AsyncSession) -> None:
    await session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw
            ON rag_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 200)
            """))
    await session.commit()


async def bootstrap_admin(session: AsyncSession) -> None:
    settings = get_settings()
    count = await session.scalar(select(func.count()).select_from(User))
    if count and count > 0:
        return
    if len(settings.ADMIN_BOOTSTRAP_PASSWORD) < 10:
        logger.warning("ADMIN_BOOTSTRAP_PASSWORD too short; skipping bootstrap")
        return
    admin = User(
        username=settings.ADMIN_BOOTSTRAP_USERNAME,
        password_hash=hash_password(settings.ADMIN_BOOTSTRAP_PASSWORD),
        role=UserRole.admin,
        is_active=True,
    )
    session.add(admin)
    await session.commit()
    logger.info("Bootstrap admin created: %s", settings.ADMIN_BOOTSTRAP_USERNAME)


async def ensure_default_settings(session: AsyncSession) -> None:
    settings = get_settings()
    defaults = {
        "default_chat_model": {"value": settings.DEFAULT_CHAT_MODEL},
        "default_embed_model": {"value": settings.DEFAULT_EMBED_MODEL},
        "embed_dim": {"value": settings.EMBED_DIM},
    }
    for key, value in defaults.items():
        existing = await session.get(AppSetting, key)
        if not existing:
            session.add(AppSetting(key=key, value=value))
    await session.commit()
