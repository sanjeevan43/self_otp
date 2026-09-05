from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.application import Application
from app.models.customer import Customer
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    stmt = select(Application).where(Application.customer_id == customer.id)
    result = await db.execute(stmt)
    apps = result.scalars().all()
    return apps


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: str,
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    app = await db.get(Application, app_id)
    if not app or app.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    data: ApplicationCreate,
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    app = Application(
        customer_id=customer.id,
        name=data.name,
        description=data.description,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    app_id: str,
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    app = await db.get(Application, app_id)
    if not app or app.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Application not found")

    await db.delete(app)
    await db.commit()
