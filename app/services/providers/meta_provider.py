import logging
from typing import Any

import httpx

from app.config import settings
from app.core.circuit_breaker import CircuitBreaker
from app.services.providers.base import SendMessageResult, WhatsAppProvider

logger = logging.getLogger(__name__)

circuit_breaker = CircuitBreaker("meta_api")


class MetaWhatsAppProvider(WhatsAppProvider):
    """
    Concrete implementation of WhatsAppProvider using Meta WhatsApp Cloud API (Graph API v20.0).
    Decouples HTTP requests, payload formatting, authorization, and error handling.
    """

    def format_auth_template_payload(
        self,
        phone_number: str,
        otp_code: str,
        template_name: str = "otp_auth_v1",
        language_code: str = "en_US",
    ) -> dict[str, Any]:
        """Formats payload for Meta WhatsApp Authentication Template schema."""
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

    async def send_otp(
        self,
        phone_number: str,
        otp_code: str,
        template_name: str = "otp_auth_v1",
        language_code: str = "en_US",
    ) -> SendMessageResult:
        """
        Dispatches OTP message to Meta Graph API v20.0.
        Parses provider_message_id (wamid) and classifies temporary vs permanent errors.
        """
        # Mock mode fallback for local dev / unconfigured environments
        if settings.META_ACCESS_TOKEN.startswith("mock_") or settings.ENVIRONMENT == "development":
            logger.info(
                f"[MOCK META API] Simulated OTP delivery to {phone_number} with code {otp_code}"
            )
            mock_wamid = f"wamid.HBgL{hash(phone_number + otp_code)}"
            return SendMessageResult(
                success=True,
                provider_message_id=mock_wamid,
                is_temporary_error=False,
                error_message=None,
            )

        # Circuit Breaker Check
        if await circuit_breaker.is_open():
            logger.error("Meta WhatsApp Cloud API Circuit Breaker is OPEN. Halting dispatch.")
            return SendMessageResult(
                success=False,
                provider_message_id=None,
                is_temporary_error=True,
                error_message="Meta WhatsApp API is temporarily unavailable (Circuit Breaker OPEN)",
            )

        url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{settings.META_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {settings.META_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = self.format_auth_template_payload(
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
                return SendMessageResult(
                    success=True,
                    provider_message_id=wamid,
                    is_temporary_error=False,
                    error_message=None,
                )

            # Error Classification
            status_code = response.status_code
            err_body = response.text
            logger.error(f"Meta Graph API error (Status {status_code}): {err_body}")

            await circuit_breaker.record_result(False)

            # Classify temporary (5xx, 429 rate limit) vs permanent (400, 401, 403)
            is_temp = status_code >= 500 or status_code == 429
            return SendMessageResult(
                success=False,
                provider_message_id=None,
                is_temporary_error=is_temp,
                error_message=f"Meta API error (Status {status_code}): {err_body}",
            )

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            logger.warning(f"Temporary network error calling Meta Graph API: {exc}")
            await circuit_breaker.record_result(False)
            return SendMessageResult(
                success=False,
                provider_message_id=None,
                is_temporary_error=True,
                error_message=f"Network error: {str(exc)}",
            )
        except Exception as e:
            logger.exception(f"Unexpected exception calling Meta Graph API: {e}")
            await circuit_breaker.record_result(False)
            return SendMessageResult(
                success=False,
                provider_message_id=None,
                is_temporary_error=False,
                error_message=str(e),
            )
