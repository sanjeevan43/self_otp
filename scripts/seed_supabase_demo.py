import asyncio
import asyncpg
from app.config import settings
from app.core.security import hash_api_key

async def seed_demo():
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(raw_url, statement_cache_size=0)
    try:
        # 1. Check or create customer
        customer = await conn.fetchrow("SELECT id, company_name FROM customers LIMIT 1;")
        if not customer:
            customer_id = await conn.fetchval("""
                INSERT INTO customers (id, company_name, email, phone, status, country_code, created_at, updated_at)
                VALUES (gen_random_uuid(), 'Acme Enterprise Inc.', 'admin@acme-enterprise.com', '+14155552671', 'active'::customer_status, '+1', NOW(), NOW())
                RETURNING id;
            """)
            print(f"Created customer: {customer_id}")
        else:
            customer_id = customer["id"]
            print(f"Found existing customer: {customer_id} ({customer['company_name']})")

        # 2. Check or create application
        app = await conn.fetchrow("SELECT id, name FROM applications WHERE customer_id = $1 LIMIT 1;", customer_id)
        if not app:
            app_id = await conn.fetchval("""
                INSERT INTO applications (id, customer_id, name, description, created_at, updated_at)
                VALUES (gen_random_uuid(), $1, 'Production App', 'Main production OTP application', NOW(), NOW())
                RETURNING id;
            """, customer_id)
            print(f"Created application: {app_id}")
        else:
            app_id = app["id"]
            print(f"Found application: {app_id} ({app['name']})")

        # 3. Check or create wallet
        wallet = await conn.fetchrow("SELECT id, balance FROM wallets WHERE customer_id = $1;", customer_id)
        if not wallet:
            await conn.execute("""
                INSERT INTO wallets (id, customer_id, currency, balance, status, created_at, updated_at)
                VALUES (gen_random_uuid(), $1, 'USD', 500.00, 'active'::wallet_status, NOW(), NOW());
            """, customer_id)
            print("Created wallet with $500.00 balance")
        else:
            print(f"Found wallet: {wallet['id']} with balance {wallet['balance']}")
            if wallet['balance'] < 10.0:
                await conn.execute("UPDATE wallets SET balance = 500.00 WHERE id = $1;", wallet['id'])
                print("Topped up wallet balance to $500.00")

        # 4. Check or create active API key
        test_raw_key = "wotp_live_demo_secret_key_1234567890abcdef"
        test_key_hash = hash_api_key(test_raw_key)

        key_row = await conn.fetchrow("SELECT id, name FROM api_keys WHERE customer_id = $1 AND status = 'active'::api_key_status LIMIT 1;", customer_id)
        if not key_row:
            await conn.execute("""
                INSERT INTO api_keys (
                    id, customer_id, application_id, name, key_prefix, key_hash, status, environment, created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), $1, $2, 'Demo Production Key', 'wotp_live_', $3, 'active'::api_key_status, 'PRODUCTION'::environmenttype, NOW(), NOW()
                );
            """, customer_id, app_id, test_key_hash)
            print(f"Created demo API Key: {test_raw_key}")
        else:
            exists = await conn.fetchrow("SELECT id FROM api_keys WHERE key_hash = $1;", test_key_hash)
            if not exists:
                await conn.execute("""
                    INSERT INTO api_keys (
                        id, customer_id, application_id, name, key_prefix, key_hash, status, environment, created_at, updated_at
                    ) VALUES (
                        gen_random_uuid(), $1, $2, 'Demo Production Key', 'wotp_live_', $3, 'active'::api_key_status, 'PRODUCTION'::environmenttype, NOW(), NOW()
                    );
                """, customer_id, app_id, test_key_hash)
            print(f"Active API Key ready: {test_raw_key}")

        print("\n=== SUPABASE READY FOR EDGE FUNCTIONS ===")
        print(f"Customer ID:    {customer_id}")
        print(f"Application ID: {app_id}")
        print(f"API Key:        {test_raw_key}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_demo())
