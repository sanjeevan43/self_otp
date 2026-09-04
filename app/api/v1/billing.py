from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.usage import PlanResponse, UsageMetricsResponse

router = APIRouter(prefix="/billing", tags=["Billing"])

@router.get("/usage", response_model=UsageMetricsResponse)
async def get_usage(
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
):
    # Mock data
    return UsageMetricsResponse(
        total_sent=15200,
        delivered=14800,
        failed=400,
        delivery_rate=97.3,
        total_cost=152.0,
        credit_balance=48.0,
        currency="USD"
    )

@router.get("/plans", response_model=list[PlanResponse])
async def get_plans(
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
):
    return [
        PlanResponse(
            id="plan_1", name="Starter", price_monthly=29.0, currency="USD",
            features=["10,000 OTPs included", "Standard Support"], is_current=True
        ),
        PlanResponse(
            id="plan_2", name="Pro", price_monthly=99.0, currency="USD",
            features=["50,000 OTPs included", "Priority Support"], is_current=False
        )
    ]
