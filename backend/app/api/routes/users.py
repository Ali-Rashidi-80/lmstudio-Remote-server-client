from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import AdminUser, DbDep
from app.core.config import get_settings
from app.core.security import hash_password, new_invite_token
from app.models.entities import Invite, User, UserRole
from app.schemas.auth import UserOut
from app.services.audit import write_audit

router = APIRouter(prefix="/api/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10)
    email: str | None = None
    role: str = "user"


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


class InviteCreate(BaseModel):
    email: str | None = None
    role: str = "user"


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
async def create_user(body: CreateUserRequest, admin: AdminUser, db: DbDep) -> UserOut:
    if await db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status_code=400, detail="Username taken")
    role = UserRole(body.role)
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await write_audit(db, "user_create", actor_id=admin.id, detail={"user": body.username})
    return _out(user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str, body: UpdateUserRequest, admin: AdminUser, db: DbDep
) -> UserOut:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    if body.role is not None:
        user.role = UserRole(body.role)
    if body.is_active is not None:
        user.is_active = body.is_active
    await db.commit()
    await db.refresh(user)
    await write_audit(
        db,
        "user_update",
        actor_id=admin.id,
        detail={"user_id": user_id, "role": body.role, "is_active": body.is_active},
    )
    return _out(user)


@router.post("/invites")
async def create_invite(body: InviteCreate, admin: AdminUser, db: DbDep) -> dict:
    settings = get_settings()
    token = new_invite_token()
    invite = Invite(
        token=token,
        email=body.email,
        role=UserRole(body.role),
        created_by=admin.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.INVITE_DAYS),
    )
    db.add(invite)
    await db.commit()
    await write_audit(db, "invite_create", actor_id=admin.id, detail={"email": body.email})
    return {
        "token": token,
        "expires_at": invite.expires_at.isoformat(),
        "accept_path": f"/accept-invite?token={token}",
    }


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
            "token": i.token if i.used_at is None else None,
        }
        for i in rows
    ]
