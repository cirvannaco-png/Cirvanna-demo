CREATE TABLE IF NOT EXISTS appearance_look_consent_events (
    event_id UUID PRIMARY KEY,
    look_id VARCHAR(128) NOT NULL
        REFERENCES appearance_look_sessions(look_id) ON DELETE CASCADE,
    subject_id VARCHAR(128) NOT NULL,
    previous_consent_id VARCHAR(128) NOT NULL,
    consent_id VARCHAR(128) NOT NULL,
    consent_version VARCHAR(80) NOT NULL,
    granted_scopes JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_appearance_look_consent_event UNIQUE (look_id, consent_id)
);

CREATE INDEX IF NOT EXISTS ix_appearance_look_consent_event_subject
    ON appearance_look_consent_events(subject_id, created_at);
