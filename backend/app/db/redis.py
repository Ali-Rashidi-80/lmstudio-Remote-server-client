"""Redis client helpers."""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import get_settings

_redis: Redis | None = None


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


async def redis_ping() -> bool:
    try:
        r = await get_redis()
        return bool(await r.ping())
    except Exception:
        return False
