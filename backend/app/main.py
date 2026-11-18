"""AI Workspace Bridge — FastAPI entrypoint."""

from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.routes import admin, auth, chats, health, internal, knowledge, users, ws
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
from app.services.maintenance import prune_stale_records

settings = get_settings()
setup_logging(
    settings.DEBUG,
    log_file=settings.LOG_FILE,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT,
)
logger = logging.getLogger("app")

REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production_secrets()
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
        await prune_stale_records(session)
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
async def security_and_request_id_middleware(request: Request, call_next):
    from app.core.request_context import request_id_ctx

    raw_rid = (request.headers.get("X-Request-ID") or "").strip()
    rid = raw_rid if REQUEST_ID_RE.match(raw_rid) else str(uuid.uuid4())
    request.state.request_id = rid

    # CSRF defense-in-depth: cookie-authenticated mutating requests with an Origin header
    # must match configured CORS origins.
    if request.method in MUTATING_METHODS:
        origin = request.headers.get("origin")
        has_auth_cookie = bool(
            request.cookies.get("access_token") or request.cookies.get("refresh_token")
        )
        has_header_auth = bool(
            request.headers.get("authorization") or request.headers.get("x-worker-token")
        )
        if origin and has_auth_cookie and not has_header_auth:
            if origin not in settings.cors_origin_list:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF origin mismatch"},
                    headers={"X-Request-ID": rid},
                )

    token = request_id_ctx.set(rid)
    try:
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if settings.COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
    finally:
        request_id_ctx.reset(token)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chats.router)
app.include_router(knowledge.router)
app.include_router(admin.router)
app.include_router(internal.router)
app.include_router(ws.router)


@app.get("/")
async def root() -> RedirectResponse:
    # Legacy HTML UI removed from primary path; Next.js is the product UI.
    origins = settings.cors_origin_list
    target = origins[0] if origins else "http://localhost:3010"
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
