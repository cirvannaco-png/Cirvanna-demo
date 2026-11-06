-- Apply with the repository's approved PostgreSQL migration process.
-- The registry stores opaque references and lifecycle metadata, never image bytes.
CREATE TABLE IF NOT EXISTS virtual_twin_records (
    twin_id VARCHAR(128) PRIMARY KEY,
    subject_id VARCHAR(128) NOT NULL,
    representation_type VARCHAR(32) NOT NULL CHECK (representation_type = 'full_body_mesh'),
    artifact_asset_id VARCHAR(160) NOT NULL,
    source_image_asset_ids JSONB NOT NULL,
    model_version VARCHAR(160) NOT NULL,
    validation_receipt_id VARCHAR(160) NOT NULL,
    consent_id VARCHAR(160) NOT NULL,
    consent_version VARCHAR(80) NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    status VARCHAR(24) NOT NULL CHECK (status IN ('active', 'deletion_pending', 'deleted')),
    version INTEGER NOT NULL CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    deleted_at TIMESTAMPTZ NULL,
    CONSTRAINT uq_virtual_twin_subject_idempotency UNIQUE (subject_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS ix_virtual_twin_subject_status
    ON virtual_twin_records (subject_id, status);

CREATE TABLE IF NOT EXISTS virtual_twin_deletion_outbox (
    outbox_id VARCHAR(36) PRIMARY KEY,
    subject_id VARCHAR(128) NOT NULL,
    twin_id VARCHAR(128) NOT NULL,
    asset_ids JSONB NOT NULL,
    command_id VARCHAR(160) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL CHECK (status IN ('pending', 'complete')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error_code VARCHAR(80) NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS ix_virtual_twin_deletion_status_created
    ON virtual_twin_deletion_outbox (status, created_at);
