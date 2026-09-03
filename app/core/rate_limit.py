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


# In-memory storage for temporary blocks when Redis is unavailable
_in_memory_blocked_phones: dict[str, float] = {}
_in_memory_blocked_customers: dict[str, float] = {}


async def block_phone_number(
    redis: aioredis.Redis | None,
    phone_hash: str,
    duration_seconds: int = 3600,
) -> None:
    """Temporarily blocks a phone number due to excessive failures or abuse."""
    key = f"phone:blocked:{phone_hash}"
    if redis is not None:
        try:
            await redis.set(key, "1", ex=duration_seconds)
            return
        except Exception:
            pass
    _in_memory_blocked_phones[phone_hash] = time.time() + duration_seconds


async def is_phone_blocked(
    redis: aioredis.Redis | None,
    phone_hash: str,
) -> bool:
    """Checks if a phone number is currently temporarily blocked."""
    key = f"phone:blocked:{phone_hash}"
    if redis is not None:
        try:
            exists = await redis.get(key)
            return bool(exists)
        except Exception:
            pass
    unblock_time = _in_memory_blocked_phones.get(phone_hash, 0.0)
    return time.time() < unblock_time


async def block_customer(
    redis: aioredis.Redis | None,
    customer_id: str,
    duration_seconds: int = 86400,
) -> None:
    """Temporarily blocks a customer account due to severe abuse detection."""
    key = f"customer:blocked:{customer_id}"
    if redis is not None:
        try:
            await redis.set(key, "1", ex=duration_seconds)
            return
        except Exception:
            pass
    _in_memory_blocked_customers[customer_id] = time.time() + duration_seconds


async def is_customer_blocked(
    redis: aioredis.Redis | None,
    customer_id: str,
) -> bool:
    """Checks if a customer account is currently blocked for abuse."""
    key = f"customer:blocked:{customer_id}"
    if redis is not None:
        try:
            exists = await redis.get(key)
            return bool(exists)
        except Exception:
            pass
    unblock_time = _in_memory_blocked_customers.get(customer_id, 0.0)
    return time.time() < unblock_time

