import pytest
from httpx import AsyncClient

from app.core.rate_limit import block_customer, block_phone_number
from app.core.hashing import hash_phone_number


@pytest.mark.asyncio
async def test_idempotency_duplicate_request_protection(client: AsyncClient) -> None:
    # Register & setup API Key
    await client.post(
        "/v1/auth/register",
        json={"company_name": "Idempotent Org", "email": "idem@test.com", "password": "Password123!"},
    )
    login_res = await client.post(
        "/v1/auth/login", json={"email": "idem@test.com", "password": "Password123!"}
    )
    access_token = login_res.json()["access_token"]
    key_res = await client.post(
        "/v1/api-keys",
        json={"name": "Idem Key"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    headers = {
        "X-API-Key": key_res.json()["raw_secret_key"],
        "Idempotency-Key": "idem_unique_key_12345",
    }

    # First request
    res1 = await client.post(
        "/v1/otp/send",
        json={"phone_number": "+14155557777", "ttl_seconds": 300},
        headers=headers,
    )
    assert res1.status_code == 202
    req1_id = res1.json()["data"]["request_id"]

    # Duplicate request with same Idempotency-Key
    res2 = await client.post(
        "/v1/otp/send",
        json={"phone_number": "+14155557777", "ttl_seconds": 300},
        headers=headers,
    )
    assert res2.status_code == 202, f"Expected 202, got {res2.status_code}: {res2.text}"
    req2_id = res2.json()["data"]["request_id"]

    # Must return exact same cached request_id
    assert req1_id == req2_id


@pytest.mark.asyncio
async def test_temporary_phone_blocking(client: AsyncClient) -> None:
    # Setup Auth & Key
    await client.post(
        "/v1/auth/register",
        json={"company_name": "Phone Block Org", "email": "phoneblock@test.com", "password": "Password123!"},
    )
    login_res = await client.post(
        "/v1/auth/login", json={"email": "phoneblock@test.com", "password": "Password123!"}
    )
    access_token = login_res.json()["access_token"]
    key_res = await client.post(
        "/v1/api-keys",
        json={"name": "Phone Block Key"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    headers = {"X-API-Key": key_res.json()["raw_secret_key"]}

    target_phone = "+14155558888"
    phone_hash = hash_phone_number(target_phone)

    # Manually trigger block for phone number
    await block_phone_number(redis=None, phone_hash=phone_hash, duration_seconds=60)

    # Attempt to send OTP to blocked phone number
    res = await client.post(
        "/v1/otp/send",
        json={"phone_number": target_phone, "ttl_seconds": 300},
        headers=headers,
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "PHONE_BLOCKED"


@pytest.mark.asyncio
async def test_customer_abuse_blocking(client: AsyncClient) -> None:
    # Setup Auth & Key
    reg_res = await client.post(
        "/v1/auth/register",
        json={"company_name": "Abuse Org", "email": "abuse@test.com", "password": "Password123!"},
    )
    customer_id = reg_res.json()["customer_id"]

    login_res = await client.post(
        "/v1/auth/login", json={"email": "abuse@test.com", "password": "Password123!"}
    )
    access_token = login_res.json()["access_token"]
    key_res = await client.post(
        "/v1/api-keys",
        json={"name": "Abuse Key"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    headers = {"X-API-Key": key_res.json()["raw_secret_key"]}

    # Block customer account
    await block_customer(redis=None, customer_id=customer_id, duration_seconds=3600)

    # Attempt request with blocked customer
    res = await client.post(
        "/v1/otp/send",
        json={"phone_number": "+14155554444", "ttl_seconds": 300},
        headers=headers,
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "CUSTOMER_BLOCKED"
