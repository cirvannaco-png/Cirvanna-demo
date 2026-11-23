-- Browser auth sessions and single-use PKCE transactions.
-- Apply with the dedicated BFF runtime role after creating it; do not expose this schema via Data API.
CREATE SCHEMA IF NOT EXISTS auth_private;
DO $ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cirvanna_bff_auth') THEN
        CREATE ROLE cirvanna_bff_auth NOLOGIN;
    END IF;
END $;
REVOKE ALL ON SCHEMA auth_private FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS auth_private.pending_auth (
    state_hash text PRIMARY KEY,
    provider text NOT NULL CHECK (provider IN ('google','apple','microsoft','email')),
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

GRANT USAGE ON SCHEMA auth_private TO cirvanna_bff_auth;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_private.pending_auth, auth_private.sessions TO cirvanna_bff_auth;
ALTER DEFAULT PRIVILEGES IN SCHEMA auth_private GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cirvanna_bff_auth;
