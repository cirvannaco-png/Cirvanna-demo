-- Defense-in-depth: private service schemas remain inaccessible to client roles,
-- while only their owning service group can access rows through RLS.
BEGIN;

REVOKE ALL ON SCHEMA identity_private FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA identity_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA identity_private TO identity_learning_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA identity_private TO identity_learning_service;

REVOKE ALL ON SCHEMA twin_private FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA twin_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA twin_private TO twin_registry_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA twin_private TO twin_registry_service;

ALTER TABLE identity_private.identity_usi_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_usi_color_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_tal_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_tal_consent_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_tal_deletion_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_pnelly_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_dsi_capture_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_dsi_capture_verification_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_consent_revocation_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_private.identity_cil_provider_consent_revocation_outbox ENABLE ROW LEVEL SECURITY;

ALTER TABLE twin_private.twin_registry_twins ENABLE ROW LEVEL SECURITY;
ALTER TABLE twin_private.twin_registry_deletion_outbox ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_usi_profiles;
CREATE POLICY identity_private_service_all ON identity_private.identity_usi_profiles FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_usi_color_profiles;
CREATE POLICY identity_private_service_all ON identity_private.identity_usi_color_profiles FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_tal_events;
CREATE POLICY identity_private_service_all ON identity_private.identity_tal_events FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_tal_consent_receipts;
CREATE POLICY identity_private_service_all ON identity_private.identity_tal_consent_receipts FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_tal_deletion_receipts;
CREATE POLICY identity_private_service_all ON identity_private.identity_tal_deletion_receipts FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_pnelly_conversations;
CREATE POLICY identity_private_service_all ON identity_private.identity_pnelly_conversations FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_dsi_capture_challenges;
CREATE POLICY identity_private_service_all ON identity_private.identity_dsi_capture_challenges FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_dsi_capture_verification_receipts;
CREATE POLICY identity_private_service_all ON identity_private.identity_dsi_capture_verification_receipts FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_consent_revocation_outbox;
CREATE POLICY identity_private_service_all ON identity_private.identity_consent_revocation_outbox FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS identity_private_service_all ON identity_private.identity_cil_provider_consent_revocation_outbox;
CREATE POLICY identity_private_service_all ON identity_private.identity_cil_provider_consent_revocation_outbox FOR ALL TO identity_learning_service USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS twin_private_service_all ON twin_private.twin_registry_twins;
CREATE POLICY twin_private_service_all ON twin_private.twin_registry_twins FOR ALL TO twin_registry_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS twin_private_service_all ON twin_private.twin_registry_deletion_outbox;
CREATE POLICY twin_private_service_all ON twin_private.twin_registry_deletion_outbox FOR ALL TO twin_registry_service USING (true) WITH CHECK (true);

COMMIT;
