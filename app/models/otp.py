from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UUID
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin
from app.models.enums import OTPStatus, OTPVerificationResult

if TYPE_CHECKING:
    from app.models.api_key import APIKey
    from app.models.application import Application
    from app.models.customer import Customer


def utc_now() -> datetime:
    return datetime.now(UTC)


class OTPRequest(Base, UUIDMixin):
    __tablename__ = "otp_requests"

    customer_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("customers.id"), nullable=False, index=True
    )
    application_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("applications.id"), nullable=False, index=True
    )
    api_key_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("api_keys.id"), nullable=True
    )
    request_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    otp_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OTPStatus] = mapped_column(
        SQLEnum(OTPStatus), nullable=False, default=OTPStatus.CREATED, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    customer: Mapped["Customer"] = relationship("Customer")
    application: Mapped["Application"] = relationship("Application")
    api_key: Mapped["APIKey | None"] = relationship("APIKey")
    verifications: Mapped[list["OTPVerification"]] = relationship(
        "OTPVerification", back_populates="otp_request", cascade="all, delete-orphan"
    )


class OTPVerification(Base, UUIDMixin):
    __tablename__ = "otp_verifications"

    otp_request_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("otp_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[OTPVerificationResult] = mapped_column(
        SQLEnum(OTPVerificationResult), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    otp_request: Mapped["OTPRequest"] = relationship("OTPRequest", back_populates="verifications")
