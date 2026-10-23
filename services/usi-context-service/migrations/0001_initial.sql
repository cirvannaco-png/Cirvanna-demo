CREATE TABLE usi_profiles (
    user_id VARCHAR(128) PRIMARY KEY,
    profile_id VARCHAR(128) NOT NULL UNIQUE,
    version VARCHAR(64) NOT NULL,
    preferences JSONB NOT NULL,
    eepl_policy JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE usi_contexts (
    user_id VARCHAR(128) PRIMARY KEY,
    age_years INTEGER NULL CHECK (age_years IS NULL OR (age_years >= 0 AND age_years <= 125)),
    location VARCHAR(120) NULL,
    occasion VARCHAR(120) NULL,
    climate VARCHAR(120) NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE usi_change_events (
    event_id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    source_version VARCHAR(64) NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_usi_change_events_user_id ON usi_change_events(user_id);
