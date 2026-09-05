import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_wallet_balance_and_ledger(client: AsyncClient) -> None:
    # Register & Login
    await client.post(
        "/v1/auth/register",
        json={"company_name": "Wallet Org", "email": "wallet@test.com", "password": "Password123!"},
    )
    login_res = await client.post(
        "/v1/auth/login", json={"email": "wallet@test.com", "password": "Password123!"}
    )
    access_token = login_res.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {access_token}"}

    # Get default application
    apps_res = await client.get("/v1/applications", headers=user_headers)
    app_id = apps_res.json()[0]["id"]

    key_res = await client.post(
        "/v1/api-keys",
        json={"name": "Wallet Key", "application_id": app_id},
        headers=user_headers,
    )
    raw_api_key = key_res.json()["raw_secret_key"]
    api_headers = {"X-API-Key": raw_api_key}

    # 1. Get initial balance (100 free credits)
    bal_res = await client.get("/v1/wallet/balance", headers=api_headers)
    assert bal_res.status_code == 200
    assert bal_res.json()["data"]["balance"] == 100.0
    assert bal_res.json()["data"]["currency"] == "INR"

    # 2. Topup credits
    topup_res = await client.post(
        "/v1/wallet/topup",
        json={"amount": 50.0, "reference_id": "tx_topup_123"},
        headers=user_headers,
    )
    assert topup_res.status_code == 200
    assert topup_res.json()["data"]["balance"] == 150.0

    # 3. Check transaction history
    tx_res = await client.get("/v1/wallet/transactions", headers=user_headers)
    assert tx_res.status_code == 200
    txs = tx_res.json()
    assert len(txs) == 1
    assert txs[0]["transaction_type"] == "credit"
    assert txs[0]["amount"] == 50.0
