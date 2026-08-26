"""AI Workspace Bridge — FastAPI entrypoint."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routes import admin, auth, chats, health, knowledge, users, ws
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.redis import close_redis
from app.db.session import SessionLocal, engine
from app.services.bootstrap import (
    bootstrap_admin,
    ensure_default_settings,
    ensure_hnsw_index,
    ensure_pgvector,
)

settings = get_settings()
setup_logging(settings.DEBUG)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    # pgvector extension must exist before creating VECTOR columns
    async with SessionLocal() as session:
        await ensure_pgvector(session)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await ensure_hnsw_index(session)
        await bootstrap_admin(session)
        await ensure_default_settings(session)
    logger.info("AI Workspace %s started", settings.APP_VERSION)
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(title="AI Workspace Bridge", version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    from app.core.request_context import request_id_ctx

    rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = rid
    token = request_id_ctx.set(rid)
    try:
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        request_id_ctx.reset(token)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chats.router)
app.include_router(knowledge.router)
app.include_router(admin.router)
app.include_router(ws.router)


@app.get("/")
async def root() -> RedirectResponse:
    # Legacy HTML UI removed from primary path; Next.js is the product UI.
    origins = settings.cors_origin_list
    target = origins[0] if origins else "http://localhost:3000"
    return RedirectResponse(url=target)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    run()
