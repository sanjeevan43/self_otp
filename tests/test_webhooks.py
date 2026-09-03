import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.mark.asyncio
async def test_meta_webhook_challenge_and_ingestion(client: AsyncClient) -> None:
    # 1. Challenge verification (GET)
    verify_token = settings.META_WEBHOOK_VERIFY_TOKEN
    challenge_url = f"/v1/webhooks/meta?hub.mode=subscribe&hub.verify_token={verify_token}&hub.challenge=test_challenge_12345"
    get_res = await client.get(challenge_url)
    assert get_res.status_code == 200
    assert get_res.text == "test_challenge_12345"

    # Invalid token verification fails
    bad_url = "/v1/webhooks/meta?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=123"
    bad_res = await client.get(bad_url)
    assert bad_res.status_code == 403

    # 2. Ingest status webhook payload (POST)
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "200000000000000",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15555555555",
                                "phone_number_id": "100000000000000",
                            },
                            "statuses": [
                                {
                                    "id": "wamid.HBgL1234567890",
                                    "status": "delivered",
                                    "timestamp": "1725379000",
                                    "recipient_id": "14155552671",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    post_res = await client.post("/v1/webhooks/meta", json=webhook_payload)
    assert post_res.status_code == 200
    assert post_res.json() == {"status": "ok"}
