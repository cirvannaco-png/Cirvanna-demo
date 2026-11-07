-- Durable per-user PNELLY wardrobe exposure cycle state.
-- owner_user_id is bound by trusted internal ingress to the verified Commerce subject.
CREATE TABLE IF NOT EXISTS wardrobe_rotation_states (
    owner_user_id VARCHAR(128) PRIMARY KEY,
    cycle_number INTEGER NOT NULL CHECK (cycle_number >= 1),
    cycle_started_at TIMESTAMPTZ NOT NULL,
    surfaced_item_ids JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(surfaced_item_ids) = 'array'),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
