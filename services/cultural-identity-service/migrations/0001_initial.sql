CREATE TABLE IF NOT EXISTS cultural_declarations (
    user_id VARCHAR(128) NOT NULL,
    declaration_id VARCHAR(128) NOT NULL,
    confirmation_version VARCHAR(80) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active','retracted')),
    correction_event_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id,declaration_id),
    CONSTRAINT uq_cultural_user_correction UNIQUE (user_id,correction_event_id)
);
CREATE INDEX IF NOT EXISTS ix_cultural_declarations_user_status ON cultural_declarations(user_id,status);
CREATE TABLE IF NOT EXISTS cultural_requirements (
    user_id VARCHAR(128) NOT NULL,
    requirement_id VARCHAR(128) NOT NULL,
    declaration_id VARCHAR(128) NOT NULL,
    attribute VARCHAR(160) NOT NULL,
    kind VARCHAR(32) NOT NULL CHECK (kind IN ('required_attribute','forbidden_attribute')),
    hard BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id,requirement_id),
    CONSTRAINT fk_cultural_requirement_declaration FOREIGN KEY(user_id,declaration_id)
        REFERENCES cultural_declarations(user_id,declaration_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_cultural_requirements_declaration ON cultural_requirements(user_id,declaration_id);
CREATE TABLE IF NOT EXISTS cultural_correction_events (
    event_id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    declaration_id VARCHAR(128) NOT NULL,
    correction_event_id VARCHAR(128) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_cultural_correction_event UNIQUE (user_id,correction_event_id),
    CONSTRAINT fk_cultural_correction_declaration FOREIGN KEY(user_id,declaration_id)
        REFERENCES cultural_declarations(user_id,declaration_id) ON DELETE CASCADE
);
