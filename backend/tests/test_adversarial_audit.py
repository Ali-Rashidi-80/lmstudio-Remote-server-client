"""Adversarial security, concurrency, cross-process RPC, CRUD, and worker tests."""

from __future__ import annotations

import asyncio
import importlib
import io
import os

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.main import app
from app.ws.manager import manager


async def _login_admin(ac: AsyncClient) -> dict:
    r = await ac.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_concurrent_accept_invite_race(client):
    import uuid

    await _login_admin(client)
    inv = await client.post("/api/users/invites", json={"role": "user"})
    assert inv.status_code == 200, inv.text
    token = inv.json()["token"]
    await client.post("/api/auth/logout")

    tag = uuid.uuid4().hex[:8]
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as c1,
        AsyncClient(transport=transport, base_url="http://test") as c2,
    ):
        r1, r2 = await asyncio.gather(
            c1.post(
                "/api/auth/accept-invite",
                json={"token": token, "username": f"race_u1_{tag}", "password": "racepass1234"},
            ),
            c2.post(
                "/api/auth/accept-invite",
                json={"token": token, "username": f"race_u2_{tag}", "password": "racepass1234"},
            ),
        )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [
        200,
        400,
    ], f"Expected single winner on invite race, got {codes}: {r1.text} | {r2.text}"


@pytest.mark.asyncio
async def test_concurrent_refresh_rotation_race(client):
    login = await _login_admin(client)
    assert login["user"]["username"] == "admin"
    refresh_cookie = client.cookies.get("refresh_token")
    assert refresh_cookie

    transport = ASGITransport(app=app)
    async with (
        AsyncClient(
            transport=transport, base_url="http://test", cookies={"refresh_token": refresh_cookie}
        ) as c1,
        AsyncClient(
            transport=transport, base_url="http://test", cookies={"refresh_token": refresh_cookie}
        ) as c2,
    ):
        r1, r2 = await asyncio.gather(
            c1.post("/api/auth/refresh"),
            c2.post("/api/auth/refresh"),
        )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 401], f"Expected single valid refresh rotation, got {codes}"


