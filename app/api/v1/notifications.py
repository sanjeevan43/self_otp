from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.customer import Customer
from app.models.user import User
from app.schemas.notification import NotificationResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    stmt = select(Notification).where(Notification.customer_id == customer.id).order_by(Notification.created_at.desc())
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    return notifications

@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_as_read(
    notification_id: str,
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    notif = await db.get(Notification, notification_id)
    if not notif or notif.customer_id != customer.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notif.is_read = True
    notif.read_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(notif)
    return notif
