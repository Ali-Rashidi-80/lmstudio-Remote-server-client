from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import WebSocketException

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models.entities import Chat, Message, User, UserRole
from app.services.rag import build_rag_context, resolve_chat_model, retrieve
from app.ws.manager import manager

router = APIRouter(tags=["ws"])
logger = logging.getLogger("ws.routes")


def _origin_ok(websocket: WebSocket) -> bool:
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if not origin:
        # Browsers always send Origin on WS; missing Origin is non-browser tooling only.
        return True
    return origin in settings.cors_origin_list


async def _persist_assistant(user_id: str, content: str) -> None:
    """Persist assembled assistant text (streaming buffer or full) for active chat."""
    if not content.strip():
        return
    chat_id = manager.active_chat_ids.get(user_id)
    if not chat_id:
        return
    sources = manager.pending_sources.pop(user_id, None)
    try:
        async with SessionLocal() as db:
            chat = await db.get(Chat, uuid.UUID(str(chat_id)))
            if chat and str(chat.user_id) == user_id:
                db.add(
                    Message(
                        chat_id=chat.id,
                        role="assistant",
                        content=content,
                        meta={"sources": sources} if sources else None,
                    )
                )
                await db.commit()
    except Exception:
        logger.exception("Failed to persist assistant message")


async def _finalize_assistant_from_worker(user_id: str, message: dict) -> None:
    """Handle Worker full/done: flush stream buffer and persist."""
    payload = message.get("payload") or {}
    msg_type = message.get("type")
    piece = payload.get("content") or message.get("content") or ""
    if msg_type in {"chunk", "delta"} and piece:
        manager.stream_buffers[user_id] = manager.stream_buffers.get(user_id, "") + str(piece)
        return
    if msg_type == "full" and piece:
        manager.stream_buffers[user_id] = str(piece)
        await _persist_assistant(user_id, str(piece))
        manager.stream_buffers.pop(user_id, None)
        return
    if msg_type == "done":
        buffered = manager.stream_buffers.pop(user_id, "")
        final = (piece or buffered or "").strip()
        if final:
            await _persist_assistant(user_id, final)
        else:
            manager.pending_sources.pop(user_id, None)


@router.websocket("/ws/pc")
async def ws_pc(websocket: WebSocket, token: str = Query(...)) -> None:
    settings = get_settings()
    if token != settings.WORKER_TOKEN:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    await manager.connect_pc(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Worker may send plaintext JSON with v/type
            msg_type = data.get("type")
            client_id = data.get("client_id")
            if msg_type == "hw_info":
                manager.pc_hw_mode = data.get("payload", {}).get("hw", data.get("hw", "CPU"))
                await manager.broadcast_sys_status(True, manager.pc_hw_mode)
                continue
            if msg_type == "ping":
                await websocket.send_json({"v": 1, "type": "pong"})
                continue
            if msg_type == "embeddings_result":
                payload = data.get("payload") or {}
                request_id = payload.get("request_id") or data.get("request_id")
                if request_id:
                    manager.resolve_embeddings(str(request_id), payload)
                continue
            if msg_type == "error" and client_id == "system":
                payload = data.get("payload") or {}
                request_id = payload.get("request_id") or data.get("request_id")
                if request_id:
                    manager.resolve_embeddings(
                        str(request_id),
                        {"error": payload.get("content") or data.get("content") or "embed failed"},
                    )
                continue
            if client_id and client_id != "system":
                outbound = data if data.get("v") else {"v": 1, **data}
                if msg_type in {"chunk", "delta", "full", "done"}:
                    await _finalize_assistant_from_worker(str(client_id), outbound)
                await manager.route_to_user(str(client_id), outbound)
    except WebSocketDisconnect:
        await manager.disconnect_pc()
    except Exception:
        logger.exception("PC websocket error")
        await manager.disconnect_pc()


@router.websocket("/ws/client")
async def ws_client(websocket: WebSocket, ticket: str = Query(...)) -> None:
    if not _origin_ok(websocket):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        payload = decode_token(ticket, expected_type="ws")
        user_id = payload["sub"]
        role = payload.get("role")
    except Exception as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc

    async with SessionLocal() as db:
        user = await db.get(User, uuid.UUID(user_id))
        if not user or not user.is_active or user.role == UserRole.pending:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await manager.connect_user(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            if data.get("v") != 1:
                await websocket.send_json(
                    {
                        "v": 1,
                        "type": "error",
                        "payload": {"content": "Unsupported protocol; use v=1"},
                    }
                )
                continue
            msg_type = data.get("type")
            payload_data = data.get("payload") or {}

            if msg_type == "unload_models" and role != "admin":
                await websocket.send_json(
                    {"v": 1, "type": "error", "payload": {"content": "Admin only"}}
                )
                continue

            if msg_type == "chat":
                content = payload_data.get("content") or payload_data.get("message") or ""
                chat_id = payload_data.get("chat_id")
                use_rag = bool(payload_data.get("use_rag"))
                sources: list[dict] = []
                async with SessionLocal() as db:
                    if not payload_data.get("model"):
                        payload_data = {
                            **payload_data,
                            "model": await resolve_chat_model(db),
                        }
                    if use_rag and content:
                        sources = await retrieve(db, uuid.UUID(user_id), content, top_k=5)
                if sources:
                    context = build_rag_context(sources)
                    payload_data = {
                        **payload_data,
                        "rag_context": context,
                        "sources": sources,
                    }
                    manager.pending_sources[user_id] = sources
                    await websocket.send_json(
                        {"v": 1, "type": "rag_sources", "payload": {"sources": sources}}
                    )
                manager.stream_buffers[user_id] = ""
                if chat_id:
                    manager.active_chat_ids[user_id] = str(chat_id)
                if chat_id and content:
                    async with SessionLocal() as db:
                        chat = await db.get(Chat, uuid.UUID(str(chat_id)))
                        if chat and str(chat.user_id) == user_id:
                            db.add(Message(chat_id=chat.id, role="user", content=content))
                            await db.commit()

                ok = await manager.route_to_pc(
                    {
                        "v": 1,
                        "type": "chat",
                        "client_id": user_id,
                        "payload": payload_data,
                    }
                )
                if not ok:
                    await websocket.send_json(
                        {
                            "v": 1,
                            "type": "error",
                            "payload": {"content": "PC Worker offline"},
                        }
                    )
                continue

            # Persist assistant finals if present from client echo — primary path is worker->user
            ok = await manager.route_to_pc(
                {
                    "v": 1,
                    "type": msg_type,
                    "client_id": user_id,
                    "payload": payload_data,
                }
            )
            if not ok and msg_type != "ping":
                await websocket.send_json(
                    {"v": 1, "type": "error", "payload": {"content": "PC Worker offline"}}
                )
    except WebSocketDisconnect:
        await manager.disconnect_user(user_id)
    except Exception:
        logger.exception("Client websocket error")
        await manager.disconnect_user(user_id)
