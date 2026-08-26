from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import KnowledgeDoc, RagJob
from app.services.audit import write_audit
from app.services.ingest_queue import enqueue_ingest
from app.services.rag import index_document, retrieve, sanitize_filename

logger = logging.getLogger("knowledge")

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXT = {".pdf", ".txt", ".md", ".docx"}
BLOCKED_EXT = {
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
    ".msi",
    ".dll",
    ".scr",
    ".com",
    ".js",
    ".vbs",
    ".sh",
}


@router.get("/docs")
async def list_docs(user: CurrentUser, db: DbDep) -> list[dict]:
    rows = await db.scalars(
        select(KnowledgeDoc)
        .where((KnowledgeDoc.user_id == user.id) | (KnowledgeDoc.is_shared.is_(True)))
        .order_by(KnowledgeDoc.created_at.desc())
    )
    return [
        {
            "id": str(d.id),
            "title": d.title,
            "filename": d.filename,
            "status": d.status,
            "size_bytes": d.size_bytes,
            "is_shared": d.is_shared,
            "created_at": d.created_at.isoformat(),
        }
        for d in rows
    ]


@router.post("/docs")
async def upload_doc(
    user: CurrentUser,
    db: DbDep,
    file: UploadFile = File(...),
) -> dict:
    settings = get_settings()
    name = sanitize_filename(file.filename or "upload.txt")
    ext = Path(name).suffix.lower()
    if ext in BLOCKED_EXT:
        raise HTTPException(status_code=400, detail="Executable / script uploads are blocked")
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    data = await file.read()
    if len(data) > settings.MAX_DOC_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    upload_root = Path(settings.UPLOAD_DIR) / str(user.id)
    upload_root.mkdir(parents=True, exist_ok=True)
    doc_id = uuid.uuid4()
    path = upload_root / f"{doc_id}_{name}"
    async with aiofiles.open(path, "wb") as f:
        await f.write(data)

    doc = KnowledgeDoc(
        id=doc_id,
        user_id=user.id,
        title=name,
        filename=name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        storage_path=str(path),
        status="queued",
    )
    job = RagJob(doc_id=doc.id, user_id=user.id, status="queued")
    db.add(doc)
    db.add(job)
    await db.commit()
    await write_audit(db, "doc_upload", actor_id=user.id, detail={"doc_id": str(doc.id)})

    mode = await enqueue_ingest(doc.id, job.id)
    return {
        "id": str(doc.id),
        "status": "queued",
        "job_id": str(job.id),
        "ingest_mode": mode,
    }


async def _ingest_doc(doc_id: uuid.UUID, job_id: uuid.UUID) -> None:
    try:
        async with SessionLocal() as session:
            d = await session.get(KnowledgeDoc, doc_id)
            j = await session.get(RagJob, job_id)
            if not d or not j:
                return
            j.status = "running"
            await session.commit()
            n = await index_document(session, d)
            j = await session.get(RagJob, job_id)
            if j:
                j.status = "completed" if n else "failed"
                j.finished_at = datetime.now(UTC)
                if not n:
                    j.error = "No text extracted"
                await session.commit()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.exception("RAG ingest failed for %s", doc_id)
        async with SessionLocal() as session:
            d = await session.get(KnowledgeDoc, doc_id)
            j = await session.get(RagJob, job_id)
            if d:
                d.status = "failed"
            if j:
                j.status = "failed"
                j.error = str(exc)
                j.finished_at = datetime.now(UTC)
            await session.commit()


@router.patch("/docs/{doc_id}")
async def patch_doc(doc_id: str, user: CurrentUser, db: DbDep, is_shared: bool) -> dict:
    """Toggle shared visibility for a document owned by the caller."""
    doc = await db.get(KnowledgeDoc, uuid.UUID(doc_id))
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    doc.is_shared = bool(is_shared)
    await db.commit()
    await write_audit(
        db,
        "doc_share",
        actor_id=user.id,
        detail={"doc_id": doc_id, "is_shared": doc.is_shared},
    )
    return {"id": str(doc.id), "is_shared": doc.is_shared}


@router.delete("/docs/{doc_id}")
async def delete_doc(doc_id: str, user: CurrentUser, db: DbDep) -> dict:
    doc = await db.get(KnowledgeDoc, uuid.UUID(doc_id))
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    path = Path(doc.storage_path)
    # Explicitly remove jobs first — existing DBs may lack ON DELETE CASCADE on rag_jobs
    jobs = await db.scalars(select(RagJob).where(RagJob.doc_id == doc.id))
    for job in jobs:
        await db.delete(job)
    await db.delete(doc)
    await db.commit()
    if path.exists():
        path.unlink(missing_ok=True)
    await write_audit(db, "doc_delete", actor_id=user.id, detail={"doc_id": doc_id})
    return {"ok": True}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, user: CurrentUser, db: DbDep) -> dict:
    job = await db.get(RagJob, uuid.UUID(job_id))
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "id": str(job.id),
        "doc_id": str(job.doc_id),
        "status": job.status,
        "error": job.error,
    }


@router.post("/search")
async def search(user: CurrentUser, db: DbDep, q: str, top_k: int = 5) -> dict:
    if not q.strip():
        raise HTTPException(status_code=400, detail="Empty query")
    try:
        sources = await retrieve(db, user.id, q, top_k=top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"sources": sources}
