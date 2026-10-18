from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from redis.exceptions import RedisError

from app.database.redis_client import check_redis_connection
from app.services.cache_service import get_cached_data, set_cached_data

router = APIRouter()


class RedisDemoValue(BaseModel):
    value: Any


@router.get(
    "/health/redis",
    tags=["Redis"],
    summary="Check Redis connection",
    description="Sends a PING command to Redis and reports whether the cache is reachable.",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Redis is unavailable",
            "content": {
                "application/json": {
                    "example": {"status": "unhealthy", "redis": "disconnected"}
                }
            },
        }
    },
)
async def redis_health_check(response: Response) -> dict[str, str]:
    """Check whether the Redis server is responding."""
    try:
        if await check_redis_connection():
            return {"status": "healthy", "redis": "connected"}
    except (RedisError, OSError):
        pass

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "unhealthy", "redis": "disconnected"}


@router.put(
    "/health/redis/demo",
    tags=["Redis"],
    summary="Store a demo value in Redis",
)
async def store_redis_demo_value(payload: RedisDemoValue) -> dict[str, str]:
    """Store a JSON value under a fixed demo key for Redis read testing."""
    try:
        await set_cached_data("redis:demo", payload.value, ttl_seconds=3600)
    except RedisError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is unavailable",
        ) from error
    return {"status": "stored", "key": "redis:demo", "expires_in_seconds": "3600"}


@router.get(
    "/health/redis/demo",
    tags=["Redis"],
    summary="Fetch the demo value from Redis",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "No demo value has been stored"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Redis is unavailable"},
    },
)
async def fetch_redis_demo_value() -> dict[str, Any]:
    """Read the fixed demo key from Redis."""
    try:
        value = await get_cached_data("redis:demo")
    except RedisError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is unavailable",
        ) from error
    if value is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No demo value stored. PUT a value to /health/redis/demo first.",
        )
    return {"key": "redis:demo", "value": value, "source": "redis"}
