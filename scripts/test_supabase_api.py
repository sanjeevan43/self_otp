import asyncio
import asyncpg
from app.config import settings
from app.core.hashing import hash_otp_code, verify_otp_code

async def test_supabase_platform():
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(raw_url, statement_cache_size=0)
    print("Testing Supabase PostgreSQL procedures and data integrity...")

    try:
        # 1. Fetch our demo customer, wallet, and application
        customer = await conn.fetchrow("SELECT id FROM customers WHERE email = 'admin@acme-enterprise.com' LIMIT 1;")
        assert customer, "Demo customer not found"
        customer_id = customer["id"]

        wallet_before = await conn.fetchrow("SELECT balance FROM wallets WHERE customer_id = $1;", customer_id)
        assert wallet_before, "Wallet not found"
        initial_balance = wallet_before["balance"]
        print(f"1. Initial Wallet Balance: ${initial_balance:.2f}")

        # 2. Test Atomic Credit Deduction (RPC: deduct_wallet_credit)
        print("2. Testing RPC: deduct_wallet_credit...")
        deduct_res = await conn.fetchval("""
            SELECT deduct_wallet_credit($1, 1.00, NULL, 'Test OTP Deduction');
        """, customer_id)
        import json
        deduct_json = json.loads(deduct_res)
        assert deduct_json["success"] is True, f"Deduction failed: {deduct_json}"
        assert deduct_json["new_balance"] == initial_balance - 1.00
        print(f"   Success! Deducted $1.00. New balance: ${deduct_json['new_balance']:.2f}")

        # Verify transaction logged
        tx = await conn.fetchrow("SELECT * FROM wallet_transactions WHERE wallet_id = $1 ORDER BY created_at DESC LIMIT 1;", deduct_json["wallet_id"])
        assert tx["transaction_type"] == "debit"
        assert tx["amount"] == 1.00
        print("   Success! Transaction logged in wallet_transactions.")

        # 3. Create OTP request and verify hashing
        print("3. Testing OTP creation and HMAC-SHA256 hashing...")
        app = await conn.fetchrow("SELECT id FROM applications WHERE customer_id = $1 LIMIT 1;", customer_id)
        test_code = "789123"
        computed_hash = hash_otp_code(test_code)
        request_id = "test_req_supabase_1"

        otp_id = await conn.fetchval("""
            INSERT INTO otp_requests (
                id, customer_id, application_id, request_id, phone_number,
                otp_hash, status, expires_at, attempts, max_attempts, created_at
            ) VALUES (
                gen_random_uuid(), $1, $2, $3, '+14155552671',
                $4, 'sent'::otp_status, NOW() + INTERVAL '5 minutes', 0, 5, NOW()
            ) RETURNING id;
        """, customer_id, app["id"], request_id, computed_hash)
        print(f"   Created OTP record with ID: {otp_id}")

        # 4. Test Atomic Attempt Tracking (RPC: record_otp_attempt)
        print("4. Testing RPC: record_otp_attempt...")
        attempt_res = await conn.fetchval("SELECT record_otp_attempt($1);", otp_id)
        attempt_json = json.loads(attempt_res)
        assert attempt_json["found"] is True
        assert attempt_json["attempts"] == 1
        assert attempt_json["exceeded"] is False
        print(f"   Success! Attempt count tracked: {attempt_json['attempts']}")

        # 5. Verify OTP code
        print("5. Testing Verification matching...")
        assert verify_otp_code(test_code, computed_hash) is True, "Verification failed for correct code"
        assert verify_otp_code("000000", computed_hash) is False, "Verification matched wrong code"

        await conn.execute("""
            UPDATE otp_requests SET status = 'verified'::otp_status, verified_at = NOW() WHERE id = $1;
        """, otp_id)
        print("   Success! Status updated to 'verified'.")

        # 6. Test Refund Procedure (RPC: refund_wallet_credit)
        print("6. Testing RPC: refund_wallet_credit...")
        refund_res = await conn.fetchval("""
            SELECT refund_wallet_credit($1, 1.00, NULL, 'Test Refund');
        """, customer_id)
        refund_json = json.loads(refund_res)
        assert refund_json["success"] is True
        assert refund_json["new_balance"] == initial_balance
        print(f"   Success! Balance refunded back to: ${refund_json['new_balance']:.2f}")

        # Clean up test OTP record
        await conn.execute("DELETE FROM otp_requests WHERE id = $1;", otp_id)

        print("\n==================================================")
        print("ALL SUPABASE STORED PROCEDURES & INTEGRATION PASSED!")
        print("==================================================")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_supabase_platform())
