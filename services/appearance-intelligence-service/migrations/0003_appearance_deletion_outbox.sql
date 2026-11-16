-- Durable Appearance look deletion and consent revocation outbox.
CREATE TABLE IF NOT EXISTS appearance_look_deletions (
    job_id UUID PRIMARY KEY,
    look_id VARCHAR(128) NOT NULL
        REFERENCES appearance_look_sessions(look_id),
    subject_id VARCHAR(128) NOT NULL,
    consent_id VARCHAR(128) NOT NULL,
    command_id VARCHAR(128) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    consent_revoked BOOLEAN NOT NULL DEFAULT FALSE,
    asset_references JSONB NOT NULL DEFAULT '[]'::jsonb,
    pending_asset_references JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(16) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'retry', 'completed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error VARCHAR(160) NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_appearance_look_deletion_look UNIQUE (look_id),
    CONSTRAINT uq_appearance_look_deletion_command UNIQUE (subject_id, command_id)
);

CREATE INDEX IF NOT EXISTS ix_appearance_look_deletion_status
    ON appearance_look_deletions(status, updated_at);
