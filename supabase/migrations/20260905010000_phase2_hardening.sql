-- ====================================================================
-- Phase 2.1 & 2.2 Hardening: Refresh Token Rotation & Wallet Invariants
-- ====================================================================

-- 1. Create refresh_tokens table for secure token family rotation
CREATE TABLE IF NOT EXISTS public.refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by_token_id UUID REFERENCES public.refresh_tokens(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);

-- Indexes for efficient lookup and cleanup
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON public.refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON public.refresh_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON public.refresh_tokens(expires_at);

-- 2. Add non-negative balance invariant check constraint to wallets table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'chk_wallets_balance_non_negative'
    ) THEN
        ALTER TABLE public.wallets
        ADD CONSTRAINT chk_wallets_balance_non_negative
        CHECK (balance >= 0.0000);
    END IF;
END $$;
