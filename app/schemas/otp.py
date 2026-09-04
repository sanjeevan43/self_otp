from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.hashing import validate_e164_phone


class OTPSendRequest(BaseModel):
    phone_number: str = Field(
        ..., description="E.164 format international phone number (e.g. +14155552671)"
    )
    otp: str | None = Field(
        None, description="Optional custom 4-8 digit OTP code. Auto-generated if omitted."
    )
    ttl_seconds: int = Field(
        default=300, ge=60, le=3600, description="OTP lifetime in seconds (1 to 60 mins)"
    )
    template_name: str = Field(
        default="otp_auth_v1", description="Approved Meta WhatsApp OTP template name"
    )
    language_code: str = Field(default="en_US", description="Template language code")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean_v = v.strip()
        if not validate_e164_phone(clean_v):
            raise ValueError("Phone number must be in valid E.164 format (e.g. +14155552671)")
        return clean_v

    @field_validator("otp")
    @classmethod
    def validate_otp_digits(cls, v: str | None) -> str | None:
        if v is not None:
            clean_v = v.strip()
            if not clean_v.isdigit() or len(clean_v) < 4 or len(clean_v) > 8:
                raise ValueError("Custom OTP must be numeric and between 4 and 8 digits.")
            return clean_v
        return v


class OTPSendData(BaseModel):
    request_id: str
    phone_number: str
    delivery_status: str
    expires_at: datetime
    cost_credits: float


class OTPSendResponse(BaseModel):
    status: str = "success"
    data: OTPSendData


class OTPVerifyRequest(BaseModel):
    phone_number: str = Field(..., description="E.164 format phone number")
    code: str = Field(..., description="OTP code received by user")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean_v = v.strip()
        if not validate_e164_phone(clean_v):
            raise ValueError("Phone number must be in valid E.164 format")
        return clean_v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean_v = v.strip()
        if not clean_v.isdigit():
            raise ValueError("OTP code must be numeric")
        return clean_v


class OTPVerifyData(BaseModel):
    verified: bool
    request_id: str
    phone_number: str
    verified_at: datetime
    message: str


class OTPVerifyResponse(BaseModel):
    status: str = "success"
    data: OTPVerifyData


class OTPResendRequest(BaseModel):
    request_id: str = Field(..., description="Unique OTP request ID to resend")


class OTPResendData(BaseModel):
    request_id: str
    phone_number: str
    delivery_status: str
    expires_at: datetime
    cost_credits: float
    resend_count: int


class OTPResendResponse(BaseModel):
    status: str = "success"
    data: OTPResendData


class OTPStatusData(BaseModel):
    request_id: str
    phone_number: str
    status: str
    attempts: int
    max_attempts: int
    expires_at: datetime
    created_at: datetime
    verified_at: datetime | None = None


class OTPStatusResponse(BaseModel):
    status: str = "success"
    data: OTPStatusData

class OTPRecordResponse(BaseModel):
    id: str
    phone_number: str
    status: str
    application_id: str | None = None
    cost_credits: float
    created_at: datetime
    expires_at: datetime
    verified_at: datetime | None = None

    class Config:
        from_attributes = True

