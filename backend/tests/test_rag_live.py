"""Live RAG against LM Studio embeddings — skipped only if LM Studio unreachable."""

from __future__ import annotations

import asyncio
import io

import httpx
import pytest
from sqlalchemy import text

from app.db.session import SessionLocal


def lmstudio_up() -> bool:
    try:
        r = httpx.get("http://127.0.0.1:1234/v1/models", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not lmstudio_up(), reason="LM Studio not running on :1234")


@pytest.mark.asyncio
async def test_embed_dim_is_768():
    from app.services.rag import embed_texts

    vecs = await embed_texts(["سلام دنیا"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 768
    # L2-normalized: norm ~= 1
    norm = sum(x * x for x in vecs[0]) ** 0.5
    assert 0.99 <= norm <= 1.01


@pytest.mark.asyncio
async def test_upload_index_search_and_isolation(client):
    # admin uploads a private doc
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    assert login.status_code == 200, login.text

    content = (
        "AI Workspace phase1 unique-token-ZEBRA-9944 document about Persian RAG retrieval.\n" * 20
    )
    files = {"file": ("zebra.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}
    up = await client.post("/api/knowledge/docs", files=files)
    assert up.status_code == 200, up.text
    body = up.json()
    doc_id = body["id"]
    assert body["status"] in {"ready", "queued", "failed"}
    # Background ingest — poll until ready (real LM Studio embed, no fake)
    mine = None
    for _ in range(60):
        docs = await client.get("/api/knowledge/docs")
        assert docs.status_code == 200
        mine = [d for d in docs.json() if d["id"] == doc_id]
        if mine and mine[0]["status"] in {"ready", "failed"}:
            break
        await asyncio.sleep(0.5)
    assert mine, "uploaded doc missing from list"
    assert mine[0]["status"] == "ready", mine[0]

    search = await client.post("/api/knowledge/search", params={"q": "ZEBRA-9944"})
    assert search.status_code == 200, search.text
    sources = search.json()["sources"]
    assert sources, "expected non-empty RAG sources"
    assert any(
        "ZEBRA" in (s.get("snippet") or "") or "zebra" in (s.get("doc_title") or "").lower()
        for s in sources
    )

    # HNSW index exists
    async with SessionLocal() as session:
        row = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename='rag_chunks' AND indexdef ILIKE '%hnsw%'"
            )
        )
        names = [r[0] for r in row.fetchall()]
        assert names, "HNSW index missing on rag_chunks"

    # second user cannot see admin doc
    await client.post(
        "/api/users",
        json={"username": "bob_rag", "password": "bobpass1234", "role": "user"},
    )
    await client.post("/api/auth/logout")
    login_b = await client.post(
        "/api/auth/login",
        json={"username": "bob_rag", "password": "bobpass1234"},
    )
    assert login_b.status_code == 200, login_b.text
    bob_docs = await client.get("/api/knowledge/docs")
    assert bob_docs.status_code == 200
    assert all(d["id"] != doc_id for d in bob_docs.json())

    bob_search = await client.post("/api/knowledge/search", params={"q": "ZEBRA-9944"})
    assert bob_search.status_code == 200
    assert bob_search.json()["sources"] == []

    # cleanup as admin
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    deleted = await client.delete(f"/api/knowledge/docs/{doc_id}")
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_login_rate_limit_uses_redis(client):
    from app.db.redis import get_redis

    rds = await get_redis()
    # Clear any prior counters for common ASGI client hosts
    for key in await rds.keys("login_rl:*"):
        await rds.delete(key)
    limited = False
    for _ in range(12):
        r = await client.post(
            "/api/auth/login",
            json={"username": "no_such_user_rl", "password": "wrong-password-xx"},
        )
        if r.status_code == 429:
            limited = True
            break
        assert r.status_code == 401, r.text
    assert limited, "expected Redis rate-limit to trigger after repeated failures"
    for key in await rds.keys("login_rl:*"):
        await rds.delete(key)
