-- PostgreSQL schema for owner-scoped AM/PM routines and revocable share links.
CREATE TABLE IF NOT EXISTS skincare_routines (
    owner_user_id VARCHAR(128) NOT NULL,
    routine_id VARCHAR(36) NOT NULL,
    name VARCHAR(120) NOT NULL,
    description VARCHAR(300),
    morning_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    evening_steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id, routine_id)
);
CREATE INDEX IF NOT EXISTS ix_skincare_routines_owner_status_updated
    ON skincare_routines(owner_user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS skincare_routine_shares (
    share_id BIGSERIAL PRIMARY KEY,
    owner_user_id VARCHAR(128) NOT NULL,
    routine_id VARCHAR(36) NOT NULL,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_skincare_routine_share_routine
        FOREIGN KEY(owner_user_id, routine_id)
        REFERENCES skincare_routines(owner_user_id, routine_id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_skincare_routine_shares_owner_routine
    ON skincare_routine_shares(owner_user_id, routine_id, revoked_at);
CREATE INDEX IF NOT EXISTS ix_skincare_routine_shares_expiry
    ON skincare_routine_shares(expires_at);
