import time

import redis.asyncio as aioredis

# In-memory storage fallback if Redis is disabled or unavailable during tests
_in_memory_rate_limits: dict[str, list[float]] = {}


async def is_rate_limited(
    redis: aioredis.Redis | None,
    key: str,
    max_requests: int,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    """
    Sliding window log rate limiter.
    Returns: (is_limited: bool, remaining_requests: int)
    """
    now = time.time()
    clear_before = now - window_seconds

    if redis is not None:
        try:
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, clear_before)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds + 5)
            results = await pipe.execute()
            current_count = results[2]

            remaining = max(0, max_requests - current_count)
            if current_count > max_requests:
                return True, 0
            return False, remaining
        except Exception:
            pass

    # In-memory fallback
    timestamps = _in_memory_rate_limits.get(key, [])
    timestamps = [t for t in timestamps if t > clear_before]
    timestamps.append(now)
    _in_memory_rate_limits[key] = timestamps

    current_count = len(timestamps)
    remaining = max(0, max_requests - current_count)
    if current_count > max_requests:
        return True, 0
    return False, remaining
