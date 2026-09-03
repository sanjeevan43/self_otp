from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SendMessageResult:
    """Standardized result returned by all WhatsApp providers."""

    success: bool
    provider_message_id: str | None = None
    is_temporary_error: bool = False
    error_message: str | None = None


class WhatsAppProvider(ABC):
    """Abstract Base Interface for WhatsApp messaging providers."""

    @abstractmethod
    async def send_otp(
        self,
        phone_number: str,
        otp_code: str,
        template_name: str = "otp_auth_v1",
        language_code: str = "en_US",
    ) -> SendMessageResult:
        """Sends an OTP authentication message through the provider."""
        pass
