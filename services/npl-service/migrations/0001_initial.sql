-- NPL schema version 1. PostgreSQL; apply with a controlled migration tool.
CREATE TABLE IF NOT EXISTS npl_preferences (
    user_id VARCHAR(128) NOT NULL,
    preference_id VARCHAR(128) NOT NULL,
    target_type VARCHAR(16) NOT NULL CHECK (target_type IN ('item', 'attribute')),
    target_value VARCHAR(160) NOT NULL,
    source VARCHAR(32) NOT NULL CHECK (source IN ('user_declared', 'learned_rejection')),
    rejection_threshold INTEGER NOT NULL DEFAULT 3 CHECK (rejection_threshold >= 1),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    correction_event_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, preference_id)
);
CREATE INDEX IF NOT EXISTS ix_npl_preferences_user_active ON npl_preferences(user_id, active);

CREATE TABLE IF NOT EXISTS npl_rejection_events (
    event_id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    preference_id VARCHAR(128) NOT NULL,
    rejection_event_id VARCHAR(128) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_npl_rejection_user_event UNIQUE (user_id, rejection_event_id),
    CONSTRAINT fk_npl_rejection_preference FOREIGN KEY (user_id, preference_id)
        REFERENCES npl_preferences(user_id, preference_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_npl_rejection_preference ON npl_rejection_events(user_id, preference_id);

CREATE TABLE IF NOT EXISTS npl_correction_events (
    event_id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    preference_id VARCHAR(128) NOT NULL,
    correction_event_id VARCHAR(128) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_npl_correction_user_event UNIQUE (user_id, correction_event_id),
    CONSTRAINT fk_npl_correction_preference FOREIGN KEY (user_id, preference_id)
        REFERENCES npl_preferences(user_id, preference_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_npl_correction_preference ON npl_correction_events(user_id, preference_id);