@pytest.mark.asyncio
async def test_idempotency_key_replay_and_conflict(client):
    import uuid

    await _login_admin(client)
    bad = await client.post(
        "/api/chats",
        json={"title": "bad-idem"},
        headers={"Idempotency-Key": "invalid key!"},
    )
    assert bad.status_code == 400

    key = f"idem-chat-{uuid.uuid4().hex}"
    title = f"IdemChat-{uuid.uuid4().hex[:8]}"
    r1 = await client.post(
        "/api/chats",
        json={"title": title, "use_rag": False},
        headers={"Idempotency-Key": key},
    )
    r2 = await client.post(
        "/api/chats",
        json={"title": title, "use_rag": False},
        headers={"Idempotency-Key": key},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    conflict = await client.post(
        "/api/chats",
        json={"title": f"{title}-Different", "use_rag": False},
        headers={"Idempotency-Key": key},
    )
    assert conflict.status_code == 409

    listing = await client.get("/api/chats", params={"q": title})
    matches = [c for c in listing.json() if c["title"] == title]
    assert len(matches) == 1
    await client.delete(f"/api/chats/{r1.json()['id']}")


def test_ws_ticket_single_use_and_worker_hw_info():
    settings = get_settings()
    with TestClient(app) as tc:
        # Unauthenticated internal embeddings must fail
        unauth = tc.post(
            "/api/internal/embeddings",
            json={"input": ["hello"], "model": settings.DEFAULT_EMBED_MODEL},
        )
        assert unauth.status_code == 401

        login = tc.post(
            "/api/auth/login",
            json={"username": "admin", "password": "adminpass12"},
        )
        assert login.status_code == 200, login.text
        ticket = tc.post("/api/auth/ws-ticket").json()["ticket"]

        # First WS connection succeeds
        with tc.websocket_connect(f"/ws/client?ticket={ticket}") as ws:
            first = ws.receive_json()
            assert first["type"] == "sys_status"

        # Replaying same ticket must be rejected
        with pytest.raises((WebSocketDisconnect, Exception)):
            with tc.websocket_connect(f"/ws/client?ticket={ticket}") as ws:
                ws.receive_text()

        # Connect simulated PC Worker and verify hw_info propagates to /api/ready
        with tc.websocket_connect(f"/ws/pc?token={settings.WORKER_TOKEN}") as pc_ws:
            probe = pc_ws.receive_json()
            assert probe["type"] == "get_models"
            pc_ws.send_json({"v": 1, "type": "hw_info", "payload": {"hw": "GPU"}})
            ready = tc.get("/api/ready").json()
            assert ready["worker"]["worker_online"] is True
            assert ready["worker"]["hw"] == "GPU"


@pytest.mark.asyncio
async def test_internal_embeddings_rpc_and_auth(client):
    settings = get_settings()
    bad = await client.post(
        "/api/internal/embeddings",
        headers={"X-Worker-Token": "wrong-token"},
        json={"input": ["hello"], "model": settings.DEFAULT_EMBED_MODEL},
    )
    assert bad.status_code == 401

    class _DummyWorkerWs:
        client_state = __import__("starlette.websockets").websockets.WebSocketState.CONNECTED

        def __init__(self) -> None:
            self.sent: list[dict] = []

        async def send_json(self, data: dict) -> None:
            self.sent.append(data)
            req_id = data["payload"]["request_id"]
            manager.resolve_embeddings(
                req_id,
                {"data": [{"index": 0, "embedding": [0.1] * settings.EMBED_DIM}]},
            )

    prev_pc = manager.pc_client
    dummy = _DummyWorkerWs()
    manager.pc_client = dummy  # type: ignore[assignment]
    try:
        ok = await client.post(
            "/api/internal/embeddings",
            headers={"X-Worker-Token": settings.WORKER_TOKEN},
            json={"input": ["test phrase"], "model": settings.DEFAULT_EMBED_MODEL},
        )
        assert ok.status_code == 200, ok.text
        assert len(ok.json()["data"][0]["embedding"]) == settings.EMBED_DIM
        assert dummy.sent and dummy.sent[0]["type"] == "embeddings"
    finally:
        manager.pc_client = prev_pc


@pytest.mark.asyncio
async def test_chat_crud_export_and_invalid_uuid(client):
    await _login_admin(client)
    bad_uuid = await client.get("/api/chats/not-a-uuid")
    assert bad_uuid.status_code == 422

    created = await client.post("/api/chats", json={"title": "CrudChat", "use_rag": False})
    assert created.status_code == 200
    cid = created.json()["id"]

    patched = await client.patch(
        f"/api/chats/{cid}",
        json={"title": "RenamedCrudChat", "use_rag": True, "model": "demo-model"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "RenamedCrudChat"
    assert patched.json()["use_rag"] is True
    assert patched.json()["model"] == "demo-model"

    exp_md = await client.get(f"/api/chats/{cid}/export", params={"format": "md"})
    assert exp_md.status_code == 200
    assert "# RenamedCrudChat" in exp_md.text

    exp_json = await client.get(f"/api/chats/{cid}/export", params={"format": "json"})
    assert exp_json.status_code == 200
    assert exp_json.json()["title"] == "RenamedCrudChat"

    deleted = await client.delete(f"/api/chats/{cid}")
    assert deleted.status_code == 200
    missing = await client.get(f"/api/chats/{cid}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_knowledge_upload_validation_patch_and_bola(client):
    await _login_admin(client)

    bad_pdf = await client.post(
        "/api/knowledge/docs",
        files={"file": ("fake.pdf", io.BytesIO(b"not-a-pdf"), "application/pdf")},
    )
    assert bad_pdf.status_code == 400

    too_big = await client.post(
        "/api/knowledge/docs",
        files={"file": ("big.txt", io.BytesIO(b"a" * (10 * 1024 * 1024 + 10)), "text/plain")},
    )
    assert too_big.status_code == 413

    # Create a small valid text document (metadata/CRUD check without requiring LM Studio embed)
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.entities import KnowledgeDoc, User

    async with SessionLocal() as db:
        admin_user = await db.scalar(select(User).where(User.username == "admin"))
        assert admin_user is not None
        doc = KnowledgeDoc(
            user_id=admin_user.id,
            title="PrivateSpec.md",
            filename="PrivateSpec.md",
            content_type="text/markdown",
            size_bytes=42,
            storage_path="/tmp/nonexistent-test.md",
            is_shared=False,
            status="ready",
        )
        db.add(doc)
        await db.commit()
        doc_id = str(doc.id)

    patched = await client.patch(
        f"/api/knowledge/docs/{doc_id}",
        json={"title": "SharedSpec.md", "is_shared": True},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "SharedSpec.md"
    assert patched.json()["is_shared"] is True

    # Non-owner sees shared doc with is_owner=False and cannot patch/delete it
    await client.post(
        "/api/users",
        json={"username": "bola_user_99", "password": "bolapass1234", "role": "user"},
    )
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"username": "bola_user_99", "password": "bolapass1234"},
    )
    listed = await client.get("/api/knowledge/docs", params={"q": "SharedSpec"})
    assert listed.status_code == 200
    row = next(d for d in listed.json() if d["id"] == doc_id)
    assert row["is_owner"] is False

    deny_patch = await client.patch(f"/api/knowledge/docs/{doc_id}", json={"title": "Hijacked"})
    assert deny_patch.status_code == 404
    deny_del = await client.delete(f"/api/knowledge/docs/{doc_id}")
    assert deny_del.status_code == 404

    await client.post("/api/auth/logout")
    await _login_admin(client)
    cleanup = await client.delete(f"/api/knowledge/docs/{doc_id}")
    assert cleanup.status_code == 200


@pytest.mark.asyncio
async def test_admin_rbac_self_lockout_invites_and_audits(client):
    await _login_admin(client)
    me = (await client.get("/api/auth/me")).json()

    # Self-deactivation and self-demotion must be blocked
    self_deact = await client.patch(f"/api/users/{me['id']}", json={"is_active": False})
    assert self_deact.status_code == 400
    self_demote = await client.patch(f"/api/users/{me['id']}", json={"role": "user"})
    assert self_demote.status_code == 400

    # Create and revoke invite
    inv = await client.post("/api/users/invites", json={"email": "rev@example.com", "role": "user"})
    assert inv.status_code == 200
    inv_id = inv.json()["id"]
    rev = await client.delete(f"/api/users/invites/{inv_id}")
    assert rev.status_code == 200
    rev_again = await client.delete(f"/api/users/invites/{inv_id}")
    assert rev_again.status_code == 404

    # Audit logs and prune
    audits = await client.get("/api/admin/audit-logs", params={"limit": 10})
    assert audits.status_code == 200
    assert audits.json()["total"] >= 1
    prune = await client.post("/api/admin/maintenance/prune")
    assert prune.status_code == 200
    assert "refresh_tokens" in prune.json()

    # Non-admin blocked from /api/admin/models & audit-logs
    await client.post(
        "/api/users",
        json={"username": "nonadmin_99", "password": "nonadminpass12", "role": "user"},
    )
    await client.post("/api/auth/logout")
    await client.post(
        "/api/auth/login",
        json={"username": "nonadmin_99", "password": "nonadminpass12"},
    )
    assert (await client.get("/api/admin/models")).status_code == 403
    assert (await client.get("/api/admin/audit-logs")).status_code == 403
    assert (await client.post("/api/admin/maintenance/prune")).status_code == 403


@pytest.mark.asyncio
async def test_security_headers_and_csrf_origin_check(client):
    health = await client.get("/api/health", headers={"X-Request-ID": "bad\nheader"})
    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in health.headers["content-security-policy"]
    assert "\n" not in health.headers["x-request-id"]

    await _login_admin(client)
    csrf_bad = await client.post(
        "/api/chats",
        json={"title": "csrf-blocked"},
        headers={"Origin": "https://evil.attacker.example"},
    )
    assert csrf_bad.status_code == 403


def test_aes_gcm_cipher_roundtrip_and_tamper_rejection():
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    prev_key = os.environ.get("ENCRYPTION_KEY")
    os.environ["ENCRYPTION_KEY"] = "unit-test-strong-key-32-bytes!!"
    cipher_utils = None
    try:
        import cipher_utils as cu

        cipher_utils = importlib.reload(cu)
        ct = cipher_utils.encrypt_message('{"msg":"سلام"}')
        assert ct.startswith("v2:")
        assert cipher_utils.decrypt_message(ct) == '{"msg":"سلام"}'

        mid = len(ct) // 2
        flip = "A" if ct[mid] != "A" else "B"
        tampered = ct[:mid] + flip + ct[mid + 1 :]
        dec_bad = cipher_utils.decrypt_message(tampered)
        assert "Security error" in dec_bad
    finally:
        if prev_key is None:
            os.environ.pop("ENCRYPTION_KEY", None)
        else:
            os.environ["ENCRYPTION_KEY"] = prev_key
        if cipher_utils is not None:
            importlib.reload(cipher_utils)


def test_pc_client_build_chat_messages_preserves_assistant_and_current_turn():
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from pc_client.main import build_chat_messages

    history = [
        {"role": "user", "content": "سلام"},
        {"role": "assistant", "content": "سلام! چطور کمک کنم؟"},
    ]
    built = build_chat_messages(
        system_prompt="SYS",
        user_text="سوال دوم",
        req_history=history,
    )
    assert built[0] == {"role": "system", "content": "SYS"}
    assert built[1] == {"role": "user", "content": "سلام"}
    assert built[2] == {"role": "assistant", "content": "سلام! چطور کمک کنم؟"}
    assert built[3] == {"role": "user", "content": "سوال دوم"}
