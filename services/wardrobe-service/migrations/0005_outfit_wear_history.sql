-- User-authorized outfit wear history with immutable item snapshots.
CREATE TABLE IF NOT EXISTS wardrobe_outfit_wear_events (
    owner_user_id VARCHAR(128) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    outfit_id VARCHAR(128) NOT NULL,
    outfit_version INTEGER NOT NULL CHECK (outfit_version >= 1),
    items_snapshot JSONB NOT NULL CHECK (jsonb_typeof(items_snapshot) = 'array'),
    context JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(context) = 'object'),
    consent_receipt_id VARCHAR(128) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    delivery_result JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(delivery_result) = 'array'),
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id, event_id)
);
CREATE INDEX IF NOT EXISTS ix_wardrobe_outfit_wear_owner_observed
    ON wardrobe_outfit_wear_events(owner_user_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS ix_wardrobe_outfit_wear_outfit
    ON wardrobe_outfit_wear_events(owner_user_id, outfit_id);
