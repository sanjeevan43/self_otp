from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UUID
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import APIKeyStatus

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.application import Application


class APIKey(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_keys"

    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    status: Mapped[APIKeyStatus] = mapped_column(
        SQLEnum(APIKeyStatus), nullable=False, default=APIKeyStatus.ACTIVE, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="api_keys")
    application: Mapped["Application"] = relationship("Application", back_populates="api_keys")
