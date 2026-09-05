-- ====================================================================
-- WhatsApp OTP API Platform - Complete Supabase PostgreSQL Schema
-- ====================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- --------------------------------------------------------------------
-- ENUM TYPES
-- --------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE customer_status_enum AS ENUM ('active', 'suspended', 'pending');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE customer_role_enum AS ENUM ('owner', 'admin', 'developer', 'viewer');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE api_key_status_enum AS ENUM ('active', 'revoked', 'expired');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE environment_type_enum AS ENUM ('sandbox', 'production');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE wallet_transaction_type_enum AS ENUM ('credit', 'debit', 'refund', 'adjustment');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE otp_status_enum AS ENUM ('pending', 'sent', 'delivered', 'failed', 'verified', 'expired', 'cooldown');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE meta_account_status_enum AS ENUM ('active', 'pending_verification', 'suspended');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE template_category_enum AS ENUM ('authentication', 'utility', 'marketing');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE template_status_enum AS ENUM ('approved', 'pending', 'rejected');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE webhook_delivery_status_enum AS ENUM ('pending', 'success', 'failed');
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- --------------------------------------------------------------------
-- TABLES
-- --------------------------------------------------------------------

-- 1. Customers (Tenants)
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    status customer_status_enum NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Users (Accounts)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_superuser BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Customer Users (Tenant Membership)
CREATE TABLE IF NOT EXISTS customer_users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role customer_role_enum NOT NULL DEFAULT 'admin',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(customer_id, user_id)
);

-- 4. Applications (Projects within a Customer)
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. API Keys
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_prefix VARCHAR(32) NOT NULL,
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    status api_key_status_enum NOT NULL DEFAULT 'active',
    environment environment_type_enum NOT NULL DEFAULT 'sandbox',
    rate_limit_rps INTEGER NOT NULL DEFAULT 60,
    expires_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Wallets (Prepaid balance)
CREATE TABLE IF NOT EXISTS wallets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID UNIQUE NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    balance NUMERIC(14, 4) NOT NULL DEFAULT 0.0000 CHECK (balance >= 0),
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Wallet Transactions
CREATE TABLE IF NOT EXISTS wallet_transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    amount NUMERIC(14, 4) NOT NULL,
    transaction_type wallet_transaction_type_enum NOT NULL,
    balance_after NUMERIC(14, 4) NOT NULL,
    reference_id VARCHAR(255),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. Meta Accounts
CREATE TABLE IF NOT EXISTS meta_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    business_account_id VARCHAR(255) NOT NULL,
    status meta_account_status_enum NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 9. WhatsApp Phone Numbers
CREATE TABLE IF NOT EXISTS whatsapp_numbers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meta_account_id UUID NOT NULL REFERENCES meta_accounts(id) ON DELETE CASCADE,
    phone_number_id VARCHAR(255) NOT NULL,
    display_phone_number VARCHAR(64) NOT NULL,
    verified_name VARCHAR(255) NOT NULL,
    quality_rating VARCHAR(64) NOT NULL DEFAULT 'UNKNOWN',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 10. WhatsApp Templates
CREATE TABLE IF NOT EXISTS whatsapp_templates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meta_account_id UUID NOT NULL REFERENCES meta_accounts(id) ON DELETE CASCADE,
    template_name VARCHAR(255) NOT NULL,
    language VARCHAR(32) NOT NULL DEFAULT 'en_US',
    category template_category_enum NOT NULL DEFAULT 'authentication',
    status template_status_enum NOT NULL DEFAULT 'approved',
    body_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 11. OTP Requests
CREATE TABLE IF NOT EXISTS otp_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    recipient_phone VARCHAR(32) NOT NULL,
    otp_hash VARCHAR(255) NOT NULL,
    salt VARCHAR(255) NOT NULL,
    status otp_status_enum NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    meta_message_id VARCHAR(255),
    idempotency_key VARCHAR(255),
    expires_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ,
    cost_deducted NUMERIC(10, 4) NOT NULL DEFAULT 1.0000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 12. Idempotency Keys
CREATE TABLE IF NOT EXISTS idempotency_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    key VARCHAR(255) NOT NULL,
    request_params JSONB,
    response_code INTEGER,
    response_body JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(customer_id, key)
);

