-- Browser auth sessions and single-use PKCE transactions.
-- Apply with the dedicated BFF runtime role after creating it; do not expose this schema via Data API.
CREATE SCHEMA IF NOT EXISTS auth_private;
REVOKE ALL ON SCHEMA auth_private FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS auth_private.pending_auth (
    state_hash text PRIMARY KEY,
    provider text NOT NULL CHECK (provider IN ('google','apple','microsoft')),
    verifier_ciphertext bytea NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pending_auth_expiry_idx ON auth_private.pending_auth(expires_at);
CREATE TABLE IF NOT EXISTS auth_private.sessions (
    session_hash text PRIMARY KEY,
    user_id uuid NOT NULL,
    token_ciphertext bytea NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS auth_sessions_user_idx ON auth_private.sessions(user_id);
CREATE INDEX IF NOT EXISTS auth_sessions_expiry_idx ON auth_private.sessions(expires_at);
REVOKE ALL ON ALL TABLES IN SCHEMA auth_private FROM PUBLIC, anon, authenticated;
