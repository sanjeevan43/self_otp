from datetime import datetime

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    application_id: str | None = None


class APIKeyResponse(BaseModel):
    id: str
    customer_id: str
    application_id: str | None
    name: str
    key_prefix: str
    status: str
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreatedResponse(APIKeyResponse):
    raw_secret_key: str = Field(..., description="Shown ONLY ONCE upon creation. Store safely.")
