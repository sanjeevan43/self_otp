from datetime import datetime
from typing import Any
from pydantic import BaseModel


class AuditLogResponse(BaseModel):
    id: str
    customer_id: str | None
    user_id: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    metadata_json: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime

    class Config:
        from_attributes = True
