from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, UUID
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin
from app.models.enums import (
    BillingChannel,
    PaymentOrderStatus,
    PaymentStatus,
    PlanStatus,
    WalletStatus,
    WalletTxnType,
)

if TYPE_CHECKING:
    from app.models.customer import Customer


def utc_now() -> datetime:
    return datetime.now(UTC)


class Wallet(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "wallets"

    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[WalletStatus] = mapped_column(
        SQLEnum(WalletStatus), nullable=False, default=WalletStatus.ACTIVE
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="wallet")
    transactions: Mapped[list["WalletTransaction"]] = relationship(
        "WalletTransaction", back_populates="wallet", cascade="all, delete-orphan"
    )


class WalletTransaction(Base, UUIDMixin):
    __tablename__ = "wallet_transactions"

    wallet_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("wallets.id"), nullable=False, index=True
    )
    transaction_type: Mapped[WalletTxnType] = mapped_column(SQLEnum(WalletTxnType), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    balance_before: Mapped[float] = mapped_column(Float, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")


class PricingPlan(Base, UUIDMixin):
    __tablename__ = "pricing_plans"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    monthly_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[PlanStatus] = mapped_column(
        SQLEnum(PlanStatus), nullable=False, default=PlanStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    rules: Mapped[list["PricingRule"]] = relationship("PricingRule", back_populates="plan")


class PricingRule(Base, UUIDMixin):
    __tablename__ = "pricing_rules"

    plan_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("pricing_plans.id"), nullable=True, index=True
    )
    channel: Mapped[BillingChannel] = mapped_column(
        SQLEnum(BillingChannel), nullable=False, index=True
    )
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    price_per_message: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    plan: Mapped["PricingPlan | None"] = relationship("PricingPlan", back_populates="rules")


class PaymentOrder(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "payment_orders"

    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id"), nullable=False, index=True
    )
    order_reference: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    status: Mapped[PaymentOrderStatus] = mapped_column(
        SQLEnum(PaymentOrderStatus), nullable=False, default=PaymentOrderStatus.CREATED, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    customer: Mapped["Customer"] = relationship("Customer")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="order")


class Payment(Base, UUIDMixin):
    __tablename__ = "payments"

    payment_order_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("payment_orders.id"), nullable=False, index=True
    )
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")
    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus), nullable=False, index=True
    )
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    order: Mapped["PaymentOrder"] = relationship("PaymentOrder", back_populates="payments")
