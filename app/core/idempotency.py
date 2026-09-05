import hashlib
import json
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_ops import IdempotencyKey

_in_memory_idempotency_store: dict[str, dict[str, Any]] = {}


def hash_request_body(body_data: Any) -> str:
    """Computes SHA-256 hash of JSON-serializable request payload."""
    serialized = json.dumps(body_data, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def get_idempotent_response(
    redis: aioredis.Redis | None,
    session: AsyncSession,
    application_id: str,
    idempotency_key: str,
    endpoint: str,
) -> dict[str, Any] | None:
    """
    Checks if an idempotency key has already been processed.
    Returns stored response dict if found, otherwise None.
    """
    cache_key = f"idempotency:{application_id}:{idempotency_key}"

    if redis is not None:
        try:
            cached_json = await redis.get(cache_key)
            if cached_json:
                return json.loads(cached_json)
        except Exception:
            pass

    if cache_key in _in_memory_idempotency_store:
        return _in_memory_idempotency_store[cache_key]

    # Database fallback
    stmt = select(IdempotencyKey).where(
        IdempotencyKey.application_id == application_id,
        IdempotencyKey.idempotency_key == idempotency_key,
        IdempotencyKey.endpoint == endpoint,
    )
    result = (await session.execute(stmt)).scalar_one_or_none()
    if result and result.response_body:
        return result.response_body

    return None


async def save_idempotent_response(
    redis: aioredis.Redis | None,
    session: AsyncSession,
    application_id: str,
    customer_id: str,
    idempotency_key: str,
    endpoint: str,
    request_body: Any,
    response_body: dict[str, Any],
    status_code: int = 200,
    ttl_seconds: int = 86400,
) -> None:
    """Saves idempotent response to Redis and database for future duplicate requests."""
    cache_key = f"idempotency:{application_id}:{idempotency_key}"
    req_hash = hash_request_body(request_body)

    if redis is not None:
        try:
            await redis.set(cache_key, json.dumps(response_body), ex=ttl_seconds)
        except Exception:
            pass

    _in_memory_idempotency_store[cache_key] = response_body

    # Save to database
    record = IdempotencyKey(
        customer_id=customer_id,
        application_id=application_id,
        idempotency_key=idempotency_key,
        endpoint=endpoint,
        request_hash=req_hash,
        response_status=status_code,
        response_body=response_body,
    )
    session.add(record)
    await session.flush()
