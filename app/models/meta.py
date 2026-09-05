from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum, ForeignKey, String, Text, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import MetaAccountStatus, TemplateStatus, WhatsAppNumberStatus

if TYPE_CHECKING:
    from app.models.customer import Customer


class MetaAccount(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "meta_accounts"

    customer_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    business_account_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    whatsapp_business_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MetaAccountStatus] = mapped_column(
        SQLEnum(MetaAccountStatus), nullable=False, default=MetaAccountStatus.ACTIVE
    )

    customer: Mapped["Customer | None"] = relationship("Customer", back_populates="meta_accounts")
    whatsapp_numbers: Mapped[list["WhatsAppNumber"]] = relationship(
        "WhatsAppNumber", back_populates="meta_account", cascade="all, delete-orphan"
    )


class WhatsAppNumber(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "whatsapp_numbers"

    meta_account_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("meta_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone_number_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    verified_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[WhatsAppNumberStatus] = mapped_column(
        SQLEnum(WhatsAppNumberStatus), nullable=False, default=WhatsAppNumberStatus.ACTIVE
    )

    meta_account: Mapped["MetaAccount"] = relationship(
        "MetaAccount", back_populates="whatsapp_numbers"
    )
    templates: Mapped[list["WhatsAppTemplate"]] = relationship(
        "WhatsAppTemplate", back_populates="whatsapp_number", cascade="all, delete-orphan"
    )


class WhatsAppTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "whatsapp_templates"

    whatsapp_number_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("whatsapp_numbers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meta_template_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language_code: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[TemplateStatus] = mapped_column(
        SQLEnum(TemplateStatus), nullable=False, default=TemplateStatus.PENDING
    )

    whatsapp_number: Mapped["WhatsAppNumber"] = relationship(
        "WhatsAppNumber", back_populates="templates"
    )
