import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global redis_client
    try:
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        logger.info("Connected to Redis successfully.")
    except Exception as e:
        logger.warning(f"Failed to connect to Redis at {settings.REDIS_URL}: {e}")
        # In case Redis is unavailable, fallback gracefully where appropriate
        redis_client = None
    return redis_client  # type: ignore


async def get_redis() -> aioredis.Redis | None:
    global redis_client
    if redis_client is None:
        try:
            await init_redis()
        except Exception:
            pass
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None
