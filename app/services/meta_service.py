import logging
from typing import Any

import httpx

from app.config import settings
from app.core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

circuit_breaker = CircuitBreaker("meta_api")


class MetaService:
    @staticmethod
    def format_auth_template_payload(
        phone_number: str,
        otp_code: str,
        template_name: str = "otp_auth_v1",
        language_code: str = "en_US",
    ) -> dict[str, Any]:
        """Formats payload according to Meta WhatsApp Authentication Template schema."""
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": otp_code}],
                    },
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": "0",
                        "parameters": [{"type": "text", "text": otp_code}],
                    },
                ],
            },
        }

    @staticmethod
    async def send_whatsapp_otp(
        phone_number: str,
        otp_code: str,
        template_name: str = "otp_auth_v1",
        language_code: str = "en_US",
    ) -> tuple[bool, str | None, str | None]:
        """
        Sends OTP message via Meta Graph API v20.0.
        Returns: (success: bool, meta_message_id: str | None, error_message: str | None)
        """
        # Mock mode check for local testing or unconfigured tokens
        if settings.META_ACCESS_TOKEN.startswith("mock_") or settings.ENVIRONMENT == "development":
            logger.info(
                f"[MOCK META API] Simulated OTP delivery to {phone_number} with code {otp_code}"
            )
            mock_wamid = f"wamid.HBgL{hash(phone_number + otp_code)}"
            return True, mock_wamid, None

        if await circuit_breaker.is_open():
            logger.error("Meta WhatsApp Cloud API Circuit Breaker is OPEN. Halting dispatch.")
            return (
                False,
                None,
                "Meta WhatsApp API is temporarily unavailable (Circuit Breaker OPEN)",
            )

        url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{settings.META_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = MetaService.format_auth_template_payload(
            phone_number, otp_code, template_name, language_code
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                wamid = messages[0].get("id") if messages else None
                await circuit_breaker.record_result(True)
                return True, wamid, None

            # Error handling
            err_body = response.text
            logger.error(f"Meta Graph API error (Status {response.status_code}): {err_body}")
            await circuit_breaker.record_result(False)
            return False, None, f"Meta API error (Status {response.status_code}): {err_body}"

        except Exception as e:
            logger.exception(f"Exception calling Meta Graph API: {e}")
            await circuit_breaker.record_result(False)
            return False, None, str(e)
