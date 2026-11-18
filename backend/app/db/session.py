"""Async database engine and session."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()
_is_test = bool(os.getenv("PYTEST_CURRENT_TEST")) or settings.APP_ENV.lower() == "test"
engine = (
    create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    if _is_test
    else create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
