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

    # Get default application created during registration
    apps_res = await client.get("/v1/applications", headers=headers)
    assert apps_res.status_code == 200
    apps = apps_res.json()
    assert len(apps) >= 1
    app_id = apps[0]["id"]

    # 1. Create API Key (with required application_id)
    key_res = await client.post(
        "/v1/api-keys",
        json={"name": "Production Key", "application_id": app_id},
        headers=headers,
    )
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
