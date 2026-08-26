from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatCreate(BaseModel):
    title: str = "New chat"
    model: str | None = None
    use_rag: bool = False


class ChatOut(BaseModel):
    id: str
    title: str
    model: str | None
    use_rag: bool
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    meta: dict | None = None
    created_at: datetime


class LocalImportSession(BaseModel):
    title: str = "Imported"
    history: list[dict] = Field(default_factory=list)


class LocalImportRequest(BaseModel):
    sessions: list[LocalImportSession]
