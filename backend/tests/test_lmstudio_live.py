"""Comprehensive live LM Studio I/O — skipped only if :1234 unreachable. No mocks."""

from __future__ import annotations

import json
import math

import httpx
import pytest

LMS = "http://127.0.0.1:1234"
CHAT_MODEL = "gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q6_k"
EMBED_MODEL = "text-embedding-embeddinggemma-300m"
# Fast model for protocol/I/O smoke when the locked 12B is cold/loading
FAST_CHAT_CANDIDATES = (
    "nvidia/nemotron-3-nano-4b",
    "google/gemma-4-e4b",
)


def lmstudio_up() -> bool:
    try:
        r = httpx.get(f"{LMS}/v1/models", timeout=3.0, trust_env=False)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not lmstudio_up(), reason="LM Studio not running on :1234")


def _model_ids() -> set[str]:
    r = httpx.get(f"{LMS}/v1/models", timeout=10.0, trust_env=False)
    assert r.status_code == 200, r.text
    return {m.get("id") for m in r.json().get("data") or []}


def _pick_fast_chat(ids: set[str]) -> str | None:
    for mid in FAST_CHAT_CANDIDATES:
        if mid in ids:
            return mid
    # any non-embedding model
    for mid in sorted(ids):
        if "embed" not in mid.lower() and "mmproj" not in mid.lower():
            return mid
    return None


def test_models_list_contains_locked_ids():
    ids = _model_ids()
    assert EMBED_MODEL in ids, f"embed model missing; loaded={sorted(ids)}"
    assert CHAT_MODEL in ids, f"locked chat model missing; loaded={sorted(ids)}"


def test_embeddings_dim_and_normalize_and_content():
    r = httpx.post(
        f"{LMS}/v1/embeddings",
        json={"model": EMBED_MODEL, "input": ["سلام دنیا", "ALPACA-UNIQUE-991"]},
        timeout=120.0,
        trust_env=False,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data) == 2
    for item in data:
        vec = item["embedding"]
        assert len(vec) == 768
        norm = math.sqrt(sum(x * x for x in vec))
        assert norm > 0.1
        assert all(isinstance(x, int | float) for x in vec[:5])


def test_embeddings_distinct_for_different_texts():
    r = httpx.post(
        f"{LMS}/v1/embeddings",
        json={
            "model": EMBED_MODEL,
            "input": ["quantum physics lecture notes", "گربه روی فرش خوابیده"],
        },
        timeout=120.0,
        trust_env=False,
    )
    assert r.status_code == 200, r.text
    a = r.json()["data"][0]["embedding"]
    b = r.json()["data"][1]["embedding"]
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    cos = dot / (na * nb)
    assert cos < 0.95, f"unrelated texts too similar: cos={cos}"


def test_chat_completion_fast_model_io():
    """Protocol/content smoke on a small loaded model (must pass if any chat model exists)."""
    ids = _model_ids()
    model = _pick_fast_chat(ids)
    if not model:
        pytest.skip("No chat model available in LM Studio")
    try:
        r = httpx.post(
            f"{LMS}/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Reply with exactly: PING-OK-42"},
                    {"role": "user", "content": "ping"},
                ],
                "temperature": 0.0,
                "max_tokens": 32,
                "stream": False,
            },
            timeout=90.0,
            trust_env=False,
        )
    except httpx.ReadTimeout:
        pytest.skip(
            f"LM Studio chat timed out for {model} — models listed but inference "
            "not responding (VRAM/load). Embeddings still verified separately."
        )
    assert r.status_code == 200, r.text
    msg = r.json()["choices"][0]["message"]
    content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
    assert content, f"empty assistant payload: {msg}"
    assert len(content) >= 3


def test_chat_streaming_fast_model_yields_chunks():
    ids = _model_ids()
    model = _pick_fast_chat(ids)
    if not model:
        pytest.skip("No chat model available in LM Studio")
    try:
        with httpx.stream(
            "POST",
            f"{LMS}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Say hi"}],
                "temperature": 0.0,
                "max_tokens": 24,
                "stream": True,
            },
            timeout=90.0,
            trust_env=False,
        ) as resp:
            assert resp.status_code == 200
            pieces: list[str] = []
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                obj = json.loads(payload)
                delta = obj.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    pieces.append(delta["content"])
    except httpx.ReadTimeout:
        pytest.skip(f"LM Studio chat stream timed out for {model} — inference not responding")
    assert pieces, "expected at least one streamed content delta"
    assert "".join(pieces).strip()


def test_locked_chat_model_responds_or_honest_skip():
    """Locked product chat model — skip only if listed but GPU cold/timeout (no fake pass)."""
    ids = _model_ids()
    if CHAT_MODEL not in ids:
        pytest.fail(f"locked chat model not in /v1/models: {CHAT_MODEL}")
    try:
        r = httpx.post(
            f"{LMS}/v1/chat/completions",
            json={
                "model": CHAT_MODEL,
                "messages": [
                    {"role": "user", "content": "Reply with one word: ok"},
                ],
                "temperature": 0.0,
                "max_tokens": 16,
                "stream": False,
            },
            timeout=300.0,
            trust_env=False,
        )
    except httpx.ReadTimeout:
        pytest.skip(
            f"locked model {CHAT_MODEL} listed but timed out after 300s "
            "(load into GPU / free VRAM and re-run — not a fake pass)"
        )
    assert r.status_code == 200, r.text
    msg = r.json()["choices"][0]["message"]
    content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
    assert content, f"empty assistant payload from locked model: {msg}"


@pytest.mark.asyncio
async def test_product_embed_texts_matches_dim():
    """Through product RAG layer (L2-normalize + dim check)."""
    from app.services.rag import embed_texts

    vecs = await embed_texts(["product-layer-embed-check"], model=EMBED_MODEL)
    assert len(vecs) == 1
    assert len(vecs[0]) == 768
    norm = math.sqrt(sum(x * x for x in vecs[0]))
    assert 0.99 <= norm <= 1.01
