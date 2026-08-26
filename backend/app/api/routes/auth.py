from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_ws_ticket,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.entities import Invite, RefreshToken, User, UserRole
from app.schemas.auth import (
    AcceptInviteRequest,
    ChangePasswordRequest,
    LoginRequest,
    TokenResponse,
    UserOut,
)
from app.services.audit import write_audit
from app.services.rate_limit import check_login_rate

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
    )


def _set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    settings = get_settings()
    response.set_cookie(
        "access_token",
        access,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_ACCESS_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_REFRESH_DAYS * 86400,
        path="/",
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, response: Response, db: DbDep
) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    if not await check_login_rate(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")
    user = await db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        await write_audit(db, "login_failed", detail={"username": body.username, "ip": ip})
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active or user.role == UserRole.pending:
        raise HTTPException(status_code=403, detail="Account not active")
    access = create_access_token(str(user.id), user.role.value)
    refresh, jti, exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp))
    await db.commit()
    _set_auth_cookies(response, access, refresh)
    await write_audit(db, "login_ok", actor_id=user.id, detail={"ip": ip})
    return TokenResponse(access_token=access, user=_user_out(user))


@router.post("/logout")
async def logout(response: Response, db: DbDep, user: CurrentUser, request: Request) -> dict:
    from app.db.redis import blacklist_jti

    access = request.cookies.get("access_token")
    if access:
        try:
            ap = decode_token(access, expected_type="access")
            jti = ap.get("jti")
            exp = ap.get("exp")
            if jti and exp:
                ttl = max(int(exp - datetime.now(UTC).timestamp()), 1)
                await blacklist_jti(str(jti), ttl)
        except Exception:
            pass
    refresh = request.cookies.get("refresh_token")
    if refresh:
        try:
            payload = decode_token(refresh, expected_type="refresh")
            row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
            if row:
                row.revoked = True
                await db.commit()
        except Exception:
            pass
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    await write_audit(db, "logout", actor_id=user.id)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(db: DbDep, user: CurrentUser, response: Response) -> dict:
    rows = await db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id))
    for row in rows:
        row.revoked = True
    await db.commit()
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: DbDep) -> TokenResponse:
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = decode_token(token, expected_type="refresh")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh") from exc
    row = await db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    if not row or row.revoked:
        raise HTTPException(status_code=401, detail="Refresh revoked")
    user = await db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User inactive")
    access = create_access_token(str(user.id), user.role.value)
    new_refresh, jti, exp = create_refresh_token(str(user.id))
    row.revoked = True
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp))
    await db.commit()
    _set_auth_cookies(response, access, new_refresh)
    return TokenResponse(access_token=access, user=_user_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return _user_out(user)


@router.post("/ws-ticket")
async def ws_ticket(user: CurrentUser) -> dict:
    return {"ticket": create_ws_ticket(str(user.id), user.role.value)}


@router.post("/accept-invite", response_model=TokenResponse)
async def accept_invite(body: AcceptInviteRequest, response: Response, db: DbDep) -> TokenResponse:
    invite = await db.scalar(select(Invite).where(Invite.token == body.token))
    if not invite or invite.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid invite")
    if invite.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Invite expired")
    exists = await db.scalar(select(User).where(User.username == body.username))
    if exists:
        raise HTTPException(status_code=400, detail="Username taken")
    user = User(
        username=body.username,
        email=body.email or invite.email,
        password_hash=hash_password(body.password),
        role=invite.role if invite.role != UserRole.pending else UserRole.user,
        is_active=True,
    )
    db.add(user)
    invite.used_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)
    access = create_access_token(str(user.id), user.role.value)
    refresh, jti, exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp))
    await db.commit()
    _set_auth_cookies(response, access, refresh)
    return TokenResponse(access_token=access, user=_user_out(user))


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, db: DbDep, user: CurrentUser) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    await write_audit(db, "change_password", actor_id=user.id)
    return {"ok": True}


@router.post("/register")
async def register_disabled() -> None:
    raise HTTPException(status_code=403, detail="Open registration disabled; use invite")
