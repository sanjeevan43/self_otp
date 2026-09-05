from datetime import datetime

from pydantic import BaseModel, Field


class ApplicationBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = Field(None, max_length=500)


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=500)


class ApplicationResponse(ApplicationBase):
    id: str
    customer_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
