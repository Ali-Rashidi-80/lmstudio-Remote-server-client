from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.models.entities import Chat, Message
from app.schemas.chat import ChatCreate, ChatOut, ChatUpdate, LocalImportRequest, MessageOut
from app.services.audit import write_audit
from app.services.idempotency import (
    abort_idempotency,
    begin_idempotency,
    complete_idempotency,
    hash_payload,
    validate_idempotency_key,
)
from app.services.rag import resolve_chat_model, resolve_embed_model
from app.ws.manager import manager

router = APIRouter(prefix="/api/chats", tags=["chats"])


def _chat_out(c: Chat) -> ChatOut:
    return ChatOut(
        id=str(c.id),
        title=c.title,
        model=c.model,
        use_rag=c.use_rag,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


async def _get_owned_chat(db: DbDep, chat_id: uuid.UUID, user_id: uuid.UUID) -> Chat:
    chat = await db.get(Chat, chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=404, detail="Not found")
    return chat


@router.get("/models")
async def chat_models(_: CurrentUser, db: DbDep) -> dict:
    default_chat = await resolve_chat_model(db)
    default_embed = await resolve_embed_model(db)
    worker = await manager.merged_status()
    raw_models = worker.get("models") or []
    model_ids: list[str] = []
    for m in raw_models:
        if isinstance(m, dict) and m.get("id"):
            mid = str(m["id"])
            if "embed" not in mid.lower() and "mmproj" not in mid.lower():
                model_ids.append(mid)
        elif isinstance(m, str):
            model_ids.append(m)
    if default_chat and default_chat not in model_ids:
        model_ids.insert(0, default_chat)
    return {
        "default_chat_model": default_chat,
        "default_embed_model": default_embed,
        "available_models": model_ids,
        "worker": {
            "worker_online": bool(worker.get("worker_online")),
            "hw": worker.get("hw", "CPU"),
        },
    }


@router.get("", response_model=list[ChatOut])
async def list_chats(
    user: CurrentUser,
    db: DbDep,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[ChatOut]:
    stmt = select(Chat).where(Chat.user_id == user.id)
    if q and q.strip():
        stmt = stmt.where(Chat.title.ilike(f"%{q.strip()}%"))
    rows = await db.scalars(stmt.order_by(Chat.updated_at.desc()).offset(offset).limit(limit))
    return [_chat_out(c) for c in rows]


@router.post("", response_model=ChatOut)
async def create_chat(
    body: ChatCreate,
    user: CurrentUser,
    db: DbDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ChatOut:
    idem_key = validate_idempotency_key(idempotency_key)
    p_hash = hash_payload(body.model_dump())
    replayed, cached = await begin_idempotency("chats_create", str(user.id), idem_key, p_hash)
    if replayed and cached is not None:
        return ChatOut(**cached)

    try:
        chat = Chat(
            user_id=user.id,
            title=body.title.strip() or "New chat",
            model=body.model,
            use_rag=body.use_rag,
        )
        db.add(chat)
        await db.commit()
        await db.refresh(chat)
        out = _chat_out(chat)
        await complete_idempotency(
            "chats_create", str(user.id), idem_key, p_hash, out.model_dump(mode="json")
        )
        return out
    except Exception:
        await abort_idempotency("chats_create", str(user.id), idem_key)
        raise


@router.get("/{chat_id}", response_model=ChatOut)
async def get_chat(chat_id: uuid.UUID, user: CurrentUser, db: DbDep) -> ChatOut:
    chat = await _get_owned_chat(db, chat_id, user.id)
    return _chat_out(chat)


@router.patch("/{chat_id}", response_model=ChatOut)
async def update_chat(
    chat_id: uuid.UUID, body: ChatUpdate, user: CurrentUser, db: DbDep
) -> ChatOut:
    chat = await _get_owned_chat(db, chat_id, user.id)
    if body.title is not None:
        cleaned = body.title.strip()
        if not cleaned:
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        chat.title = cleaned
    if "model" in body.model_fields_set:
        chat.model = body.model.strip() if body.model and body.model.strip() else None
    if body.use_rag is not None:
        chat.use_rag = body.use_rag
    chat.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(chat)
    return _chat_out(chat)


@router.get("/{chat_id}/messages", response_model=list[MessageOut])
async def list_messages(
    chat_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[MessageOut]:
    chat = await _get_owned_chat(db, chat_id, user.id)
    rows = await db.scalars(
        select(Message)
        .where(Message.chat_id == chat.id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    return [
        MessageOut(
            id=str(m.id),
            role=m.role,
            content=m.content,
            meta=m.meta,
            created_at=m.created_at,
        )
        for m in rows
    ]


@router.get("/{chat_id}/export")
async def export_chat(
    chat_id: uuid.UUID,
    user: CurrentUser,
    db: DbDep,
    export_format: Literal["md", "json"] = Query(default="md", alias="format"),
) -> Response:
    chat = await _get_owned_chat(db, chat_id, user.id)
    rows = (
        await db.scalars(
            select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at.asc())
        )
    ).all()

    if export_format == "json":
        payload = {
            "id": str(chat.id),
            "title": chat.title,
            "model": chat.model,
            "use_rag": chat.use_rag,
            "created_at": chat.created_at.isoformat(),
            "messages": [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "meta": m.meta,
                    "created_at": m.created_at.isoformat(),
                }
                for m in rows
            ],
        }
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="chat-{chat.id}.json"'},
        )

    lines = [
        f"# {chat.title}",
        "",
        f"- **Exported:** {datetime.now(UTC).isoformat()}",
        f"- **RAG:** {'Enabled' if chat.use_rag else 'Disabled'}",
        "",
    ]
    for m in rows:
        speaker = "User" if m.role == "user" else "Assistant"
        lines.append(f"## {speaker} ({m.created_at.isoformat()})")
        lines.append("")
        lines.append(m.content)
        sources = (m.meta or {}).get("sources") if isinstance(m.meta, dict) else None
        if sources:
            lines.append("")
            lines.append("**Sources:**")
            for src in sources:
                lines.append(f"- `{src.get('doc_title', 'doc')}`")
        lines.append("")

    return Response(
        content="\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="chat-{chat.id}.md"'},
    )


@router.delete("/{chat_id}")
async def delete_chat(chat_id: uuid.UUID, user: CurrentUser, db: DbDep) -> dict:
    chat = await _get_owned_chat(db, chat_id, user.id)
    await db.delete(chat)
    await db.commit()
    return {"ok": True}


@router.post("/import-local")
async def import_local(body: LocalImportRequest, user: CurrentUser, db: DbDep) -> dict:
    created = 0
    for session in body.sessions:
        chat = Chat(user_id=user.id, title=session.title or "Imported")
        db.add(chat)
        await db.flush()
        for item in session.history:
            role = str(item.get("role", "user"))
            content = str(item.get("content", ""))
            if not content:
                continue
            db.add(Message(chat_id=chat.id, role=role, content=content, meta={"imported": True}))
        created += 1
    await db.commit()
    await write_audit(db, "import_local", actor_id=user.id, detail={"chats": created})
    return {"imported": created}
