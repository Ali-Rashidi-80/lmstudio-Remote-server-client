"""ARQ worker: RAG document ingest jobs."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import KnowledgeDoc, RagJob
from app.services.rag import index_document

logger = logging.getLogger("rag_worker")


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    # arq expects redis://host:port
    return RedisSettings.from_dsn(settings.REDIS_URL)


async def ingest_document(ctx: dict, doc_id: str, job_id: str) -> dict:
    """Index one knowledge document (called by ARQ worker process)."""
    did = uuid.UUID(doc_id)
    jid = uuid.UUID(job_id)
    try:
        async with SessionLocal() as session:
            d = await session.get(KnowledgeDoc, did)
            j = await session.get(RagJob, jid)
            if not d or not j:
                return {"ok": False, "error": "missing doc/job"}
            j.status = "running"
            await session.commit()
            n = await index_document(session, d)
            j = await session.get(RagJob, jid)
            if j:
                j.status = "completed" if n else "failed"
                j.finished_at = datetime.now(UTC)
                if not n:
                    j.error = "No text extracted"
                await session.commit()
            return {"ok": bool(n), "chunks": n}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("ARQ ingest failed for %s", doc_id)
        async with SessionLocal() as session:
            d = await session.get(KnowledgeDoc, did)
            j = await session.get(RagJob, jid)
            if d:
                d.status = "failed"
            if j:
                j.status = "failed"
                j.error = str(exc)
                j.finished_at = datetime.now(UTC)
            await session.commit()
        return {"ok": False, "error": str(exc)}


class WorkerSettings:
    """arq CLI: `arq app.workers.rag.WorkerSettings`"""

    functions = [ingest_document]
    redis_settings = _redis_settings()
    max_jobs = 2
    job_timeout = 600
    keep_result = 3600
