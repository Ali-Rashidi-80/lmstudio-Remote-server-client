"""Redis client helpers, JWT blacklisting, single-use WS tickets, and worker state."""

from __future__ import annotations

import json
import logging
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger("redis")

_redis: Redis | None = None
WORKER_STATE_KEY = "aiws:worker:state"


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        close = getattr(_redis, "aclose", None) or _redis.close
        await close()
        _redis = None


async def blacklist_jti(jti: str, ttl_seconds: int) -> None:
    """Mark an access-token jti revoked until natural expiry."""
    if ttl_seconds <= 0:
        return
    r = await get_redis()
    await r.setex(f"jwt_bl:{jti}", ttl_seconds, "1")


async def is_jti_blacklisted(jti: str) -> bool:
    r = await get_redis()
    return bool(await r.exists(f"jwt_bl:{jti}"))


async def consume_ws_ticket(jti: str, ttl_seconds: int) -> bool:
    """Atomically mark a WS ticket as consumed. Returns True only on first use."""
    if not jti:
        return False
    try:
        r = await get_redis()
        ok = await r.set(f"ws_ticket:{jti}", "1", ex=max(ttl_seconds, 1), nx=True)
        return bool(ok)
    except Exception as exc:
        logger.warning("Failed to consume WS ticket %s: %s", jti, exc)
        return False


async def set_worker_state(
    online: bool,
    hw: str,
    models: list[dict[str, Any]] | None = None,
    ttl_seconds: int | None = None,
) -> None:
    """Persist shared worker presence and loaded models in Redis for multi-process consumers."""
    settings = get_settings()
    ttl = ttl_seconds or settings.WORKER_HEARTBEAT_TTL_SEC
    try:
        r = await get_redis()
        payload = {
            "worker_online": bool(online),
            "hw": hw or "CPU",
            "models": models if models is not None else [],
        }
        await r.setex(WORKER_STATE_KEY, max(ttl, 10), json.dumps(payload))
    except Exception as exc:
        logger.warning("Failed to persist worker state in Redis: %s", exc)


async def get_worker_state() -> dict[str, Any] | None:
    """Read shared worker state from Redis if present."""
    try:
        r = await get_redis()
        raw = await r.get(WORKER_STATE_KEY)
        if not raw:
            return None
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:
        logger.warning("Failed to read worker state from Redis: %s", exc)
        return None


async def redis_ping() -> bool:
    try:
        r = await get_redis()
        return bool(await r.ping())
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc)
        return False
