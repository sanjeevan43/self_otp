import logging

from app.services.providers.base import SendMessageResult, WhatsAppProvider
from app.services.providers.meta_provider import MetaWhatsAppProvider

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    High-level WhatsApp Service layer.
    Acts as provider dispatcher so OTP business logic is never coupled to Meta HTTP calls.
    """

    def __init__(self, provider: WhatsAppProvider | None = None) -> None:
        self.provider: WhatsAppProvider = provider or MetaWhatsAppProvider()

    async def send_otp(
        self,
        phone_number: str,
        otp_code: str,
        template_name: str = "otp_auth_v1",
        language_code: str = "en_US",
    ) -> SendMessageResult:
        """Dispatches OTP message using the configured provider."""
        return await self.provider.send_otp(
            phone_number=phone_number,
            otp_code=otp_code,
            template_name=template_name,
            language_code=language_code,
        )


# Default singleton instance
whatsapp_service = WhatsAppService()
