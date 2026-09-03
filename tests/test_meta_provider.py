import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.providers.base import SendMessageResult, WhatsAppProvider
from app.services.providers.meta_provider import MetaWhatsAppProvider
from app.services.whatsapp_service import WhatsAppService


@pytest.mark.asyncio
async def test_meta_provider_auth_template_payload_formatting() -> None:
    provider = MetaWhatsAppProvider()
    payload = provider.format_auth_template_payload(
        phone_number="+14155552671",
        otp_code="998877",
        template_name="otp_auth_v1",
        language_code="en_US",
    )

    assert payload["messaging_product"] == "whatsapp"
    assert payload["to"] == "+14155552671"
    assert payload["template"]["name"] == "otp_auth_v1"
    assert payload["template"]["language"]["code"] == "en_US"
    assert payload["template"]["components"][0]["parameters"][0]["text"] == "998877"


@pytest.mark.asyncio
async def test_meta_provider_successful_send_wamid_extraction() -> None:
    provider = MetaWhatsAppProvider()
    
    with patch("app.config.settings.META_ACCESS_TOKEN", "real_test_access_token_12345"), \
         patch("app.config.settings.ENVIRONMENT", "production"):
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messaging_product": "whatsapp",
            "contacts": [{"input": "+14155552671", "wa_id": "14155552671"}],
            "messages": [{"id": "wamid.HBgLMTE0MTU1NTI2NzEVAgARGBI1REI3RTI0OUE0MzRBMzg5AA=="}],
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.send_otp(
                phone_number="+14155552671",
                otp_code="123456",
            )

            assert result.success is True
            assert result.provider_message_id == "wamid.HBgLMTE0MTU1NTI2NzEVAgARGBI1REI3RTI0OUE0MzRBMzg5AA=="
            assert result.is_temporary_error is False
            assert result.error_message is None


@pytest.mark.asyncio
async def test_meta_provider_temporary_failure_classification() -> None:
    provider = MetaWhatsAppProvider()

    with patch("app.config.settings.META_ACCESS_TOKEN", "real_test_access_token_12345"), \
         patch("app.config.settings.ENVIRONMENT", "production"):
        
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.send_otp(
                phone_number="+14155552671",
                otp_code="123456",
            )

            assert result.success is False
            assert result.is_temporary_error is True
            assert "503" in (result.error_message or "")


@pytest.mark.asyncio
async def test_meta_provider_permanent_failure_classification() -> None:
    provider = MetaWhatsAppProvider()

    with patch("app.config.settings.META_ACCESS_TOKEN", "real_test_access_token_12345"), \
         patch("app.config.settings.ENVIRONMENT", "production"):
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid Recipient Number"

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.send_otp(
                phone_number="+14155552671",
                otp_code="123456",
            )

            assert result.success is False
            assert result.is_temporary_error is False
            assert "400" in (result.error_message or "")


@pytest.mark.asyncio
async def test_whatsapp_service_decoupled_provider_injection() -> None:
    # Custom Mock Provider implementing WhatsAppProvider
    class MockCustomProvider(WhatsAppProvider):
        async def send_otp(
            self,
            phone_number: str,
            otp_code: str,
            template_name: str = "otp_auth_v1",
            language_code: str = "en_US",
        ) -> SendMessageResult:
            return SendMessageResult(
                success=True,
                provider_message_id="mock_custom_wamid_999",
                is_temporary_error=False,
            )

    custom_service = WhatsAppService(provider=MockCustomProvider())
    res = await custom_service.send_otp(phone_number="+14155552671", otp_code="654321")

    assert res.success is True
    assert res.provider_message_id == "mock_custom_wamid_999"
