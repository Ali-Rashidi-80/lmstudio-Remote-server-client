"""Enqueue RAG ingest jobs via ARQ, with optional inline fallback for tests."""

from __future__ import annotations

import asyncio
import logging
import uuid

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

logger = logging.getLogger("ingest_queue")


async def enqueue_ingest(doc_id: uuid.UUID, job_id: uuid.UUID) -> str:
    """
    Enqueue ARQ job. Returns mode used: "arq" or "inline".

    RAG_INGEST_MODE=inline forces local asyncio task (pytest / no worker).
    Default is arq; on enqueue failure falls back to inline so uploads never hang forever.
    """
    settings = get_settings()
    mode = (getattr(settings, "RAG_INGEST_MODE", None) or "arq").strip().lower()
    if mode == "inline":
        from app.api.routes.knowledge import _ingest_doc

        asyncio.create_task(_ingest_doc(doc_id, job_id))
        return "inline"

    try:
        pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        try:
            await pool.enqueue_job("ingest_document", str(doc_id), str(job_id))
        finally:
            close = getattr(pool, "aclose", None) or pool.close
            await close()
        return "arq"
    except Exception:
        logger.exception("ARQ enqueue failed; falling back to inline ingest")
        from app.api.routes.knowledge import _ingest_doc

        asyncio.create_task(_ingest_doc(doc_id, job_id))
        return "inline"
