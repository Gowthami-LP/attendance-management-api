import os

from redis.asyncio import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# One reusable asynchronous client per application process.
redis_client = Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
    health_check_interval=30,
)


async def check_redis_connection() -> bool:
    """Check whether Redis is responding."""
    return bool(await redis_client.ping())


async def close_redis_connection() -> None:
    """Close the Redis client during application shutdown."""
    await redis_client.aclose()
