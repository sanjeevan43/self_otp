from datetime import datetime
from pydantic import BaseModel, Field


class NotificationBase(BaseModel):
    title: str = Field(..., max_length=200)
    message: str
    type: str = Field(..., max_length=50)


class NotificationCreate(NotificationBase):
    customer_id: str


class NotificationResponse(NotificationBase):
    id: str
    customer_id: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
