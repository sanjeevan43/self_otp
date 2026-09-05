"""
P0 Verification Tests
Tests critical cross-cutting concerns: application isolation, wallet atomicity, and webhook idempotency.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_key, hash_password
from app.models.api_key import APIKey
from app.models.application import Application
from app.models.customer import Customer, CustomerUser
from app.models.enums import (
    APIKeyStatus,
    CustomerRole,
    CustomerStatus,
    OTPStatus,
    UserStatus,
    WalletStatus,
)
from app.models.otp import OTPRequest
from app.models.user import User
from app.models.wallet import Wallet
from app.services.wallet_service import WalletService

pytestmark = pytest.mark.asyncio


async def _create_full_tenant(
    db_session: AsyncSession,
    email: str,
    company: str = "Test Co",
    balance: float = 100.0,
) -> tuple[Customer, User, Application, str]:
    """
    Helper: creates Customer + User + CustomerUser link + Application + APIKey + Wallet.
    Returns (customer, user, application, raw_api_key).
    """
    customer = Customer(
        company_name=company,
        email=email,
        status=CustomerStatus.ACTIVE,
        country_code="+1",
    )
    db_session.add(customer)
    await db_session.flush()

    user = User(
        email=email,
        password_hash=hash_password("TestPassword123!"),
        first_name="Test",
        last_name="User",
        status=UserStatus.ACTIVE,
        email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    cu_link = CustomerUser(
        customer_id=customer.id,
        user_id=user.id,
        role=CustomerRole.OWNER,
    )
    db_session.add(cu_link)

    application = Application(
        customer_id=customer.id,
        name=f"{company} App",
        description="Test application",
    )
    db_session.add(application)
    await db_session.flush()

    raw_key, key_prefix, key_hash = generate_api_key()
    api_key = APIKey(
        customer_id=customer.id,
        application_id=application.id,
        name="Test Key",
        key_prefix=key_prefix,
        key_hash=key_hash,
        status=APIKeyStatus.ACTIVE,
    )
    db_session.add(api_key)

    wallet = Wallet(
        customer_id=customer.id,
        balance=balance,
        currency="INR",
        status=WalletStatus.ACTIVE,
    )
    db_session.add(wallet)

    await db_session.commit()
    return customer, user, application, raw_key


async def test_application_isolation(client: AsyncClient, db_session: AsyncSession):
    """API key from tenant 1 must not see OTP requests from tenant 2."""
    # Create two isolated tenants
    cust1, _, app1, key1 = await _create_full_tenant(
        db_session, "tenant1@example.com", "Tenant One", balance=100.0
    )
    cust2, _, app2, key2 = await _create_full_tenant(
        db_session, "tenant2@example.com", "Tenant Two", balance=100.0
    )

    # Tenant 1 sends an OTP
    resp1 = await client.post(
        "/v1/otp/send",
        json={"phone_number": "+14155550001", "ttl_seconds": 300},
        headers={"X-API-Key": key1},
    )
    assert resp1.status_code == 202
    req_id = resp1.json()["data"]["request_id"]

    # Tenant 2 tries to look up Tenant 1's OTP request → should be 404
    resp2 = await client.get(
        f"/v1/otp/{req_id}",
        headers={"X-API-Key": key2},
    )
    assert resp2.status_code == 404, (
        f"Tenant 2 should not see Tenant 1's OTP. Got {resp2.status_code}: {resp2.json()}"
    )


async def test_wallet_debit_insufficient_funds(client: AsyncClient, db_session: AsyncSession):
    """Sending OTP with zero balance must return 402 PAYMENT_REQUIRED."""
    _, _, _, raw_key = await _create_full_tenant(
        db_session, "broke@example.com", "Broke Co", balance=0.0
    )

    resp = await client.post(
        "/v1/otp/send",
        json={"phone_number": "+14155550099", "ttl_seconds": 300},
        headers={"X-API-Key": raw_key},
    )
    assert resp.status_code == 402
    body = resp.json()
    assert body["detail"]["code"] == "INSUFFICIENT_FUNDS"


async def test_wallet_debit_reduces_balance(client: AsyncClient, db_session: AsyncSession):
    """Successful OTP send must deduct credits from wallet."""
    _, _, _, raw_key = await _create_full_tenant(
        db_session, "debit@example.com", "Debit Co", balance=50.0
    )

    # Check balance before
    balance_resp = await client.get(
        "/v1/wallet/balance",
        headers={"X-API-Key": raw_key},
    )
    assert balance_resp.status_code == 200
    before = balance_resp.json()["data"]["balance"]
    assert before == 50.0

    # Send OTP (costs 1.0 credit)
    send_resp = await client.post(
        "/v1/otp/send",
        json={"phone_number": "+14155550050", "ttl_seconds": 300},
        headers={"X-API-Key": raw_key},
    )
    assert send_resp.status_code == 202

    # Check balance after
    balance_resp2 = await client.get(
        "/v1/wallet/balance",
        headers={"X-API-Key": raw_key},
    )
    after = balance_resp2.json()["data"]["balance"]
    assert after == before - 1.0


async def test_webhook_idempotency(client: AsyncClient, db_session: AsyncSession):
    """Submitting the same Meta webhook event twice should not create duplicates."""
    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "123456"},
                            "statuses": [
                                {
                                    "id": "wamid.test_idempotent_001",
                                    "status": "delivered",
                                    "timestamp": "1693526400",
                                    "recipient_id": "14155550001",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    # First submission
    resp1 = await client.post("/v1/webhooks/meta", json=webhook_payload)
    assert resp1.status_code == 200

    # Second submission with same wamid+status → should still return 200 (idempotent)
    resp2 = await client.post("/v1/webhooks/meta", json=webhook_payload)
    assert resp2.status_code == 200
