from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, update

from app.api.deps import AdminUser, DbDep
from app.core.config import get_settings
from app.core.security import hash_password, new_invite_token
from app.models.entities import Invite, RefreshToken, User, UserRole
from app.schemas.auth import UserOut, _blank_email_to_none
from app.services.audit import write_audit
from app.services.idempotency import (
    abort_idempotency,
    begin_idempotency,
    complete_idempotency,
    hash_payload,
    validate_idempotency_key,
)

router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    email: EmailStr | None = None
    role: UserRole = UserRole.user

    _normalize_email = field_validator("email", mode="before")(_blank_email_to_none)


class UpdateUserRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class InviteCreate(BaseModel):
    email: EmailStr | None = None
    role: UserRole = UserRole.user

    _normalize_email = field_validator("email", mode="before")(_blank_email_to_none)


def _out(u: User) -> UserOut:
    return UserOut(
        id=str(u.id),
        username=u.username,
        email=u.email,
        role=u.role.value,
        is_active=u.is_active,
    )


@router.get("", response_model=list[UserOut])
async def list_users(_: AdminUser, db: DbDep) -> list[UserOut]:
    rows = await db.scalars(select(User).order_by(User.created_at.desc()))
    return [_out(u) for u in rows]


@router.post("", response_model=UserOut)
async def create_user(
    body: CreateUserRequest,
    admin: AdminUser,
    db: DbDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> UserOut:
    idem_key = validate_idempotency_key(idempotency_key)
    p_hash = hash_payload({"username": body.username, "email": body.email, "role": body.role.value})
    replayed, cached = await begin_idempotency("users_create", str(admin.id), idem_key, p_hash)
    if replayed and cached is not None:
        return UserOut(**cached)

    try:
        if await db.scalar(select(User).where(User.username == body.username)):
            raise HTTPException(status_code=400, detail="Username taken")
        if body.email and await db.scalar(select(User).where(User.email == str(body.email))):
            raise HTTPException(status_code=400, detail="Email already in use")
        user = User(
            username=body.username,
            email=str(body.email) if body.email else None,
            password_hash=hash_password(body.password),
            role=body.role,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        await write_audit(
            db,
            "user_create",
            actor_id=admin.id,
            detail={"user": body.username, "role": body.role.value},
        )
        out = _out(user)
        await complete_idempotency(
            "users_create", str(admin.id), idem_key, p_hash, out.model_dump()
        )
        return out
    except Exception:
        await abort_idempotency("users_create", str(admin.id), idem_key)
        raise


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID, body: UpdateUserRequest, admin: AdminUser, db: DbDep
) -> UserOut:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    if user.id == admin.id:
        if body.is_active is False:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")
        if body.role is not None and body.role != UserRole.admin:
            raise HTTPException(status_code=400, detail="Cannot demote your own admin role")
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
                .values(revoked=True)
            )
    await db.commit()
    await db.refresh(user)
    await write_audit(
        db,
        "user_update",
        actor_id=admin.id,
        detail={
            "user_id": str(user_id),
            "role": body.role.value if body.role else None,
            "is_active": body.is_active,
        },
    )
    return _out(user)


@router.post("/invites")
async def create_invite(
    body: InviteCreate,
    admin: AdminUser,
    db: DbDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    idem_key = validate_idempotency_key(idempotency_key)
    p_hash = hash_payload({"email": body.email, "role": body.role.value})
    replayed, cached = await begin_idempotency("invites_create", str(admin.id), idem_key, p_hash)
    if replayed and cached is not None:
        return cached

    try:
        settings = get_settings()
        token = new_invite_token()
        invite = Invite(
            token=token,
            email=str(body.email) if body.email else None,
            role=body.role,
            created_by=admin.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.INVITE_DAYS),
        )
        db.add(invite)
        await db.commit()
        await db.refresh(invite)
        await write_audit(
            db,
            "invite_create",
            actor_id=admin.id,
            detail={"email": str(body.email) if body.email else None, "role": body.role.value},
        )
        res = {
            "id": str(invite.id),
            "token": token,
            "role": invite.role.value,
            "email": invite.email,
            "expires_at": invite.expires_at.isoformat(),
            "accept_path": f"/accept-invite?token={token}",
        }
        await complete_idempotency("invites_create", str(admin.id), idem_key, p_hash, res)
        return res
    except Exception:
        await abort_idempotency("invites_create", str(admin.id), idem_key)
        raise


@router.get("/invites")
async def list_invites(_: AdminUser, db: DbDep) -> list[dict]:
    rows = await db.scalars(select(Invite).order_by(Invite.created_at.desc()))
    return [
        {
            "id": str(i.id),
            "email": i.email,
            "role": i.role.value,
            "expires_at": i.expires_at.isoformat(),
            "used_at": i.used_at.isoformat() if i.used_at else None,
            "created_at": i.created_at.isoformat(),
            "token": i.token if i.used_at is None else None,
        }
        for i in rows
    ]


@router.delete("/invites/{invite_id}")
async def revoke_invite(invite_id: uuid.UUID, admin: AdminUser, db: DbDep) -> dict:
    invite = await db.get(Invite, invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.used_at is not None:
        raise HTTPException(status_code=400, detail="Used invites cannot be revoked")
    await db.delete(invite)
    await db.commit()
    await write_audit(
        db,
        "invite_revoke",
        actor_id=admin.id,
        detail={"invite_id": str(invite_id), "email": invite.email},
    )
    return {"ok": True}
