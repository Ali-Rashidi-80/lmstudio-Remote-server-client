"""Database hygiene and log/record retention helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.entities import AuditLog, RagJob, RefreshToken

logger = logging.getLogger("maintenance")


async def prune_stale_records(
    session: AsyncSession, retention_days: int | None = None
) -> dict[str, int]:
    """Delete expired/revoked refresh tokens and aged audit/RAG job history."""
    settings = get_settings()
    days = max(retention_days if retention_days is not None else settings.AUDIT_RETENTION_DAYS, 1)
    now = datetime.now(UTC)
    token_cutoff = now - timedelta(days=1)
    history_cutoff = now - timedelta(days=days)

    token_res = await session.execute(
        delete(RefreshToken).where(
            or_(
                RefreshToken.expires_at < token_cutoff,
                (RefreshToken.revoked.is_(True)) & (RefreshToken.created_at < token_cutoff),
            )
        )
    )
    audit_res = await session.execute(delete(AuditLog).where(AuditLog.created_at < history_cutoff))
    job_res = await session.execute(
        delete(RagJob).where(
            RagJob.status.in_(["completed", "failed"]),
            RagJob.finished_at.is_not(None),
            RagJob.finished_at < history_cutoff,
        )
    )
    await session.commit()
    summary = {
        "refresh_tokens": int(token_res.rowcount or 0),
        "audit_logs": int(audit_res.rowcount or 0),
        "rag_jobs": int(job_res.rowcount or 0),
    }
    logger.info("Pruned stale records: %s", summary)
    return summary
