from __future__ import annotations

import io
import logging
import uuid
import zipfile
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Body, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.core.config import get_settings
from app.models.entities import KnowledgeDoc, RagJob
from app.services.audit import write_audit
from app.services.idempotency import (
    abort_idempotency,
    begin_idempotency,
    complete_idempotency,
    hash_payload,
    validate_idempotency_key,
)
from app.services.ingest_queue import enqueue_ingest
from app.services.rag import retrieve, sanitize_filename
from app.services.rate_limit import check_rate_limit

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
MAX_DOCX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
READ_CHUNK_BYTES = 65536


class KnowledgeDocUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    is_shared: bool | None = None


class KnowledgeSearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


async def _read_upload_bounded(file: UploadFile, max_bytes: int) -> bytes:
    buf = bytearray()
    while True:
        chunk = await file.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                status_code=413, detail=f"File too large (max {max_bytes // (1024 * 1024)}MB)"
            )
    return bytes(buf)


def _validate_file_content(ext: str, data: bytes) -> None:
    if not data or not data.strip():
        raise HTTPException(status_code=400, detail="Empty file is not allowed")
    if ext == ".pdf":
        trimmed = data.lstrip(b"\xef\xbb\xbf \t\r\n")
        if not trimmed.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Invalid PDF file header")
    elif ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                if "word/document.xml" not in names:
                    raise HTTPException(status_code=400, detail="Invalid DOCX structure")
                total_uncompressed = sum(info.file_size for info in zf.infolist())
                if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=400, detail="DOCX expanded size exceeds safety limit"
                    )
        except zipfile.BadZipFile as exc:
            raise HTTPException(
                status_code=400, detail="Corrupted or invalid DOCX archive"
            ) from exc
    elif ext in {".txt", ".md"}:
        if b"\x00" in data:
            raise HTTPException(status_code=400, detail="Binary content rejected for text upload")


@router.get("/docs")
async def list_docs(
    user: CurrentUser,
    db: DbDep,
    q: str | None = None,
    status: str | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    stmt = select(KnowledgeDoc).where(
        (KnowledgeDoc.user_id == user.id) | (KnowledgeDoc.is_shared.is_(True))
    )
    if q and q.strip():
        stmt = stmt.where(KnowledgeDoc.title.ilike(f"%{q.strip()}%"))
    if status and status.strip():
        stmt = stmt.where(KnowledgeDoc.status == status.strip())
    rows = (
        await db.scalars(stmt.order_by(KnowledgeDoc.created_at.desc()).offset(offset).limit(limit))
    ).all()

    doc_ids = [d.id for d in rows]
    latest_errors: dict[uuid.UUID, str | None] = {}
    if doc_ids:
        jobs = await db.scalars(
            select(RagJob).where(RagJob.doc_id.in_(doc_ids)).order_by(RagJob.created_at.desc())
        )
        for job in jobs:
            if job.doc_id not in latest_errors:
                latest_errors[job.doc_id] = job.error

    return [
        {
            "id": str(d.id),
            "title": d.title,
            "filename": d.filename,
            "content_type": d.content_type,
            "status": d.status,
            "size_bytes": d.size_bytes,
            "is_shared": d.is_shared,
            "is_owner": d.user_id == user.id,
            "last_error": latest_errors.get(d.id),
            "created_at": d.created_at.isoformat(),
        }
        for d in rows
    ]


@router.post("/docs")
async def upload_doc(
    user: CurrentUser,
    db: DbDep,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    settings = get_settings()
    if not await check_rate_limit(
        "upload", str(user.id), settings.UPLOAD_RATE_LIMIT, settings.UPLOAD_RATE_WINDOW_SEC
    ):
        raise HTTPException(status_code=429, detail="Too many uploads; please wait")

    idem_key = validate_idempotency_key(idempotency_key)
    name = sanitize_filename(file.filename or "upload.txt")
    ext = Path(name).suffix.lower()
    if ext in BLOCKED_EXT:
        raise HTTPException(status_code=400, detail="Executable / script uploads are blocked")
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    data = await _read_upload_bounded(file, settings.MAX_DOC_BYTES)
    _validate_file_content(ext, data)

    p_hash = hash_payload(name.encode("utf-8") + b":" + data)
    replayed, cached = await begin_idempotency("doc_upload", str(user.id), idem_key, p_hash)
    if replayed and cached is not None:
        return cached

    try:
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
        res = {
            "id": str(doc.id),
            "status": "queued",
            "job_id": str(job.id),
            "ingest_mode": mode,
        }
        await complete_idempotency("doc_upload", str(user.id), idem_key, p_hash, res)
        return res
    except Exception:
        await abort_idempotency("doc_upload", str(user.id), idem_key)
        raise


@router.patch("/docs/{doc_id}")
async def patch_doc(
    doc_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    is_shared: bool | None = None,
    body: KnowledgeDocUpdate | None = Body(default=None),
) -> dict:
    """Update shared visibility or title for a document owned by the caller."""
    doc = await db.get(KnowledgeDoc, doc_id)
    if not doc or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")

    next_shared = is_shared if is_shared is not None else (body.is_shared if body else None)
    next_title = body.title.strip() if body and body.title is not None else None
    if next_shared is None and next_title is None:
        raise HTTPException(status_code=400, detail="No update fields provided")
    if next_title is not None:
        if not next_title:
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        doc.title = next_title
    if next_shared is not None:
        doc.is_shared = bool(next_shared)
    await db.commit()
    await write_audit(
        db,
        "doc_update",
        actor_id=user.id,
        detail={"doc_id": str(doc_id), "is_shared": doc.is_shared, "title": doc.title},
    )
    return {"id": str(doc.id), "title": doc.title, "is_shared": doc.is_shared}


@router.delete("/docs/{doc_id}")
async def delete_doc(doc_id: uuid.UUID, user: CurrentUser, db: DbDep) -> dict:
    doc = await db.get(KnowledgeDoc, doc_id)
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
    await write_audit(db, "doc_delete", actor_id=user.id, detail={"doc_id": str(doc_id)})
    return {"ok": True}


@router.get("/jobs/{job_id}")
async def job_status(job_id: uuid.UUID, user: CurrentUser, db: DbDep) -> dict:
    job = await db.get(RagJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "id": str(job.id),
        "doc_id": str(job.doc_id),
        "status": job.status,
        "error": job.error,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.post("/search")
async def search(
    user: CurrentUser,
    db: DbDep,
    q: str | None = None,
    top_k: int = Query(5, ge=1, le=20),
    body: KnowledgeSearchRequest | None = Body(default=None),
) -> dict:
    query_text = (q if q is not None else (body.q if body else "")).strip()
    eff_top_k = body.top_k if (body is not None and q is None) else top_k
    if not query_text:
        raise HTTPException(status_code=400, detail="Empty query")
    try:
        sources = await retrieve(db, user.id, query_text, top_k=eff_top_k)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"sources": sources}
