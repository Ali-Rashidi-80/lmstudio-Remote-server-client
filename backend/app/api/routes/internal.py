from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.ws.manager import manager

router = APIRouter(prefix="/api/internal", tags=["internal"])


class InternalEmbedRequest(BaseModel):
    input: list[str] = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=255)


@router.post("/embeddings")
async def internal_embeddings(
    body: InternalEmbedRequest,
    x_worker_token: str = Header(default="", alias="X-Worker-Token"),
) -> dict:
    """Bridge-internal RPC so separate ARQ worker processes can embed via PC Worker WS."""
    settings = get_settings()
    if not x_worker_token or not secrets.compare_digest(x_worker_token, settings.WORKER_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid worker token")
    try:
        result = await manager.request_embeddings(body.input, body.model)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"data": result.get("data") or [], "model": body.model}
