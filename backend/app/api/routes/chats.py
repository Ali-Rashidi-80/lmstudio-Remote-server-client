from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.models.entities import Chat, Message
from app.schemas.chat import ChatCreate, ChatOut, LocalImportRequest, MessageOut
from app.services.audit import write_audit

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


@router.get("", response_model=list[ChatOut])
async def list_chats(user: CurrentUser, db: DbDep, q: str | None = None) -> list[ChatOut]:
    stmt = select(Chat).where(Chat.user_id == user.id)
    if q and q.strip():
        stmt = stmt.where(Chat.title.ilike(f"%{q.strip()}%"))
    rows = await db.scalars(stmt.order_by(Chat.updated_at.desc()))
    return [_chat_out(c) for c in rows]


@router.post("", response_model=ChatOut)
async def create_chat(body: ChatCreate, user: CurrentUser, db: DbDep) -> ChatOut:
    chat = Chat(user_id=user.id, title=body.title, model=body.model, use_rag=body.use_rag)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return _chat_out(chat)


@router.get("/{chat_id}", response_model=ChatOut)
async def get_chat(chat_id: str, user: CurrentUser, db: DbDep) -> ChatOut:
    chat = await db.get(Chat, uuid.UUID(chat_id))
    if not chat or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return _chat_out(chat)


@router.get("/{chat_id}/messages", response_model=list[MessageOut])
async def list_messages(chat_id: str, user: CurrentUser, db: DbDep) -> list[MessageOut]:
    chat = await db.get(Chat, uuid.UUID(chat_id))
    if not chat or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    rows = await db.scalars(
        select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at.asc())
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


@router.delete("/{chat_id}")
async def delete_chat(chat_id: str, user: CurrentUser, db: DbDep) -> dict:
    chat = await db.get(Chat, uuid.UUID(chat_id))
    if not chat or chat.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
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
