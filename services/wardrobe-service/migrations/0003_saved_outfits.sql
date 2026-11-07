-- User-owned saved outfits. Pieces are references to active wardrobe items, never copied catalogue facts.
CREATE TABLE IF NOT EXISTS wardrobe_outfits (
    owner_user_id VARCHAR(128) NOT NULL,
    outfit_id VARCHAR(128) NOT NULL,
    name VARCHAR(160) NOT NULL,
    pieces JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    last_command_id VARCHAR(128),
    last_command_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id, outfit_id),
    UNIQUE (owner_user_id, last_command_id),
    CHECK (jsonb_typeof(pieces) = 'array'),
    CHECK (jsonb_array_length(pieces) >= 1)
);
CREATE INDEX IF NOT EXISTS ix_wardrobe_outfit_owner_status
    ON wardrobe_outfits(owner_user_id,status);
