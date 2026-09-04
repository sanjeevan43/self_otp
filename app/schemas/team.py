from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from app.models.enums import CustomerRole


class TeamMemberInvite(BaseModel):
    email: EmailStr
    role: CustomerRole = Field(default=CustomerRole.MEMBER)


class TeamMemberResponse(BaseModel):
    id: str
    email: EmailStr
    role: CustomerRole
    created_at: datetime

    class Config:
        from_attributes = True
