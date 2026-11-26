SET search_path TO twin_private;

-- Cover the deletion outbox foreign key used during owner-scoped dispatch.
CREATE INDEX IF NOT EXISTS ix_twin_registry_deletion_outbox_twin_id
  ON twin_registry_deletion_outbox(twin_id);
