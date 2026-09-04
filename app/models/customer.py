from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UUID
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import CustomerRole, CustomerStatus

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.meta import MetaAccount
    from app.models.user import User
    from app.models.wallet import Wallet
    from app.models.application import Application


def utc_now() -> datetime:
    return datetime.now(UTC)


class Customer(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "customers"

    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[CustomerStatus] = mapped_column(
        SQLEnum(CustomerStatus), nullable=False, default=CustomerStatus.ACTIVE
    )
    country_code: Mapped[str] = mapped_column(String(5), nullable=False, default="+91")

    users: Mapped[list["CustomerUser"]] = relationship(
        "CustomerUser", back_populates="customer", cascade="all, delete-orphan"
    )
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="customer", cascade="all, delete-orphan"
    )
    wallet: Mapped["Wallet"] = relationship(
        "Wallet", back_populates="customer", uselist=False, cascade="all, delete-orphan"
    )
    meta_accounts: Mapped[list["MetaAccount"]] = relationship(
        "MetaAccount", back_populates="customer", cascade="all, delete-orphan"
    )
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="customer", cascade="all, delete-orphan"
    )


class CustomerUser(Base):
    __tablename__ = "customer_users"

    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[CustomerRole] = mapped_column(
        SQLEnum(CustomerRole), nullable=False, default=CustomerRole.MEMBER
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="users")
    user: Mapped["User"] = relationship("User", back_populates="customer_links")
