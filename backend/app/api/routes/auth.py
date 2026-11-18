from __future__ import annotations

import logging
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select, update

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
from app.db.redis import blacklist_jti
from app.models.entities import Invite, RefreshToken, User, UserRole
from app.schemas.auth import (
    AcceptInviteRequest,
    ChangePasswordRequest,
    LoginRequest,
    TokenResponse,
    UserOut,
)
from app.services.audit import write_audit
from app.services.rate_limit import check_login_rate, check_rate_limit

logger = logging.getLogger("auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.TRUST_PROXY_HEADERS:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _extract_access_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.cookies.get("access_token")


async def _blacklist_access_from_request(request: Request) -> None:
    access = _extract_access_token(request)
    if not access:
        return
    try:
        ap = decode_token(access, expected_type="access")
        jti = ap.get("jti")
        exp = ap.get("exp")
        if jti and exp:
            ttl = max(int(exp - datetime.now(UTC).timestamp()), 1)
            await blacklist_jti(str(jti), ttl)
    except jwt.PyJWTError as exc:
        logger.debug("Ignoring invalid access token during logout: %s", exc)
    except Exception as exc:
        logger.warning("Failed to blacklist access token jti: %s", exc)


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
    )


def _set_auth_cookies(response: Response, access: str, refresh_tok: str) -> None:
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
        refresh_tok,
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
    ip = _client_ip(request)
    if not await check_login_rate(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")
    user = await db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.password_hash):
        await write_audit(db, "login_failed", detail={"username": body.username, "ip": ip})
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active or user.role == UserRole.pending:
        raise HTTPException(status_code=403, detail="Account not active")
    access = create_access_token(str(user.id), user.role.value)
    refresh_tok, jti, exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp))
    await db.commit()
    _set_auth_cookies(response, access, refresh_tok)
    await write_audit(db, "login_ok", actor_id=user.id, detail={"ip": ip})
    return TokenResponse(access_token=access, user=_user_out(user))


@router.post("/logout")
async def logout(response: Response, db: DbDep, user: CurrentUser, request: Request) -> dict:
    await _blacklist_access_from_request(request)
    refresh_cookie = request.cookies.get("refresh_token")
    if refresh_cookie:
        try:
            payload = decode_token(refresh_cookie, expected_type="refresh")
            row = await db.scalar(
                select(RefreshToken).where(RefreshToken.jti == payload["jti"]).with_for_update()
            )
            if row and not row.revoked:
                row.revoked = True
                await db.commit()
        except jwt.PyJWTError as exc:
            logger.debug("Ignoring invalid refresh cookie on logout: %s", exc)
        except Exception as exc:
            logger.warning("Failed to revoke refresh token on logout: %s", exc)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    await write_audit(db, "logout", actor_id=user.id)
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(db: DbDep, user: CurrentUser, request: Request, response: Response) -> dict:
    await _blacklist_access_from_request(request)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    await db.commit()
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    await write_audit(db, "logout_all", actor_id=user.id)
    return {"ok": True}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: DbDep) -> TokenResponse:
    settings = get_settings()
    ip = _client_ip(request)
    if not await check_rate_limit(
        "auth_refresh", ip, settings.AUTH_MUTATION_RATE_LIMIT, settings.AUTH_MUTATION_WINDOW_SEC
    ):
        raise HTTPException(status_code=429, detail="Too many refresh attempts")
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = decode_token(token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh") from exc
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.jti == payload["jti"]).with_for_update()
    )
    if not row or row.revoked or row.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Refresh revoked or expired")
    user = await db.get(User, row.user_id)
    if not user or not user.is_active or user.role == UserRole.pending:
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
async def accept_invite(
    body: AcceptInviteRequest, request: Request, response: Response, db: DbDep
) -> TokenResponse:
    settings = get_settings()
    ip = _client_ip(request)
    if not await check_rate_limit(
        "accept_invite", ip, settings.AUTH_MUTATION_RATE_LIMIT, settings.AUTH_MUTATION_WINDOW_SEC
    ):
        raise HTTPException(status_code=429, detail="Too many invite attempts")

    invite = await db.scalar(select(Invite).where(Invite.token == body.token).with_for_update())
    if not invite or invite.used_at is not None:
        raise HTTPException(status_code=400, detail="Invalid invite")
    if invite.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Invite expired")

    username_exists = await db.scalar(select(User).where(User.username == body.username))
    if username_exists:
        raise HTTPException(status_code=400, detail="Username taken")

    target_email = str(body.email) if body.email else invite.email
    if target_email:
        email_exists = await db.scalar(select(User).where(User.email == target_email))
        if email_exists:
            raise HTTPException(status_code=400, detail="Email already in use")

    user = User(
        username=body.username,
        email=target_email,
        password_hash=hash_password(body.password),
        role=invite.role if invite.role != UserRole.pending else UserRole.user,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    invite.used_at = datetime.now(UTC)
    access = create_access_token(str(user.id), user.role.value)
    refresh_tok, jti, exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp))
    await write_audit(
        db,
        "invite_accept",
        actor_id=user.id,
        detail={"username": user.username, "ip": ip},
    )
    _set_auth_cookies(response, access, refresh_tok)
    return TokenResponse(access_token=access, user=_user_out(user))


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest, response: Response, db: DbDep, user: CurrentUser
) -> dict:
    if not await check_rate_limit("change_pw", str(user.id), 10, 300):
        raise HTTPException(status_code=429, detail="Too many password change attempts")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    user.password_hash = hash_password(body.new_password)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False))
        .values(revoked=True)
    )
    access = create_access_token(str(user.id), user.role.value)
    refresh_tok, jti, exp = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=exp))
    await write_audit(db, "change_password", actor_id=user.id)
    _set_auth_cookies(response, access, refresh_tok)
    return {"ok": True}


@router.post("/register")
async def register_disabled() -> None:
    raise HTTPException(status_code=403, detail="Open registration disabled; use invite")
