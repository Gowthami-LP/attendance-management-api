import asyncio

from redis.exceptions import RedisError

from app.database.redis_client import check_redis_connection, close_redis_connection


async def main() -> int:
    try:
        if await check_redis_connection():
            print("Redis connection successful; server responded to PING.")
            return 0
        print("Redis connection failed; server did not respond to PING.")
        return 1
    except (RedisError, OSError) as error:
        print(f"Redis connection failed: {error}")
        return 1
    finally:
        await close_redis_connection()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
