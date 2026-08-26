"""Redis sliding-window style rate limit for login."""

from __future__ import annotations

from app.db.redis import get_redis


async def check_login_rate(ip: str, limit: int = 10, window: int = 300) -> bool:
    """Return True if allowed, False if rate-limited."""
    r = await get_redis()
    key = f"login_rl:{ip}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window)
    return count <= limit
