import pytest
from httpx import AsyncClient

from app.core.rate_limit import block_customer, block_phone_number
from app.core.hashing import hash_phone_number


async def _setup_api_key(client: AsyncClient, company: str, email: str, password: str = "Password123!") -> tuple[str, str, str]:
    """Helper: register, login, get default app, create API key. Returns (raw_api_key, access_token, customer_id)."""
    reg_res = await client.post(
        "/v1/auth/register",
        json={"company_name": company, "email": email, "password": password},
    )
    customer_id = reg_res.json()["customer_id"]
    login_res = await client.post(
        "/v1/auth/login", json={"email": email, "password": password}
    )
    access_token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # Get default application
    apps_res = await client.get("/v1/applications", headers=auth_headers)
    app_id = apps_res.json()[0]["id"]

    key_res = await client.post(
        "/v1/api-keys",
        json={"name": f"{company} Key", "application_id": app_id},
        headers=auth_headers,
    )
    return key_res.json()["raw_secret_key"], access_token, customer_id


@pytest.mark.asyncio
async def test_idempotency_duplicate_request_protection(client: AsyncClient) -> None:
    raw_api_key, _, _ = await _setup_api_key(client, "Idempotent Org", "idem@test.com")
    headers = {
        "X-API-Key": raw_api_key,
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
    raw_api_key, _, _ = await _setup_api_key(client, "Phone Block Org", "phoneblock@test.com")
    headers = {"X-API-Key": raw_api_key}

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
    raw_api_key, _, customer_id = await _setup_api_key(client, "Abuse Org", "abuse@test.com")
    headers = {"X-API-Key": raw_api_key}

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
