from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.redis import redis_ping
from app.db.session import SessionLocal
from app.ws.manager import manager

logger = logging.getLogger("health")

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
    except Exception as exc:
        logger.warning("Readiness DB check failed: %s", exc)
        db_ok = False
    redis_ok = await redis_ping()
    worker = await manager.merged_status()
    ready_ok = db_ok and redis_ok
    return {
        "ready": ready_ok,
        "database": db_ok,
        "redis": redis_ok,
        "worker": {
            "worker_online": bool(worker.get("worker_online")),
            "hw": worker.get("hw", "CPU"),
            "connected_users": worker.get("connected_users", 0),
        },
    }
