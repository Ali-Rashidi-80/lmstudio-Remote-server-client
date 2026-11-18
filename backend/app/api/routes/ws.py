from __future__ import annotations

import base64
import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import WebSocketException
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.redis import consume_ws_ticket
from app.db.session import SessionLocal
from app.models.entities import Chat, Message, User, UserRole
from app.services.rag import build_rag_context, resolve_chat_model, retrieve
from app.ws.manager import manager

router = APIRouter(tags=["ws"])
logger = logging.getLogger("ws.routes")


def _as_dict(val: object) -> dict[str, Any]:
    return val if isinstance(val, dict) else {}


def _origin_ok(websocket: WebSocket) -> bool:
    settings = get_settings()
    origin = websocket.headers.get("origin")
    if not origin:
        # Browsers always send Origin on WS; missing Origin is non-browser tooling only.
        return True
    return origin in settings.cors_origin_list


def _image_payload_within_limit(image_b64: str, max_bytes: int) -> bool:
    raw = image_b64.split(",", 1)[-1].strip()
    if len(raw) > ((max_bytes + 2) // 3) * 4 + 16:
        return False
    try:
        decoded = base64.b64decode(raw, validate=True)
        return len(decoded) <= max_bytes
    except Exception:
        return len(raw.encode("utf-8")) <= max_bytes


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
                chat.updated_at = datetime.now(UTC)
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
async def ws_pc(websocket: WebSocket, token: str = Query(default="")) -> None:
    settings = get_settings()
    auth = websocket.headers.get("authorization", "")
    header_token = auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else ""
    presented = token or header_token
    if not presented or not secrets.compare_digest(presented, settings.WORKER_TOKEN):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    await manager.connect_pc(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict):
                continue
            msg_type = data.get("type")
            client_id = data.get("client_id")
            payload = _as_dict(data.get("payload"))

            if msg_type == "hw_info":
                hw = str(
                    payload.get("hw")
                    or data.get("hw")
                    or payload.get("content")
                    or data.get("content")
                    or "CPU"
                )
                await manager.update_hw(hw)
                continue
            if msg_type == "ping":
                await manager.touch_worker()
                await websocket.send_json({"v": 1, "type": "pong"})
                continue
            if msg_type == "models_list":
                models = payload.get("models")
                if isinstance(models, list):
                    await manager.update_models(models)
                if client_id and client_id not in {"system", ""}:
                    outbound = data if data.get("v") else {"v": 1, **data}
                    await manager.route_to_user(str(client_id), outbound)
                continue
            if msg_type == "embeddings_result":
                request_id = payload.get("request_id") or data.get("request_id")
                if request_id:
                    manager.resolve_embeddings(str(request_id), payload)
                continue
            if msg_type == "error" and client_id == "system":
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
    except RuntimeError as exc:
        logger.debug("PC websocket closed during receive: %s", exc)
        await manager.disconnect_pc()
    except Exception:
        logger.exception("PC websocket error")
        await manager.disconnect_pc()


@router.websocket("/ws/client")
async def ws_client(websocket: WebSocket, ticket: str = Query(...)) -> None:
    settings = get_settings()
    if not _origin_ok(websocket):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    try:
        payload = decode_token(ticket, expected_type="ws")
        user_id = payload["sub"]
        role = payload.get("role")
        jti = payload.get("jti")
        exp = payload.get("exp")
        uid = uuid.UUID(str(user_id))
    except Exception as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc

    ttl = (
        max(int((exp or 0) - datetime.now(UTC).timestamp()), 1)
        if exp
        else settings.WS_TICKET_SECONDS
    )
    if not jti or not await consume_ws_ticket(str(jti), ttl):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    async with SessionLocal() as db:
        user = await db.get(User, uid)
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
            payload_data = _as_dict(data.get("payload"))

            if msg_type == "ping":
                await websocket.send_json({"v": 1, "type": "pong"})
                continue

            if msg_type == "unload_models" and role != "admin":
                await websocket.send_json(
                    {"v": 1, "type": "error", "payload": {"content": "Admin only"}}
                )
                continue

            if msg_type == "chat":
                content = str(payload_data.get("content") or payload_data.get("message") or "")
                raw_chat_id = payload_data.get("chat_id")
                image_b64 = payload_data.get("image")
                if image_b64 and (
                    not isinstance(image_b64, str)
                    or not _image_payload_within_limit(image_b64, settings.MAX_IMAGE_BYTES)
                ):
                    await websocket.send_json(
                        {
                            "v": 1,
                            "type": "error",
                            "payload": {"content": "تصویر ارسالی بیش از حد مجاز (۲ مگابایت) است."},
                        }
                    )
                    continue

                parsed_chat_id: uuid.UUID | None = None
                if raw_chat_id:
                    try:
                        parsed_chat_id = uuid.UUID(str(raw_chat_id))
                    except ValueError:
                        await websocket.send_json(
                            {
                                "v": 1,
                                "type": "error",
                                "payload": {"content": "شناسه گفتگو نامعتبر است."},
                            }
                        )
                        continue

                use_rag = bool(payload_data.get("use_rag"))
                sources: list[dict] = []
                async with SessionLocal() as db:
                    chat_row: Chat | None = None
                    if parsed_chat_id:
                        chat_row = await db.get(Chat, parsed_chat_id)
                        if not chat_row or chat_row.user_id != uid:
                            await websocket.send_json(
                                {
                                    "v": 1,
                                    "type": "error",
                                    "payload": {"content": "گفتگو یافت نشد یا مجاز نیست."},
                                }
                            )
                            continue
                        if not payload_data.get("history"):
                            prev = (
                                await db.scalars(
                                    select(Message)
                                    .where(Message.chat_id == chat_row.id)
                                    .order_by(Message.created_at.asc())
                                )
                            ).all()
                            if prev:
                                payload_data = {
                                    **payload_data,
                                    "history": [
                                        {"role": m.role, "content": m.content}
                                        for m in prev[-20:]
                                        if m.role in {"user", "assistant"}
                                    ],
                                }

                    if not payload_data.get("model"):
                        chat_model = chat_row.model if chat_row and chat_row.model else None
                        payload_data = {
                            **payload_data,
                            "model": chat_model or await resolve_chat_model(db),
                        }

                    if use_rag and content.strip():
                        try:
                            sources = await retrieve(db, uid, content, top_k=5)
                        except RuntimeError as exc:
                            await websocket.send_json(
                                {"v": 1, "type": "error", "payload": {"content": str(exc)}}
                            )
                            continue

                    if chat_row and (content.strip() or image_b64):
                        db.add(
                            Message(
                                chat_id=chat_row.id,
                                role="user",
                                content=content or "[تصویر]",
                            )
                        )
                        if chat_row.title in {"New chat", "گفتگوی جدید"} and content.strip():
                            chat_row.title = content.strip()[:60]
                        chat_row.updated_at = datetime.now(UTC)
                        await db.commit()

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
                else:
                    manager.pending_sources.pop(user_id, None)

                manager.stream_buffers[user_id] = ""
                if parsed_chat_id:
                    manager.active_chat_ids[user_id] = str(parsed_chat_id)

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

            ok = await manager.route_to_pc(
                {
                    "v": 1,
                    "type": msg_type,
                    "client_id": user_id,
                    "payload": payload_data,
                }
            )
            if not ok:
                await websocket.send_json(
                    {"v": 1, "type": "error", "payload": {"content": "PC Worker offline"}}
                )
    except WebSocketDisconnect:
        await manager.disconnect_user(user_id)
    except RuntimeError as exc:
        logger.debug("Client websocket closed during receive: %s", exc)
        await manager.disconnect_user(user_id)
    except Exception:
        logger.exception("Client websocket error")
        await manager.disconnect_user(user_id)
