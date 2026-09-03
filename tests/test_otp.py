import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_otp_send_and_verify_flow(client: AsyncClient) -> None:
    # 1. Setup User & API Key
    await client.post(
        "/v1/auth/register",
        json={"company_name": "OTP Test Org", "email": "otp@test.com", "password": "Password123!"},
    )
    login_res = await client.post(
        "/v1/auth/login", json={"email": "otp@test.com", "password": "Password123!"}
    )
    access_token = login_res.json()["access_token"]

    key_res = await client.post(
        "/v1/api-keys",
        json={"name": "OTP Key"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    raw_api_key = key_res.json()["raw_secret_key"]
    api_headers = {"X-API-Key": raw_api_key}

    # 2. Send OTP
    send_payload = {
        "phone_number": "+14155552671",
        "otp": "987654",
        "ttl_seconds": 300,
    }
    send_res = await client.post("/v1/otp/send", json=send_payload, headers=api_headers)
    assert send_res.status_code == 202
    send_data = send_res.json()
    assert send_data["status"] == "success"
    assert send_data["data"]["phone_number"] == "+1415***2671"
    assert "request_id" in send_data["data"]
    assert send_data["data"]["cost_credits"] == 1.0

    # 3. Send OTP again immediately (Cooldown Triggered)
    cooldown_res = await client.post("/v1/otp/send", json=send_payload, headers=api_headers)
    assert cooldown_res.status_code == 429
    assert cooldown_res.json()["detail"]["code"] == "COOLDOWN_ACTIVE"

    # 4. Verify OTP Invalid Code
    invalid_verify_res = await client.post(
        "/v1/otp/verify",
        json={"phone_number": "+14155552671", "code": "000000"},
        headers=api_headers,
    )
    assert invalid_verify_res.status_code == 400
    assert invalid_verify_res.json()["detail"]["code"] == "INVALID_OTP"

    # 5. Verify OTP Correct Code
    valid_verify_res = await client.post(
        "/v1/otp/verify",
        json={"phone_number": "+14155552671", "code": "987654"},
        headers=api_headers,
    )
    assert valid_verify_res.status_code == 200
    verify_data = valid_verify_res.json()
    assert verify_data["data"]["verified"] is True
    assert verify_data["data"]["message"] == "OTP verified successfully"

    # 6. Verify OTP again (Replay attack attempt fails because OTP deleted on success)
    replay_res = await client.post(
        "/v1/otp/verify",
        json={"phone_number": "+14155552671", "code": "987654"},
        headers=api_headers,
    )
    assert replay_res.status_code == 400
    assert replay_res.json()["detail"]["code"] == "OTP_EXPIRED"

    # 7. Check OTP Status GET endpoint
    request_id = send_data["data"]["request_id"]
    status_res = await client.get(f"/v1/otp/{request_id}", headers=api_headers)
    assert status_res.status_code == 200
    status_data = status_res.json()["data"]
    assert status_data["request_id"] == request_id
    assert status_data["status"] == "verified"
    assert status_data["attempts"] == 2
    assert status_data["verified_at"] is not None


@pytest.mark.asyncio
async def test_otp_max_attempts_lockout(client: AsyncClient) -> None:
    # 1. Register & Auth
    await client.post(
        "/v1/auth/register",
        json={"company_name": "Lockout Org", "email": "lock@test.com", "password": "Password123!"},
    )
    login_res = await client.post(
        "/v1/auth/login", json={"email": "lock@test.com", "password": "Password123!"}
    )
    access_token = login_res.json()["access_token"]
    key_res = await client.post(
        "/v1/api-keys",
        json={"name": "Lock Key"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    api_headers = {"X-API-Key": key_res.json()["raw_secret_key"]}

    # 2. Send OTP
    send_res = await client.post(
        "/v1/otp/send",
        json={"phone_number": "+14155559999", "otp": "112233", "ttl_seconds": 300},
        headers=api_headers,
    )
    assert send_res.status_code == 202
    req_id = send_res.json()["data"]["request_id"]

    # 3. Submit wrong OTP 1
    res1 = await client.post(
        "/v1/otp/verify",
        json={"phone_number": "+14155559999", "code": "000001"},
        headers=api_headers,
    )
    assert res1.status_code == 400
    assert res1.json()["detail"]["code"] == "INVALID_OTP"

    # 4. Submit wrong OTP 2
    res2 = await client.post(
        "/v1/otp/verify",
        json={"phone_number": "+14155559999", "code": "000002"},
        headers=api_headers,
    )
    assert res2.status_code == 400
    assert res2.json()["detail"]["code"] == "INVALID_OTP"

    # 5. Submit wrong OTP 3 -> Reaches max attempts (3)
    res3 = await client.post(
        "/v1/otp/verify",
        json={"phone_number": "+14155559999", "code": "000003"},
        headers=api_headers,
    )
    assert res3.status_code == 400
    assert res3.json()["detail"]["code"] == "MAX_ATTEMPTS_EXCEEDED"

    # 6. Check status is now expired/locked
    status_res = await client.get(f"/v1/otp/{req_id}", headers=api_headers)
    assert status_res.status_code == 200
    assert status_res.json()["data"]["status"] == "expired"
    assert status_res.json()["data"]["attempts"] == 3

