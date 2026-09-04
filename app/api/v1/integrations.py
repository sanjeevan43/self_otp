from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User

router = APIRouter(prefix="/integrations", tags=["Integrations"])

class IntegrationResponse(BaseModel):
    id: str
    provider: str
    status: str
    config: dict

class IntegrationCreate(BaseModel):
    provider: str
    config: dict

@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
):
    # Mock Integrations (e.g. Meta, Stripe)
    return [
        IntegrationResponse(id="int_1", provider="meta", status="connected", config={"phone_id": "12345"}),
        IntegrationResponse(id="int_2", provider="stripe", status="connected", config={})
    ]

@router.post("", response_model=IntegrationResponse)
async def create_integration(
    data: IntegrationCreate,
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
):
    return IntegrationResponse(id="int_new", provider=data.provider, status="connected", config=data.config)
