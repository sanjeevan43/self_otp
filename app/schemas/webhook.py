from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=500)
    description: str | None = Field(None, max_length=500)
    application_id: str
    subscribed_events: list[str]

class WebhookResponse(BaseModel):
    id: str
    application_id: str
    url: str
    description: str | None
    is_active: bool
    subscribed_events: list[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class MetaWebhookPayload(BaseModel):
    object: str | None = None
    entry: list[dict[str, Any]] | None = None
