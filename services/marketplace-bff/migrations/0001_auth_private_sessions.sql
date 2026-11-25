-- Browser auth sessions and single-use PKCE transactions.
-- Apply with the Supabase project owner; then provision a separate LOGIN member of cirvanna_bff_auth.
-- Never expose auth_private through the Supabase Data API.
CREATE SCHEMA IF NOT EXISTS auth_private;
DO $create_role$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cirvanna_bff_auth') THEN
        CREATE ROLE cirvanna_bff_auth NOLOGIN;
    END IF;
END
$create_role$;
DO $client_roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'CREATE ROLE anon NOLOGIN';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'CREATE ROLE authenticated NOLOGIN';
    END IF;
END
$client_roles$;
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
ALTER DEFAULT PRIVILEGES IN SCHEMA auth_private
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cirvanna_bff_auth;
ALTER TABLE auth_private.pending_auth ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_private.sessions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auth_private_bff_service_all ON auth_private.pending_auth;
CREATE POLICY auth_private_bff_service_all ON auth_private.pending_auth
    FOR ALL TO cirvanna_bff_auth USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS auth_private_bff_service_all ON auth_private.sessions;
CREATE POLICY auth_private_bff_service_all ON auth_private.sessions
    FOR ALL TO cirvanna_bff_auth USING (true) WITH CHECK (true);