-- 13. Meta Webhook Events
CREATE TABLE IF NOT EXISTS meta_webhook_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id VARCHAR(255) UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    raw_payload JSONB NOT NULL,
    processed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 14. Webhook Configurations
CREATE TABLE IF NOT EXISTS webhook_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    application_id UUID REFERENCES applications(id) ON DELETE CASCADE,
    url VARCHAR(1024) NOT NULL,
    secret_key VARCHAR(255) NOT NULL,
    events JSONB NOT NULL DEFAULT '["otp.sent", "otp.delivered", "otp.verified", "otp.failed"]',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 15. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    ip_address VARCHAR(45),
    metadata_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- --------------------------------------------------------------------
-- INDEXES
-- --------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS ix_api_keys_customer_id ON api_keys(customer_id);
CREATE INDEX IF NOT EXISTS ix_api_keys_application_id ON api_keys(application_id);

CREATE INDEX IF NOT EXISTS ix_otp_requests_customer_id ON otp_requests(customer_id);
CREATE INDEX IF NOT EXISTS ix_otp_requests_application_id ON otp_requests(application_id);
CREATE INDEX IF NOT EXISTS ix_otp_requests_recipient_phone ON otp_requests(recipient_phone);
CREATE INDEX IF NOT EXISTS ix_otp_requests_meta_message_id ON otp_requests(meta_message_id);
CREATE INDEX IF NOT EXISTS ix_otp_requests_status ON otp_requests(status);
CREATE INDEX IF NOT EXISTS ix_otp_requests_created_at ON otp_requests(created_at);

CREATE INDEX IF NOT EXISTS ix_idempotency_keys_customer_key ON idempotency_keys(customer_id, key);

-- --------------------------------------------------------------------
-- ATOMIC STORED PROCEDURES (Concurrency & Race condition safe)
-- --------------------------------------------------------------------

-- Function: Atomically deduct credits from wallet
CREATE OR REPLACE FUNCTION deduct_wallet_credit(
    p_customer_id UUID,
    p_amount NUMERIC,
    p_reference_id TEXT,
    p_description TEXT DEFAULT 'OTP SMS Delivery Charge'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_wallet RECORD;
    v_new_balance NUMERIC;
    v_tx_id UUID;
BEGIN
    -- Row-lock wallet to prevent race conditions
    SELECT id, balance INTO v_wallet
    FROM wallets
    WHERE customer_id = p_customer_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Wallet not found for customer %', p_customer_id;
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
        wallet_id, amount, transaction_type, balance_after, reference_id, description
    ) VALUES (
        v_wallet.id, -p_amount, 'debit', v_new_balance, p_reference_id, p_description
    ) RETURNING id INTO v_tx_id;

    RETURN jsonb_build_object(
        'success', true,
        'wallet_id', v_wallet.id,
        'new_balance', v_new_balance,
        'transaction_id', v_tx_id
    );
END;
$$;

-- Function: Atomically refund credits
CREATE OR REPLACE FUNCTION refund_wallet_credit(
    p_customer_id UUID,
    p_amount NUMERIC,
    p_reference_id TEXT,
    p_description TEXT DEFAULT 'OTP Delivery Failure Refund'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_wallet RECORD;
    v_new_balance NUMERIC;
BEGIN
    SELECT id, balance INTO v_wallet
    FROM wallets
    WHERE customer_id = p_customer_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Wallet not found for customer %', p_customer_id;
    END IF;

    v_new_balance := v_wallet.balance + p_amount;

    UPDATE wallets
    SET balance = v_new_balance, updated_at = NOW()
    WHERE id = v_wallet.id;

    INSERT INTO wallet_transactions (
        wallet_id, amount, transaction_type, balance_after, reference_id, description
    ) VALUES (
        v_wallet.id, p_amount, 'refund', v_new_balance, p_reference_id, p_description
    );

    RETURN jsonb_build_object(
        'success', true,
        'new_balance', v_new_balance
    );
END;
$$;

-- Function: Record an OTP verification attempt safely
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
        SET attempts = v_new_attempts, status = 'failed', updated_at = NOW()
        WHERE id = p_otp_id;

        RETURN jsonb_build_object(
            'found', true,
            'attempts', v_new_attempts,
            'max_attempts', v_req.max_attempts,
            'exceeded', true
        );
    ELSE
        UPDATE otp_requests
        SET attempts = v_new_attempts, updated_at = NOW()
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
