import asyncio
import asyncpg
from app.config import settings

SQL_FUNCTIONS = """
-- Deduct wallet credit stored procedure
CREATE OR REPLACE FUNCTION deduct_wallet_credit(
    p_customer_id UUID,
    p_amount DOUBLE PRECISION,
    p_reference_id UUID DEFAULT NULL,
    p_description TEXT DEFAULT 'WhatsApp OTP Delivery'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_wallet RECORD;
    v_new_balance DOUBLE PRECISION;
    v_tx_id UUID := gen_random_uuid();
BEGIN
    SELECT id, balance INTO v_wallet
    FROM wallets
    WHERE customer_id = p_customer_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'WALLET_NOT_FOUND'
        );
    END IF;

    IF v_wallet.balance < p_amount THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'INSUFFICIENT_FUNDS',
            'current_balance', v_wallet.balance,
            'required', p_amount
        );
    END IF;

    v_new_balance := v_wallet.balance - p_amount;

    UPDATE wallets
    SET balance = v_new_balance, updated_at = NOW()
    WHERE id = v_wallet.id;

    INSERT INTO wallet_transactions (
        id, wallet_id, transaction_type, amount, balance_before, balance_after,
        reference_type, reference_id, description, created_at
    ) VALUES (
        v_tx_id, v_wallet.id, 'debit'::wallet_txn_type, p_amount, v_wallet.balance, v_new_balance,
        'otp_request', p_reference_id, p_description, NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'wallet_id', v_wallet.id,
        'new_balance', v_new_balance,
        'transaction_id', v_tx_id
    );
END;
$$;

-- Refund wallet credit stored procedure
CREATE OR REPLACE FUNCTION refund_wallet_credit(
    p_customer_id UUID,
    p_amount DOUBLE PRECISION,
    p_reference_id UUID DEFAULT NULL,
    p_description TEXT DEFAULT 'WhatsApp OTP Refund'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_wallet RECORD;
    v_new_balance DOUBLE PRECISION;
    v_tx_id UUID := gen_random_uuid();
BEGIN
    SELECT id, balance INTO v_wallet
    FROM wallets
    WHERE customer_id = p_customer_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'WALLET_NOT_FOUND'
        );
    END IF;

    v_new_balance := v_wallet.balance + p_amount;

    UPDATE wallets
    SET balance = v_new_balance, updated_at = NOW()
    WHERE id = v_wallet.id;

    INSERT INTO wallet_transactions (
        id, wallet_id, transaction_type, amount, balance_before, balance_after,
        reference_type, reference_id, description, created_at
    ) VALUES (
        v_tx_id, v_wallet.id, 'refund'::wallet_txn_type, p_amount, v_wallet.balance, v_new_balance,
        'otp_refund', p_reference_id, p_description, NOW()
    );

    RETURN jsonb_build_object(
        'success', true,
        'new_balance', v_new_balance,
        'transaction_id', v_tx_id
    );
END;
$$;

-- Record OTP attempt stored procedure
CREATE OR REPLACE FUNCTION record_otp_attempt(
    p_otp_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_req RECORD;
    v_new_attempts INTEGER;
BEGIN
    SELECT id, attempts, max_attempts, status INTO v_req
    FROM otp_requests
    WHERE id = p_otp_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('found', false);
    END IF;

    v_new_attempts := v_req.attempts + 1;

    IF v_new_attempts >= v_req.max_attempts THEN
        UPDATE otp_requests
        SET attempts = v_new_attempts, status = 'failed'::otp_status
        WHERE id = p_otp_id;

        RETURN jsonb_build_object(
            'found', true,
            'attempts', v_new_attempts,
            'max_attempts', v_req.max_attempts,
            'exceeded', true
        );
    ELSE
        UPDATE otp_requests
        SET attempts = v_new_attempts
        WHERE id = p_otp_id;

        RETURN jsonb_build_object(
            'found', true,
            'attempts', v_new_attempts,
            'max_attempts', v_req.max_attempts,
            'exceeded', false
        );
    END IF;
END;
$$;
"""

async def deploy():
    raw_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(raw_url, statement_cache_size=0)
    try:
        print("Deploying stored procedures into Supabase PostgreSQL...")
        await conn.execute(SQL_FUNCTIONS)
        print("Stored procedures deployed successfully!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(deploy())
