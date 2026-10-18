import json
from typing import Any

from app.database.redis_client import redis_client


async def get_cached_data(key: str) -> Any | None:
    """Return cached JSON data, or None when it is missing or invalid."""
    cached_value = await redis_client.get(key)
    if cached_value is None:
        return None
    try:
        return json.loads(cached_value)
    except (json.JSONDecodeError, TypeError):
        await redis_client.delete(key)
        return None


async def set_cached_data(key: str, value: Any, ttl_seconds: int = 60) -> None:
    """Store JSON-compatible data with an expiry."""
    await redis_client.set(key, json.dumps(value, default=str), ex=ttl_seconds)


async def invalidate_cache(key: str) -> None:
    """Delete one cached value."""
    await redis_client.delete(key)


async def invalidate_tenant_reports(tenant_id: str) -> None:
    """Delete report cache entries for one tenant after attendance changes."""
    prefix = f"attendance:{tenant_id}:report:"
    keys = [key async for key in redis_client.scan_iter(match=f"{prefix}*")]
    if keys:
        await redis_client.delete(*keys)
