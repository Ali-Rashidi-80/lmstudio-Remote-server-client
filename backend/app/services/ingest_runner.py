"""Shared background ingest job runner (used by ARQ and inline queue)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from app.db.session import SessionLocal
from app.models.entities import KnowledgeDoc, RagJob
from app.services.rag import index_document

logger = logging.getLogger("ingest")


async def run_ingest_job(doc_id: uuid.UUID, job_id: uuid.UUID) -> int:
    """Index one document and persist terminal job status."""
    try:
        async with SessionLocal() as session:
            doc = await session.get(KnowledgeDoc, doc_id)
            job = await session.get(RagJob, job_id)
            if not doc or not job:
                return 0
            job.status = "running"
            await session.commit()
            n = await index_document(session, doc)
            job = await session.get(RagJob, job_id)
            if job:
                job.status = "completed" if n else "failed"
                job.finished_at = datetime.now(UTC)
                if not n:
                    job.error = "No text extracted"
                await session.commit()
            return n
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("RAG ingest failed for %s", doc_id)
        async with SessionLocal() as session:
            doc = await session.get(KnowledgeDoc, doc_id)
            job = await session.get(RagJob, job_id)
            if doc:
                doc.status = "failed"
            if job:
                job.status = "failed"
                job.error = str(exc)[:500]
                job.finished_at = datetime.now(UTC)
            await session.commit()
        return 0
