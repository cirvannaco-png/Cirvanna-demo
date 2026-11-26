-- Defense-in-depth for the private Twin Registry schema.
BEGIN;
REVOKE ALL ON SCHEMA twin_private FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA twin_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA twin_private TO twin_registry_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA twin_private TO twin_registry_service;

ALTER TABLE twin_private.twin_registry_twins ENABLE ROW LEVEL SECURITY;
ALTER TABLE twin_private.twin_registry_deletion_outbox ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS twin_private_service_all ON twin_private.twin_registry_twins;
CREATE POLICY twin_private_service_all ON twin_private.twin_registry_twins
    FOR ALL TO twin_registry_service USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS twin_private_service_all ON twin_private.twin_registry_deletion_outbox;
CREATE POLICY twin_private_service_all ON twin_private.twin_registry_deletion_outbox
    FOR ALL TO twin_registry_service USING (true) WITH CHECK (true);
COMMIT;
