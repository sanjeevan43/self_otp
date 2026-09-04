import enum


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"
    DELETED = "deleted"


class CustomerStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"
    DELETED = "deleted"


class CustomerRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    DEVELOPER = "developer"
    MEMBER = "member"
    BILLING = "billing"


class APIKeyStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class MetaAccountStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    SUSPENDED = "suspended"


class WhatsAppNumberStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    BANNED = "banned"


class TemplateStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISABLED = "disabled"


class OTPStatus(str, enum.Enum):
    CREATED = "created"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    VERIFIED = "verified"
    EXPIRED = "expired"
    FAILED = "failed"
    BLOCKED = "blocked"


class OTPVerificationResult(str, enum.Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    EXPIRED = "expired"
    LOCKED = "locked"


class MessageType(str, enum.Enum):
    AUTHENTICATION = "authentication"
    UTILITY = "utility"
    MARKETING = "marketing"


class MessageStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MessageEventType(str, enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    DELETED = "deleted"


class WebhookProcessingStatus(str, enum.Enum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED = "ignored"


class WalletStatus(str, enum.Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class WalletTxnType(str, enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class PlanStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class BillingChannel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    VOICE = "voice"
    EMAIL = "email"


class PaymentOrderStatus(str, enum.Enum):
    CREATED = "created"
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PaymentStatus(str, enum.Enum):
    INITIATED = "initiated"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class RateLimitAction(str, enum.Enum):
    OTP_SEND = "otp_send"
    OTP_VERIFY = "otp_verify"
    API_REQUEST = "api_request"
    LOGIN = "login"


class EnvironmentType(str, enum.Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
