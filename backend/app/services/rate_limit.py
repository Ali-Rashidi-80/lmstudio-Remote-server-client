"""Redis rate limiting helpers."""

from __future__ import annotations

from app.core.config import get_settings
from app.db.redis import get_redis


async def check_rate_limit(scope: str, key_id: str, limit: int, window: int) -> bool:
    """Return True if allowed, False if rate-limited."""
    r = await get_redis()
    key = f"rl:{scope}:{key_id}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, window)
    else:
        ttl = await r.ttl(key)
        if ttl == -1:
            await r.expire(key, window)
    return count <= limit


async def check_login_rate(ip: str, limit: int | None = None, window: int | None = None) -> bool:
    """Return True if login attempt is allowed, False if rate-limited."""
    settings = get_settings()
    eff_limit = limit if limit is not None else settings.LOGIN_RATE_LIMIT
    eff_window = window if window is not None else settings.LOGIN_RATE_WINDOW_SEC
    r = await get_redis()
    key = f"login_rl:{ip}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, eff_window)
    else:
        ttl = await r.ttl(key)
        if ttl == -1:
            await r.expire(key, eff_window)
    return count <= eff_limit
