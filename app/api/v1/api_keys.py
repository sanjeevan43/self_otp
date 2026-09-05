from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import generate_api_key
from app.database import get_db
from app.models.api_key import APIKey
from app.models.base import utc_now
from app.models.customer import Customer
from app.models.enums import APIKeyStatus
from app.models.user import User
from app.schemas.api_key import APIKeyCreate, APIKeyCreatedResponse, APIKeyResponse

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.post("", response_model=APIKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_in: APIKeyCreate,
    current_user_tuple: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Generates a new API Key for the user's customer account."""
    _, customer = current_user_tuple
    raw_key, key_prefix, key_hash = generate_api_key()

    api_key = APIKey(
        customer_id=customer.id,
        application_id=key_in.application_id,
        name=key_in.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        status=APIKeyStatus.ACTIVE,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return {
        "id": api_key.id,
        "customer_id": api_key.customer_id,
        "application_id": api_key.application_id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "status": api_key.status.value,
        "expires_at": api_key.expires_at,
        "last_used_at": api_key.last_used_at,
        "created_at": api_key.created_at,
        "raw_secret_key": raw_key,
    }


@router.get("", response_model=list[APIKeyResponse])
async def list_api_keys(
    current_user_tuple: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    """Lists all active API keys for the customer account."""
    _, customer = current_user_tuple
    stmt = (
        select(APIKey)
        .where(
            APIKey.customer_id == customer.id,
            APIKey.status == APIKeyStatus.ACTIVE,
        )
        .order_by(APIKey.created_at.desc())
    )
    result = await db.execute(stmt)
    keys = result.scalars().all()
    return [
        {
            "id": k.id,
            "customer_id": k.customer_id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "status": k.status.value,
            "expires_at": k.expires_at,
            "last_used_at": k.last_used_at,
            "created_at": k.created_at,
        }
        for k in keys
    ]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    current_user_tuple: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Revokes an active API key."""
    _, customer = current_user_tuple
    stmt = select(APIKey).where(
        APIKey.id == key_id,
        APIKey.customer_id == customer.id,
    )
    api_key = (await db.execute(stmt)).scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "KEY_NOT_FOUND", "message": "API key not found."},
        )

    api_key.status = APIKeyStatus.REVOKED
    api_key.revoked_at = utc_now()
    await db.commit()
