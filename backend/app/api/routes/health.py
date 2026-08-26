from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.redis import redis_ping
from app.db.session import SessionLocal
from app.ws.manager import manager

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "version": settings.APP_VERSION}


@router.get("/api/ready")
async def ready() -> dict:
    db_ok = False
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False
    redis_ok = await redis_ping()
    worker = manager.status()
    ready_ok = db_ok and redis_ok
    return {
        "ready": ready_ok,
        "database": db_ok,
        "redis": redis_ok,
        "worker": worker,
    }
