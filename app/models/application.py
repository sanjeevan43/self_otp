from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text, UUID, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import EnvironmentType

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.api_key import APIKey
    from app.models.webhook import WebhookConfig


class Application(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "applications"

    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    environment: Mapped[EnvironmentType] = mapped_column(
        SQLEnum(EnvironmentType), nullable=False, default=EnvironmentType.DEVELOPMENT
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="applications")
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="application", cascade="all, delete-orphan"
    )
    webhooks: Mapped[list["WebhookConfig"]] = relationship(
        "WebhookConfig", back_populates="application", cascade="all, delete-orphan"
    )
