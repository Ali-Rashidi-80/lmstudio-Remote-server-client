"""RAG chunking, embedding via Worker / LM Studio, and retrieval."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.entities import AppSetting, KnowledgeDoc, RagChunk
from app.services.vectors import l2_normalize

CHUNK_CHARS = 1800
OVERLAP = 200
# Approximate context budget for injected RAG snippets (chars)
RAG_CONTEXT_CHARS = 6000
HNSW_EF_SEARCH = 40


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


def chunk_text(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunk = text[i : i + CHUNK_CHARS]
        chunks.append(chunk.strip())
        i += max(CHUNK_CHARS - OVERLAP, 1)
    return [c for c in chunks if c]


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


async def embed_texts(
    texts: list[str],
    lmstudio_base: str | None = None,
    model: str | None = None,
) -> list[list[float]]:
    """Embed via PC Worker (preferred) or direct LM Studio if EMBED_DIRECT_URL is set."""
    settings = get_settings()
    embed_model = model or settings.DEFAULT_EMBED_MODEL
    direct = lmstudio_base or (settings.EMBED_DIRECT_URL or "").strip()
    if not direct:
        from app.ws.manager import manager

        result = await manager.request_embeddings(texts, embed_model)
        data = result.get("data") or []
        vectors = [
            l2_normalize(item["embedding"])
            for item in sorted(data, key=lambda x: x.get("index", 0))
        ]
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{str(direct).rstrip('/')}/v1/embeddings",
                json={"model": embed_model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            vectors = [
                l2_normalize(item["embedding"]) for item in sorted(data, key=lambda x: x["index"])
            ]
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
    embed_model = await resolve_embed_model(db)
    qvec = (await embed_texts([query], lmstudio_base=lmstudio_base, model=embed_model))[0]
    fetch_k = top_k * 5
    try:
        await db.execute(
            text("SELECT set_config('hnsw.ef_search', :v, true)"),
            {"v": str(int(HNSW_EF_SEARCH))},
        )
    except Exception:
        # Older pgvector builds may not expose ef_search; retrieval still works.
        pass
    sql = text("""
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
        """)
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
            .where(
                RagChunk.user_id == user_id,
                RagChunk.embed_model_id != embed_model,
            )
        )
        if stale:
            raise RuntimeError(
                "Embedding model mismatch: chunks need admin reindex "
                f"(current model={embed_model})"
            )
    out = []
    for row in rows[:top_k]:
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
    parts: list[str] = []
    used = 0
    for s in sources:
        piece = f"[{s['doc_title']}] {s['snippet']}"
        if used + len(piece) > RAG_CONTEXT_CHARS:
            break
        parts.append(piece)
        used += len(piece) + 2
    return "\n\n".join(parts)
