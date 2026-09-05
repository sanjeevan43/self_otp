from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import JSON, DateTime, String, Text, ForeignKey, UUID, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.application import Application


class MetaWebhookEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "meta_webhook_events"

    meta_message_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # sent, delivered, read, failed
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebhookConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "webhook_configs"

    application_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    subscribed_events: Mapped[list[str]] = mapped_column(JSON, nullable=False)  # List of event types like ['otp.sent', 'otp.verified']

    application: Mapped["Application"] = relationship("Application", back_populates="webhooks")
