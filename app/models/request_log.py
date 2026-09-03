from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class APIRequestLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_request_logs"

    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    api_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
