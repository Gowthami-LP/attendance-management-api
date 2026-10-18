import logging
import os

import redis
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("redis_client")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create a connection pool and Redis client instance
redis_pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)
redis_client = redis.Redis(connection_pool=redis_pool)


def ping_redis() -> bool:
    """Verifies that Redis is reachable and responding to PING."""
    try:
        return bool(redis_client.ping())
    except redis.RedisError as err:
        logger.warning("Redis ping failed: %s", err)
        return False
