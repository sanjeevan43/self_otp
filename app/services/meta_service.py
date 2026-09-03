import logging
from typing import Any

import httpx

from app.config import settings
from app.core.circuit_breaker import CircuitBreaker

from app.services.providers.meta_provider import MetaWhatsAppProvider
from app.services.whatsapp_service import whatsapp_service

logger = logging.getLogger(__name__)


class MetaService:
    @staticmethod
    def format_auth_template_payload(
        phone_number: str,
        otp_code: str,
        template_name: str = "otp_auth_v1",
        language_code: str = "en_US",
    ) -> dict[str, Any]:
        """Formats payload according to Meta WhatsApp Authentication Template schema."""
        provider = MetaWhatsAppProvider()
        return provider.format_auth_template_payload(
            phone_number=phone_number,
            otp_code=otp_code,
            template_name=template_name,
            language_code=language_code,
        )

    @staticmethod
    async def send_whatsapp_otp(
        phone_number: str,
        otp_code: str,
        template_name: str = "otp_auth_v1",
        language_code: str = "en_US",
    ) -> tuple[bool, str | None, str | None]:
        """
        Sends OTP message via WhatsAppService provider interface.
        Returns: (success: bool, meta_message_id: str | None, error_message: str | None)
        """
        res = await whatsapp_service.send_otp(
            phone_number=phone_number,
            otp_code=otp_code,
            template_name=template_name,
            language_code=language_code,
        )
        return res.success, res.provider_message_id, res.error_message

