"""FastAPI dependencies."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.entities import User, UserRole

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    db: DbDep,
    access_token: Annotated[str | None, Cookie()] = None,
) -> User:
    auth = request.headers.get("Authorization")
    token = None
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    elif access_token:
        token = access_token
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
        jti = payload.get("jti")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    if jti:
        from app.db.redis import is_jti_blacklisted

        if await is_jti_blacklisted(str(jti)):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    if user.role == UserRole.pending:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pending approval")
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
