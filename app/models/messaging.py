from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UUID
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import MessageEventType, MessageStatus, MessageType, WebhookProcessingStatus

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.meta import WhatsAppNumber
    from app.models.otp import OTPRequest


def utc_now() -> datetime:
    return datetime.now(UTC)


class Message(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "messages"

    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id"), nullable=False, index=True
    )
    otp_request_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("otp_requests.id"), nullable=True, index=True
    )
    whatsapp_number_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("whatsapp_numbers.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="meta")
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )  # wamid
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    message_type: Mapped[MessageType] = mapped_column(
        SQLEnum(MessageType), nullable=False, default=MessageType.AUTHENTICATION
    )
    status: Mapped[MessageStatus] = mapped_column(
        SQLEnum(MessageStatus), nullable=False, default=MessageStatus.QUEUED, index=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship("Customer")
    otp_request: Mapped["OTPRequest | None"] = relationship("OTPRequest")
    whatsapp_number: Mapped["WhatsAppNumber | None"] = relationship("WhatsAppNumber")
    events: Mapped[list["MessageEvent"]] = relationship(
        "MessageEvent", back_populates="message", cascade="all, delete-orphan"
    )


class MessageEvent(Base, UUIDMixin):
    __tablename__ = "message_events"

    message_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[MessageEventType] = mapped_column(
        SQLEnum(MessageEventType), nullable=False, index=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    message: Mapped["Message"] = relationship("Message", back_populates="events")


class WebhookEvent(Base, UUIDMixin):
    __tablename__ = "webhook_events"

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    processing_status: Mapped[WebhookProcessingStatus] = mapped_column(
        SQLEnum(WebhookProcessingStatus),
        nullable=False,
        default=WebhookProcessingStatus.RECEIVED,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
