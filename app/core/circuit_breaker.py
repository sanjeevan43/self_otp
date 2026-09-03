import time

import redis.asyncio as aioredis


class CircuitBreakerOpenException(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        name: str = "meta_api",
        failure_threshold: float = 0.20,  # 20% failure rate
        window_seconds: int = 60,
        recovery_seconds: int = 30,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.recovery_seconds = recovery_seconds
        self.state_key = f"circuit_breaker:{name}:state"
        self.success_key = f"circuit_breaker:{name}:success"
        self.failure_key = f"circuit_breaker:{name}:failure"

        # Local fallback state if Redis is offline
        self._local_successes = 0
        self._local_failures = 0
        self._local_state = "CLOSED"
        self._local_opened_at = 0.0

    async def is_open(self, redis: aioredis.Redis | None = None) -> bool:
        now = time.time()
        if redis is not None:
            try:
                state = await redis.get(self.state_key)
                if state == "OPEN":
                    return True
                return False
            except Exception:
                pass

        if self._local_state == "OPEN":
            if now - self._local_opened_at > self.recovery_seconds:
                self._local_state = "HALF_OPEN"
                return False
            return True
        return False

    async def record_result(self, success: bool, redis: aioredis.Redis | None = None) -> None:
        now = time.time()
        if redis is not None:
            try:
                key = self.success_key if success else self.failure_key
                pipe = redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, self.window_seconds)
                results = await pipe.execute()

                successes = int(await redis.get(self.success_key) or 0)
                failures = int(await redis.get(self.failure_key) or 0)
                total = successes + failures

                if total >= 10:
                    failure_rate = failures / total
                    if failure_rate >= self.failure_threshold:
                        await redis.set(self.state_key, "OPEN", ex=self.recovery_seconds)
                return
            except Exception:
                pass

        if success:
            self._local_successes += 1
        else:
            self._local_failures += 1

        total = self._local_successes + self._local_failures
        if total >= 10 and (self._local_failures / total) >= self.failure_threshold:
            self._local_state = "OPEN"
            self._local_opened_at = now
