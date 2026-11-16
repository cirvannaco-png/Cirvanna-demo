-- Appearance look-session metadata only. Binary assets remain in Asset Service.
CREATE TABLE IF NOT EXISTS appearance_look_sessions (
    look_id VARCHAR(128) PRIMARY KEY,
    subject_id VARCHAR(128) NOT NULL,
    consent_id VARCHAR(128) NOT NULL,
    consent_version VARCHAR(80) NOT NULL,
    base JSONB NOT NULL,
    operations JSONB NOT NULL DEFAULT '[]'::jsonb,
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version >= 1),
    is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_appearance_subject_look UNIQUE (subject_id, look_id)
);

CREATE INDEX IF NOT EXISTS ix_appearance_look_subject_status
    ON appearance_look_sessions(subject_id, status);

CREATE TABLE IF NOT EXISTS appearance_look_versions (
    look_id VARCHAR(128) NOT NULL REFERENCES appearance_look_sessions(look_id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version >= 1),
    subject_id VARCHAR(128) NOT NULL,
    command_id VARCHAR(128) NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    action VARCHAR(24) NOT NULL,
    base_snapshot JSONB NOT NULL,
    operations_snapshot JSONB NOT NULL,
    output_asset_id UUID NULL,
    renderer_id VARCHAR(128) NULL,
    renderer_version VARCHAR(180) NULL,
    fidelity_assessment JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (look_id, version),
    CONSTRAINT uq_appearance_subject_command UNIQUE (subject_id, command_id)
);

CREATE INDEX IF NOT EXISTS ix_appearance_look_version
    ON appearance_look_versions(look_id, version);
