from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import AdminUser, CurrentUser, DbDep
from app.core.config import get_settings
from app.models.entities import AppSetting, KnowledgeDoc, RagJob, User, UserRole
from app.services.audit import write_audit
from app.services.rag import index_document
from app.ws.manager import manager

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SettingsUpdate(BaseModel):
    default_chat_model: str | None = None
    default_embed_model: str | None = None


@router.get("/stats")
async def stats(_: AdminUser, db: DbDep) -> dict:
    users = await db.scalar(select(func.count()).select_from(User))
    docs = await db.scalar(select(func.count()).select_from(KnowledgeDoc))
    jobs = await db.scalar(
        select(func.count()).select_from(RagJob).where(RagJob.status.in_(["queued", "running"]))
    )
    return {
        "users": users or 0,
        "docs": docs or 0,
        "active_rag_jobs": jobs or 0,
        "worker": manager.status(),
    }


@router.get("/settings")
async def get_settings_api(_: AdminUser, db: DbDep) -> dict:
    settings = get_settings()
    chat = await db.get(AppSetting, "default_chat_model")
    embed = await db.get(AppSetting, "default_embed_model")
    return {
        "default_chat_model": (chat.value.get("value") if chat else settings.DEFAULT_CHAT_MODEL),
        "default_embed_model": (
            embed.value.get("value") if embed else settings.DEFAULT_EMBED_MODEL
        ),
        "embed_dim": settings.EMBED_DIM,
    }


@router.put("/settings")
async def put_settings(body: SettingsUpdate, admin: AdminUser, db: DbDep) -> dict:
    if body.default_chat_model:
        row = await db.get(AppSetting, "default_chat_model")
        if not row:
            db.add(AppSetting(key="default_chat_model", value={"value": body.default_chat_model}))
        else:
            row.value = {"value": body.default_chat_model}
    if body.default_embed_model:
        row = await db.get(AppSetting, "default_embed_model")
        if not row:
            db.add(AppSetting(key="default_embed_model", value={"value": body.default_embed_model}))
        else:
            row.value = {"value": body.default_embed_model}
        await write_audit(
            db,
            "embed_model_change",
            actor_id=admin.id,
            detail={"model": body.default_embed_model, "reindex_required": True},
        )
    await db.commit()
    return await get_settings_api(admin, db)


@router.post("/reindex")
async def reindex_all(admin: AdminUser, db: DbDep) -> dict:
    """Re-embed all knowledge documents with the current DEFAULT_EMBED_MODEL."""
    docs = (await db.scalars(select(KnowledgeDoc))).all()
    ok = 0
    failed = 0
    for doc in docs:
        try:
            doc.status = "queued"
            await db.commit()
            n = await index_document(db, doc)
            if n > 0:
                ok += 1
            else:
                failed += 1
        except Exception as exc:  # pylint: disable=broad-exception-caught
            failed += 1
            doc.status = "failed"
            await db.commit()
            await write_audit(
                db,
                "reindex_doc_failed",
                actor_id=admin.id,
                detail={"doc_id": str(doc.id), "error": str(exc)},
            )
    await write_audit(
        db,
        "reindex_all",
        actor_id=admin.id,
        detail={"ok": ok, "failed": failed, "total": len(docs)},
    )
    return {"ok": ok, "failed": failed, "total": len(docs)}


@router.post("/unload-models")
async def unload_models(admin: AdminUser, db: DbDep) -> dict:
    if admin.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin only")
    ok = await manager.route_to_pc(
        {"v": 1, "type": "unload_models", "client_id": "admin", "payload": {}}
    )
    await write_audit(db, "unload_models", actor_id=admin.id)
    if not ok:
        raise HTTPException(status_code=503, detail="Worker offline")
    return {"ok": True}


@router.get("/models")
async def models_proxy(user: CurrentUser, db: DbDep) -> dict:
    from app.services.rag import resolve_chat_model, resolve_embed_model

    return {
        "default_chat_model": await resolve_chat_model(db),
        "default_embed_model": await resolve_embed_model(db),
        "worker": manager.status(),
        "note": "Live model list is pushed over WebSocket type=models_list",
    }
