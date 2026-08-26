"""Security invariants — real assertions only."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


def test_env_example_has_no_committed_secrets():
    text = Path(__file__).resolve().parents[2].joinpath(".env.example").read_text(encoding="utf-8")
    assert "S1SD50" not in text
    assert "adminpass12" not in text
    assert "change-me" in text


def test_legacy_html_does_not_inject_key():
    html = (
        Path(__file__)
        .resolve()
        .parents[2]
        .joinpath("templates/index.html")
        .read_text(encoding="utf-8")
    )
    assert "{{ env_key }}" not in html


def test_ws_pc_rejects_bad_token():
    with TestClient(app) as tc:
        with pytest.raises((WebSocketDisconnect, Exception)):
            with tc.websocket_connect("/ws/pc?token=definitely-wrong") as ws:
                ws.receive_text()


@pytest.mark.asyncio
async def test_unload_models_forbidden_for_user(client):
    from app.db.redis import get_redis

    rds = await get_redis()
    for key in await rds.keys("login_rl:*"):
        await rds.delete(key)

    admin = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    assert admin.status_code == 200, admin.text
    created = await client.post(
        "/api/users",
        json={"username": "carol_sec", "password": "carolpass12", "role": "user"},
    )
    assert created.status_code in {200, 400}, created.text
    await client.post("/api/auth/logout")
    login = await client.post(
        "/api/auth/login",
        json={"username": "carol_sec", "password": "carolpass12"},
    )
    assert login.status_code == 200, login.text
    r = await client.post("/api/admin/unload-models")
    assert r.status_code == 403


def test_cipher_utils_no_default_key_constant():
    root = Path(__file__).resolve().parents[2]
    src = (root / "cipher_utils.py").read_text(encoding="utf-8")
    assert "12345678901234567890123456789012" not in src
    assert "fail" in src.lower() or "missing" in src.lower() or "too short" in src.lower()
