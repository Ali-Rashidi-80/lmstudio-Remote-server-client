from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbDep
from app.core.config import get_settings
from app.models.entities import (
    AppSetting,
    AuditLog,
    KnowledgeDoc,
    RagChunk,
    RagJob,
    User,
    UserRole,
)
from app.services.audit import write_audit
from app.services.idempotency import (
    abort_idempotency,
    begin_idempotency,
    complete_idempotency,
    hash_payload,
    validate_idempotency_key,
)
from app.services.maintenance import prune_stale_records
from app.services.rag import index_document, resolve_chat_model, resolve_embed_model
from app.ws.manager import manager

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SettingsUpdate(BaseModel):
    default_chat_model: str | None = Field(default=None, min_length=1, max_length=255)
    default_embed_model: str | None = Field(default=None, min_length=1, max_length=255)


@router.get("/stats")
async def stats(_: AdminUser, db: DbDep) -> dict:
    settings = get_settings()
    users = await db.scalar(select(func.count()).select_from(User))
    docs = await db.scalar(select(func.count()).select_from(KnowledgeDoc))
    chunks = await db.scalar(select(func.count()).select_from(RagChunk))
    audits = await db.scalar(select(func.count()).select_from(AuditLog))
    jobs = await db.scalar(
        select(func.count()).select_from(RagJob).where(RagJob.status.in_(["queued", "running"]))
    )
    worker = await manager.merged_status()
    return {
        "app_version": settings.APP_VERSION,
        "users": users or 0,
        "docs": docs or 0,
        "chunks": chunks or 0,
        "audit_logs": audits or 0,
        "active_rag_jobs": jobs or 0,
        "worker": worker,
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
        cleaned_chat = body.default_chat_model.strip()
        row = await db.get(AppSetting, "default_chat_model")
        if not row:
            db.add(AppSetting(key="default_chat_model", value={"value": cleaned_chat}))
        else:
            row.value = {"value": cleaned_chat}
    if body.default_embed_model:
        cleaned_embed = body.default_embed_model.strip()
        row = await db.get(AppSetting, "default_embed_model")
        if not row:
            db.add(AppSetting(key="default_embed_model", value={"value": cleaned_embed}))
        else:
            row.value = {"value": cleaned_embed}
        await write_audit(
            db,
            "embed_model_change",
            actor_id=admin.id,
            detail={"model": cleaned_embed, "reindex_required": True},
        )
    await db.commit()
    return await get_settings_api(admin, db)


@router.post("/reindex")
async def reindex_all(
    admin: AdminUser,
    db: DbDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    """Re-embed all knowledge documents with the current DEFAULT_EMBED_MODEL."""
    idem_key = validate_idempotency_key(idempotency_key)
    p_hash = hash_payload({"action": "reindex_all"})
    replayed, cached = await begin_idempotency("admin_reindex", str(admin.id), idem_key, p_hash)
    if replayed and cached is not None:
        return cached

    try:
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
                    detail={"doc_id": str(doc.id), "error": str(exc)[:300]},
                )
        await write_audit(
            db,
            "reindex_all",
            actor_id=admin.id,
            detail={"ok": ok, "failed": failed, "total": len(docs)},
        )
        res = {"ok": ok, "failed": failed, "total": len(docs)}
        await complete_idempotency("admin_reindex", str(admin.id), idem_key, p_hash, res)
        return res
    except Exception:
        await abort_idempotency("admin_reindex", str(admin.id), idem_key)
        raise


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
async def models_proxy(_: AdminUser, db: DbDep) -> dict:
    worker = await manager.merged_status()
    return {
        "default_chat_model": await resolve_chat_model(db),
        "default_embed_model": await resolve_embed_model(db),
        "available_models": worker.get("models", []),
        "worker": worker,
        "note": "Live model list is pushed over WebSocket type=models_list",
    }


@router.get("/audit-logs")
async def list_audit_logs(
    _: AdminUser,
    db: DbDep,
    action: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)
    if action and action.strip():
        cleaned = action.strip()
        stmt = stmt.where(AuditLog.action.ilike(f"%{cleaned}%"))
        count_stmt = count_stmt.where(AuditLog.action.ilike(f"%{cleaned}%"))

    total = await db.scalar(count_stmt) or 0
    rows = (
        await db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit))
    ).all()
    return {
        "total": total,
        "items": [
            {
                "id": str(row.id),
                "actor_id": str(row.actor_id) if row.actor_id else None,
                "action": row.action,
                "detail": row.detail or {},
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.post("/maintenance/prune")
async def run_maintenance_prune(admin: AdminUser, db: DbDep) -> dict:
    summary = await prune_stale_records(db)
    await write_audit(db, "maintenance_prune", actor_id=admin.id, detail=summary)
    return summary
