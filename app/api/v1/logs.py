from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.security_ops import AuditLog
from app.models.customer import Customer
from app.models.user import User
from app.schemas.audit_log import AuditLogResponse

router = APIRouter(prefix="/logs", tags=["Logs"])

@router.get("/audit", response_model=list[AuditLogResponse])
async def list_audit_logs(
    user_customer: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    user, customer = user_customer
    stmt = select(AuditLog).where(AuditLog.customer_id == customer.id).order_by(AuditLog.created_at.desc()).limit(100)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return logs
