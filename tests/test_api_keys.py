import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_keys_lifecycle(client: AsyncClient) -> None:
    # Register & Login
    reg_payload = {
        "company_name": "API Corp",
        "email": "dev@apicorp.com",
        "password": "Password123!",
    }
    await client.post("/v1/auth/register", json=reg_payload)
    login_res = await client.post(
        "/v1/auth/login", json={"email": "dev@apicorp.com", "password": "Password123!"}
    )
    access_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. Create API Key
    key_res = await client.post("/v1/api-keys", json={"name": "Production Key"}, headers=headers)
    assert key_res.status_code == 201
    key_data = key_res.json()
    assert "raw_secret_key" in key_data
    raw_key = key_data["raw_secret_key"]
    key_id = key_data["id"]
    assert raw_key.startswith("wotp_live_")

    # 2. List API Keys
    list_res = await client.get("/v1/api-keys", headers=headers)
    assert list_res.status_code == 200
    keys = list_res.json()
    assert len(keys) == 1
    assert keys[0]["id"] == key_id

    # 3. Revoke API Key
    revoke_res = await client.delete(f"/v1/api-keys/{key_id}", headers=headers)
    assert revoke_res.status_code == 204

    # 4. List again (empty active keys)
    list_after = await client.get("/v1/api-keys", headers=headers)
    assert len(list_after.json()) == 0
