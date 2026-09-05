from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import is_rate_limited
from app.core.security import decode_token, hash_api_key
from app.database import get_db
from app.models.api_key import APIKey
from app.models.customer import Customer, CustomerUser
from app.models.enums import APIKeyStatus, CustomerStatus, UserStatus
from app.models.user import User
from app.redis import get_redis

security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[User, Customer]:
    """Validates JWT access token and returns authenticated (User, Customer) tuple."""
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHORIZED", "message": "Invalid token type."},
            )
        user_id: str = payload.get("sub")  # type: ignore
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "UNAUTHORIZED", "message": "Invalid token payload."},
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Could not validate credentials."},
        )

    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "User not found or inactive."},
        )

    # Fetch Customer link
    cu_stmt = (
        select(Customer)
        .join(CustomerUser, Customer.id == CustomerUser.customer_id)
        .where(CustomerUser.user_id == user.id)
    )
    customer = (await db.execute(cu_stmt)).scalar_one_or_none()
    if not customer or customer.status != CustomerStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Customer account is suspended or inactive."},
        )

    return user, customer


from app.models.application import Application

async def get_api_key_context(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis | None = Depends(get_redis),
) -> tuple[APIKey, Application, Customer]:
    """
    Validates X-API-Key header, checks status, rate limits,
    and returns (APIKey, Application, Customer) tuple to guarantee tenant isolation.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHORIZED",
                "message": "API key required in 'X-API-Key' header.",
            },
        )

    key_hash = hash_api_key(x_api_key)

    stmt = (
        select(APIKey, Application, Customer)
        .join(Application, APIKey.application_id == Application.id)
        .join(Customer, APIKey.customer_id == Customer.id)
        .where(APIKey.key_hash == key_hash, APIKey.status == APIKeyStatus.ACTIVE)
    )
    result = await db.execute(stmt)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or revoked API key."},
        )

    api_key, application, customer = row

    if customer.status != CustomerStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Customer account is suspended or disabled."},
        )

    # Check API key rate limit (60 req/min default)
    limited, _ = await is_rate_limited(
        redis=redis,
        key=f"ratelimit:apikey:{api_key.id}",
        max_requests=60,
        window_seconds=60,
    )
    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "API key rate limit exceeded.",
            },
        )

    return api_key, application, customer
