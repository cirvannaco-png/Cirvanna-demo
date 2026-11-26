BEGIN;
DROP POLICY IF EXISTS twin_private_service_all ON twin_private.twin_registry_twins;
DROP POLICY IF EXISTS twin_private_service_all ON twin_private.twin_registry_deletion_outbox;
ALTER TABLE twin_private.twin_registry_twins DISABLE ROW LEVEL SECURITY;
ALTER TABLE twin_private.twin_registry_deletion_outbox DISABLE ROW LEVEL SECURITY;
COMMIT;
