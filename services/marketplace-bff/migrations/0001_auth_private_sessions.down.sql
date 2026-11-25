BEGIN;
DROP POLICY IF EXISTS auth_private_bff_service_all ON auth_private.pending_auth;
DROP POLICY IF EXISTS auth_private_bff_service_all ON auth_private.sessions;
ALTER TABLE IF EXISTS auth_private.pending_auth DISABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS auth_private.sessions DISABLE ROW LEVEL SECURITY;
DROP TABLE IF EXISTS auth_private.pending_auth;
DROP TABLE IF EXISTS auth_private.sessions;
COMMIT;
