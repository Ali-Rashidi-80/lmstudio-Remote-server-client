"""Password hashing and JWT helpers."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(user_id: str, role: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": _now() + timedelta(minutes=settings.JWT_ACCESS_MINUTES),
        "iat": _now(),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    settings = get_settings()
    jti = str(uuid.uuid4())
    exp = _now() + timedelta(days=settings.JWT_REFRESH_DAYS)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": exp,
        "iat": _now(),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    return token, jti, exp


def create_ws_ticket(user_id: str, role: str) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "role": role,
        "type": "ws",
        "exp": _now() + timedelta(seconds=settings.WS_TICKET_SECONDS),
        "iat": _now(),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    if expected_type and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def new_invite_token() -> str:
    return secrets.token_urlsafe(32)
