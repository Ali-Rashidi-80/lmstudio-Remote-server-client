from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import AuditLog


async def write_audit(
    db: AsyncSession,
    action: str,
    actor_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, detail=detail or {}))
    await db.commit()
