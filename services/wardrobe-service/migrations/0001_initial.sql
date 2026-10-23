CREATE TABLE IF NOT EXISTS wardrobe_items (
    owner_user_id VARCHAR(128) NOT NULL,
    item_id VARCHAR(128) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    category VARCHAR(80) NOT NULL,
    attributes JSON NOT NULL,
    catalog_product_id VARCHAR(128),
    image_asset_id VARCHAR(160),
    image_storage_consent BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(16) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived','deleted')),
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    last_command_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id, item_id),
    CONSTRAINT uq_wardrobe_owner_command UNIQUE (owner_user_id, last_command_id),
    CONSTRAINT ck_wardrobe_image_consent CHECK (image_asset_id IS NULL OR image_storage_consent = TRUE)
);
CREATE INDEX IF NOT EXISTS ix_wardrobe_owner_status ON wardrobe_items(owner_user_id,status);
CREATE TABLE IF NOT EXISTS wardrobe_asset_deletion_outbox (
    outbox_id BIGSERIAL PRIMARY KEY,
    owner_user_id VARCHAR(128) NOT NULL,
    item_id VARCHAR(128) NOT NULL,
    asset_id VARCHAR(160) NOT NULL,
    command_id VARCHAR(128) NOT NULL,
    state VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processing','completed','failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_until TIMESTAMPTZ,
    lease_owner VARCHAR(128),
    last_error_code VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_wardrobe_asset_delete_command UNIQUE (owner_user_id,item_id,command_id),
    CONSTRAINT fk_wardrobe_deletion_item FOREIGN KEY(owner_user_id,item_id)
        REFERENCES wardrobe_items(owner_user_id,item_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_wardrobe_asset_delete_state ON wardrobe_asset_deletion_outbox(state,created_at);

CREATE TABLE IF NOT EXISTS wardrobe_worker_heartbeats (
    worker_id VARCHAR(128) PRIMARY KEY,
    last_seen_at TIMESTAMPTZ NOT NULL
);
