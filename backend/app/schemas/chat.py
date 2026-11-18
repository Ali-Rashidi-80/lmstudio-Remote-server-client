from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatCreate(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    use_rag: bool = False


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    use_rag: bool | None = None


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
    title: str = Field(default="Imported", max_length=255)
    history: list[dict] = Field(default_factory=list)


class LocalImportRequest(BaseModel):
    sessions: list[LocalImportSession]
