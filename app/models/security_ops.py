from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UUID
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin
from app.models.enums import RateLimitAction

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.user import User


def utc_now() -> datetime:
    return datetime.now(UTC)


class RateLimitRecord(Base, UUIDMixin):
    __tablename__ = "rate_limit_records"

    customer_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id"), nullable=True, index=True
    )
    phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    action: Mapped[RateLimitAction] = mapped_column(SQLEnum(RateLimitAction), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class IdempotencyKey(Base, UUIDMixin):
    __tablename__ = "idempotency_keys"

    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True
    )
    customer_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    user: Mapped["User | None"] = relationship("User")
    customer: Mapped["Customer | None"] = relationship("Customer")
