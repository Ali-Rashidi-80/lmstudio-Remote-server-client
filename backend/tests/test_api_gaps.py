"""Regression tests for phase-1 gaps closed during verification."""

from __future__ import annotations

import io

import pytest


@pytest.mark.asyncio
async def test_logout_blacklists_access_token(client):
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    assert login.status_code == 200, login.text
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 200
    # Cookie may still be present on the AsyncClient jar after delete_cookie
    # depending on httpx behavior — clear and re-set from logout response cookies.
    # After logout, /me with previous cookie must fail if blacklist works.
    # Force reuse of the access cookie value captured at login.
    token = login.cookies.get("access_token") or login.json().get("access_token")
    assert token
    denied = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 401, denied.text


@pytest.mark.asyncio
async def test_reject_executable_upload(client):
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    assert login.status_code == 200
    files = {
        "file": ("evil.exe", io.BytesIO(b"MZ\x00\x00not-a-real-exe"), "application/octet-stream")
    }
    up = await client.post("/api/knowledge/docs", files=files)
    assert up.status_code == 400
    assert "blocked" in up.text.lower() or "Executable" in up.text


@pytest.mark.asyncio
async def test_chat_title_search(client):
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    assert login.status_code == 200
    created = await client.post(
        "/api/chats",
        json={"title": "UniqueZebraChatTitle-991", "use_rag": False},
    )
    assert created.status_code == 200, created.text
    found = await client.get("/api/chats", params={"q": "ZebraChatTitle"})
    assert found.status_code == 200
    titles = [c["title"] for c in found.json()]
    assert any("UniqueZebraChatTitle-991" in t for t in titles)
    empty = await client.get("/api/chats", params={"q": "no-such-title-zzz"})
    assert empty.status_code == 200
    assert empty.json() == []
