from typing import Annotated
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.customer import Customer, CustomerUser
from app.models.user import User
from app.schemas.team import TeamMemberInvite, TeamMemberResponse

router = APIRouter(prefix="/team", tags=["Team"])

@router.get("", response_model=list[TeamMemberResponse])
async def list_team_members(
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    stmt = (
        select(User, CustomerUser)
        .join(CustomerUser, User.id == CustomerUser.user_id)
        .where(CustomerUser.customer_id == customer.id)
    )
    result = await db.execute(stmt)
    
    response = []
    for u, cu in result.all():
        response.append(
            TeamMemberResponse(
                id=u.id,
                email=u.email,
                role=cu.role,
                created_at=cu.created_at
            )
        )
    return response

@router.post("/invite", status_code=status.HTTP_201_CREATED)
async def invite_team_member(
    data: TeamMemberInvite,
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    # Mock invitation logic
    return {"status": "success", "message": f"Invited {data.email}"}

@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    member_id: str,
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    stmt = select(CustomerUser).where(
        CustomerUser.customer_id == customer.id,
        CustomerUser.user_id == member_id
    )
    result = await db.execute(stmt)
    cu = result.scalar_one_or_none()
    if not cu:
        raise HTTPException(status_code=404, detail="Member not found")
    
    await db.delete(cu)
    await db.commit()
