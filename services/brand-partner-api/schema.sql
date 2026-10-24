-- Initial brand identity/session schema only.
-- Migration candidate: apply only through the approved migration process after
-- database ownership and deployment configuration are confirmed.
-- Product/catalog tables are intentionally not created here.

CREATE TABLE IF NOT EXISTS brand_accounts (
    brand_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_normalized TEXT NOT NULL UNIQUE,
    brand_name TEXT NOT NULL CHECK (char_length(brand_name) BETWEEN 2 AND 120),
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'suspended', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    approved_by TEXT,
    deleted_at TIMESTAMPTZ,
    CHECK (email_normalized = lower(btrim(email_normalized)))
);

CREATE INDEX IF NOT EXISTS idx_brand_accounts_status ON brand_accounts (status);

CREATE TABLE IF NOT EXISTS brand_account_permissions (
    brand_id UUID NOT NULL REFERENCES brand_accounts(brand_id) ON DELETE CASCADE,
    permission TEXT NOT NULL CHECK (char_length(permission) BETWEEN 1 AND 128),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    granted_by TEXT NOT NULL,
    PRIMARY KEY (brand_id, permission)
);

CREATE TABLE IF NOT EXISTS brand_refresh_sessions (
    token_id UUID PRIMARY KEY,
    brand_id UUID NOT NULL REFERENCES brand_accounts(brand_id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    consumed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    replaced_by UUID REFERENCES brand_refresh_sessions(token_id),
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_brand_refresh_sessions_active
    ON brand_refresh_sessions (brand_id, expires_at)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS brand_auth_audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id TEXT NOT NULL,
    brand_id UUID REFERENCES brand_accounts(brand_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'denied', 'failure')),
    correlation_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_brand_auth_audit_events_brand_time
    ON brand_auth_audit_events (brand_id, created_at DESC);
