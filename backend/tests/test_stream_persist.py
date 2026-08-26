"""Unit tests for streaming assistant persistence (no Worker required)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.api.routes.ws import _finalize_assistant_from_worker
from app.db.session import SessionLocal
from app.models.entities import Chat, Message
from app.ws.manager import manager


@pytest.mark.asyncio
async def test_streaming_chunks_persist_on_done(client):
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "adminpass12"},
    )
    assert login.status_code == 200
    me = await client.get("/api/auth/me")
    user_id = me.json()["id"]

    created = await client.post(
        "/api/chats",
        json={"title": "stream-persist-test", "use_rag": False},
    )
    assert created.status_code == 200
    chat_id = created.json()["id"]

    manager.active_chat_ids[user_id] = chat_id
    manager.stream_buffers[user_id] = ""
    manager.pending_sources[user_id] = [{"doc_title": "t", "snippet": "s"}]

    await _finalize_assistant_from_worker(
        user_id, {"type": "chunk", "payload": {"content": "Hello "}}
    )
    await _finalize_assistant_from_worker(
        user_id, {"type": "chunk", "payload": {"content": "world"}}
    )
    await _finalize_assistant_from_worker(user_id, {"type": "done", "payload": {"content": ""}})

    async with SessionLocal() as db:
        chat = await db.get(Chat, uuid.UUID(chat_id))
        assert chat is not None
        rows = (
            await db.scalars(
                select(Message)
                .where(Message.chat_id == chat.id, Message.role == "assistant")
                .order_by(Message.created_at.desc())
            )
        ).all()
        assert rows, "assistant message not persisted after streaming done"
        assert rows[0].content == "Hello world"
        assert rows[0].meta and rows[0].meta.get("sources")
