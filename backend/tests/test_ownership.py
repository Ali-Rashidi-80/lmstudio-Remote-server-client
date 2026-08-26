"""Auth and chat ownership — must fail honestly if DB/Redis broken."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]


@pytest.mark.asyncio
async def test_ready_requires_db_and_redis(client):
    r = await client.get("/api/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] is True, f"DB not ready: {body}"
    assert body["redis"] is True, f"Redis not ready: {body}"
    assert body["ready"] is True


@pytest.mark.asyncio
async def test_open_register_forbidden(client):
    r = await client.post("/api/auth/register", json={})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_chat_isolation(client):
    login_a = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    assert login_a.status_code == 200, login_a.text

    create = await client.post(
        "/api/users",
        json={"username": "alice_iso", "password": "alicepass12", "role": "user"},
    )
    assert create.status_code in (200, 400), create.text

    chat = await client.post("/api/chats", json={"title": "admin-private-chat"})
    assert chat.status_code == 200, chat.text
    chat_id = chat.json()["id"]

    await client.post("/api/auth/logout")
    login_b = await client.post(
        "/api/auth/login",
        json={"username": "alice_iso", "password": "alicepass12"},
    )
    assert login_b.status_code == 200, login_b.text
    forbidden = await client.get(f"/api/chats/{chat_id}/messages")
    assert forbidden.status_code == 404
