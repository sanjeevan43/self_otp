import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient) -> None:
    # 1. Register User & Customer
    payload = {
        "company_name": "Acme Corp",
        "email": "owner@acme.com",
        "password": "SecurePassword123!",
        "first_name": "John",
        "last_name": "Doe",
    }
    response = await client.post("/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "owner@acme.com"
    assert data["status"] == "active"
    assert "customer_id" in data
    assert "id" in data

    # 2. Duplicate registration fails
    dup_res = await client.post("/v1/auth/register", json=payload)
    assert dup_res.status_code == 400
    assert dup_res.json()["detail"]["code"] == "EMAIL_EXISTS"

    # 3. Login
    login_payload = {
        "email": "owner@acme.com",
        "password": "SecurePassword123!",
    }
    login_res = await client.post("/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    tokens = login_res.json()
    assert "access_token" in tokens
    assert tokens["token_type"] == "bearer"

    # 4. Access /v1/auth/me
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me_res = await client.get("/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "owner@acme.com"
