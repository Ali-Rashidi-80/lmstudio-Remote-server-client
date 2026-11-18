"""RAG chunking, embedding via Worker / Bridge RPC / LM Studio, and retrieval."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.entities import AppSetting, KnowledgeDoc, RagChunk
from app.services.vectors import l2_normalize

logger = logging.getLogger("rag")

CHUNK_CHARS = 1800
OVERLAP = 200
RAG_CONTEXT_CHARS = 6000
HNSW_EF_SEARCH = 40
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def sanitize_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^\w.\- ()\u0600-\u06FF]+", "_", name)
    return name[:200] or "upload.bin"


def extract_text(path: Path, content_type: str) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"} or content_type.startswith("text/"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".docx":
        import docx

        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)
    raise ValueError(f"Unsupported file type: {suffix}")


def chunk_text(text_content: str) -> list[str]:
    settings = get_settings()
    chunk_chars = max(int(settings.RAG_CHUNK_CHARS or CHUNK_CHARS), 200)
    overlap = max(0, min(int(settings.RAG_CHUNK_OVERLAP or OVERLAP), chunk_chars // 2))
    cleaned = re.sub(r"\n{3,}", "\n\n", text_content).strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    i = 0
    step = max(chunk_chars - overlap, 1)
    while i < len(cleaned):
        chunk = cleaned[i : i + chunk_chars].strip()
        if chunk:
            chunks.append(chunk)
        i += step
    return chunks


async def resolve_embed_model(db: AsyncSession) -> str:
    """Prefer admin AppSetting; fall back to env DEFAULT_EMBED_MODEL."""
    row = await db.get(AppSetting, "default_embed_model")
    if row and isinstance(row.value, dict):
        value = row.value.get("value")
        if value:
            return str(value)
    return get_settings().DEFAULT_EMBED_MODEL


async def resolve_chat_model(db: AsyncSession) -> str:
    row = await db.get(AppSetting, "default_chat_model")
    if row and isinstance(row.value, dict):
        value = row.value.get("value")
        if value:
            return str(value)
    return get_settings().DEFAULT_CHAT_MODEL


async def _post_with_retries(
    url: str,
    json_body: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
    attempts: int = 3,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        for attempt in range(attempts):
            try:
                resp = await client.post(url, json=json_body, headers=headers)
                if resp.status_code in RETRYABLE_STATUS and attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("Embedding HTTP call failed unexpectedly")


async def embed_texts(
    texts: list[str],
    lmstudio_base: str | None = None,
    model: str | None = None,
) -> list[list[float]]:
    """
    Embed texts via:
    1) Direct LM Studio URL (when EMBED_DIRECT_URL or lmstudio_base is configured), or
    2) In-process PC Worker WebSocket if connected, or
    3) Bridge internal RPC endpoint (/api/internal/embeddings) for separate ARQ worker processes.
    """
    settings = get_settings()
    embed_model = model or settings.DEFAULT_EMBED_MODEL
    direct = (lmstudio_base or settings.EMBED_DIRECT_URL or "").strip()

    if direct:
        payload = await _post_with_retries(
            f"{direct.rstrip('/')}/v1/embeddings",
            {"model": embed_model, "input": texts},
        )
        data = payload.get("data") or []
    else:
        from app.ws.manager import manager

        if manager.status()["worker_online"]:
            result = await manager.request_embeddings(texts, embed_model)
            data = result.get("data") or []
        else:
            bridge_url = (settings.BRIDGE_INTERNAL_URL or "").strip().rstrip("/")
            if not bridge_url:
                raise RuntimeError("PC Worker offline and BRIDGE_INTERNAL_URL not configured")
            try:
                payload = await _post_with_retries(
                    f"{bridge_url}/api/internal/embeddings",
                    {"input": texts, "model": embed_model},
                    headers={"X-Worker-Token": settings.WORKER_TOKEN},
                )
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:200]
                raise RuntimeError(
                    f"Bridge embeddings RPC failed ({exc.response.status_code}): {detail}"
                ) from exc
            data = payload.get("data") or []

    vectors = [
        l2_normalize(item["embedding"]) for item in sorted(data, key=lambda x: x.get("index", 0))
    ]
    if len(vectors) != len(texts):
        raise ValueError(f"Expected {len(texts)} embeddings, got {len(vectors)}")
    for v in vectors:
        if len(v) != settings.EMBED_DIM:
            raise ValueError(f"Expected embed dim {settings.EMBED_DIM}, got {len(v)}")
    return vectors


async def index_document(
    db: AsyncSession, doc: KnowledgeDoc, lmstudio_base: str | None = None
) -> int:
    settings = get_settings()
    embed_model = await resolve_embed_model(db)
    path = Path(doc.storage_path)
    raw = extract_text(path, doc.content_type)
    parts = chunk_text(raw)
    if not parts:
        doc.status = "failed"
        await db.commit()
        return 0

    existing = await db.scalars(select(RagChunk).where(RagChunk.doc_id == doc.id))
    for row in existing:
        await db.delete(row)
    await db.flush()

    batch_size = 8
    total = 0
    for start in range(0, len(parts), batch_size):
        batch = parts[start : start + batch_size]
        vectors = await embed_texts(batch, lmstudio_base=lmstudio_base, model=embed_model)
        for offset, (content, vec) in enumerate(zip(batch, vectors, strict=True)):
            db.add(
                RagChunk(
                    user_id=doc.user_id,
                    doc_id=doc.id,
                    chunk_index=start + offset,
                    content=content,
                    embed_model_id=embed_model,
                    embed_dim=settings.EMBED_DIM,
                    embedding=vec,
                )
            )
            total += 1
    doc.status = "ready"
    await db.commit()
    return total


async def retrieve(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    top_k: int = 5,
    doc_ids: list[uuid.UUID] | None = None,
    lmstudio_base: str | None = None,
) -> list[dict]:
    settings = get_settings()
    bounded_k = max(1, min(int(top_k), 20))
    embed_model = await resolve_embed_model(db)
    qvec = (await embed_texts([query], lmstudio_base=lmstudio_base, model=embed_model))[0]
    fetch_k = bounded_k * 5
    ef_search = max(int(settings.RAG_HNSW_EF_SEARCH or HNSW_EF_SEARCH), 1)
    try:
        async with db.begin_nested():
            await db.execute(
                text("SELECT set_config('hnsw.ef_search', :v, true)"),
                {"v": str(ef_search)},
            )
    except Exception as exc:
        logger.debug("Skipping hnsw.ef_search setting: %s", exc)

    sql = text(
        """
        SELECT c.id, c.doc_id, c.content, c.embed_model_id, c.embed_dim,
               d.title AS doc_title,
               1 - (c.embedding <=> CAST(:qvec AS vector)) AS score
        FROM rag_chunks c
        JOIN knowledge_docs d ON d.id = c.doc_id
        WHERE (c.user_id = CAST(:user_id AS uuid) OR d.is_shared = true)
          AND c.embed_model_id = :embed_model
          AND c.embed_dim = :embed_dim
          AND (
            CAST(:filter_docs AS boolean) = false
            OR c.doc_id = ANY(CAST(:doc_ids AS uuid[]))
          )
        ORDER BY c.embedding <=> CAST(:qvec AS vector)
        LIMIT :limit
        """
    )
    qvec_literal = "[" + ",".join(str(float(x)) for x in qvec) + "]"
    result = await db.execute(
        sql,
        {
            "qvec": qvec_literal,
            "user_id": str(user_id),
            "embed_model": embed_model,
            "embed_dim": settings.EMBED_DIM,
            "filter_docs": bool(doc_ids),
            "doc_ids": [str(d) for d in (doc_ids or [])] or None,
            "limit": fetch_k,
        },
    )
    rows = result.mappings().all()
    if not rows:
        stale = await db.scalar(
            select(func.count())
            .select_from(RagChunk)
            .join(KnowledgeDoc, KnowledgeDoc.id == RagChunk.doc_id)
            .where(
                or_(RagChunk.user_id == user_id, KnowledgeDoc.is_shared.is_(True)),
                RagChunk.embed_model_id != embed_model,
            )
        )
        if stale:
            raise RuntimeError(
                "Embedding model mismatch: chunks need admin reindex "
                f"(current model={embed_model})"
            )
    out = []
    for row in rows[:bounded_k]:
        out.append(
            {
                "chunk_id": str(row["id"]),
                "doc_id": str(row["doc_id"]),
                "doc_title": row["doc_title"],
                "snippet": row["content"][:500],
                "score": float(row["score"] or 0),
            }
        )
    return out


def build_rag_context(sources: list[dict]) -> str:
    settings = get_settings()
    budget = max(int(settings.RAG_CONTEXT_CHARS or RAG_CONTEXT_CHARS), 500)
    parts: list[str] = []
    used = 0
    for s in sources:
        piece = f"[{s['doc_title']}] {s['snippet']}"
        if used + len(piece) > budget:
            break
        parts.append(piece)
        used += len(piece) + 2
    return "\n\n".join(parts)
