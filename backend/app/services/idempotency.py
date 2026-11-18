"""Redis-backed Idempotency-Key protection for mutating endpoints."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from fastapi import HTTPException

from app.db.redis import get_redis

logger = logging.getLogger("idempotency")

IDEM_KEY_RE = re.compile(r"^[a-zA-Z0-9._:-]{1,128}$")
IDEM_PENDING_TTL_SEC = 120
IDEM_DONE_TTL_SEC = 86400


def validate_idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if not IDEM_KEY_RE.match(cleaned):
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key header")
    return cleaned


def hash_payload(data: Any) -> str:
    if isinstance(data, bytes):
        raw = data
    else:
        raw = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _redis_key(scope: str, actor: str, key: str) -> str:
    return f"idem:{scope}:{actor}:{key}"


async def begin_idempotency(
    scope: str, actor: str, key: str | None, payload_hash: str
) -> tuple[bool, Any | None]:
    """
    Acquire idempotency slot.

    Returns (replayed, cached_body).
    Raises 409 if the same key is concurrently in-flight or bound to a different payload.
    """
    if not key:
        return False, None
    r = await get_redis()
    rkey = _redis_key(scope, actor, key)
    pending = json.dumps({"state": "pending", "hash": payload_hash})
    acquired = await r.set(rkey, pending, ex=IDEM_PENDING_TTL_SEC, nx=True)
    if acquired:
        return False, None

    raw = await r.get(rkey)
    if not raw:
        acquired = await r.set(rkey, pending, ex=IDEM_PENDING_TTL_SEC, nx=True)
        if acquired:
            return False, None
        raise HTTPException(status_code=409, detail="Request with this Idempotency-Key in progress")

    try:
        record = json.loads(raw)
    except Exception:
        return False, None

    if record.get("hash") != payload_hash:
        raise HTTPException(
            status_code=409, detail="Idempotency-Key already used with a different payload"
        )
    if record.get("state") == "pending":
        raise HTTPException(status_code=409, detail="Request with this Idempotency-Key in progress")
    return True, record.get("body")


async def complete_idempotency(
    scope: str, actor: str, key: str | None, payload_hash: str, body: Any
) -> None:
    if not key:
        return
    try:
        r = await get_redis()
        rkey = _redis_key(scope, actor, key)
        record = json.dumps({"state": "done", "hash": payload_hash, "body": body}, default=str)
        await r.setex(rkey, IDEM_DONE_TTL_SEC, record)
    except Exception as exc:
        logger.warning("Failed to save idempotency result for %s: %s", scope, exc)


async def abort_idempotency(scope: str, actor: str, key: str | None) -> None:
    if not key:
        return
    try:
        r = await get_redis()
        await r.delete(_redis_key(scope, actor, key))
    except Exception as exc:
        logger.warning("Failed to clear idempotency key for %s: %s", scope, exc)
