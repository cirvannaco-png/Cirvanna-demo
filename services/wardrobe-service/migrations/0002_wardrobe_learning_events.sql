-- Wardrobe feedback audit mirror. Authoritative learning lives in USI/TAL and NPL.
CREATE TABLE IF NOT EXISTS wardrobe_learning_events (
    owner_user_id VARCHAR(128) NOT NULL,
    event_id VARCHAR(128) NOT NULL,
    item_id VARCHAR(128) NOT NULL,
    item_version INTEGER NOT NULL CHECK (item_version >= 1),
    signal VARCHAR(16) NOT NULL CHECK (signal IN ('like','dislike','avoid','modify','wear')),
    target_type VARCHAR(16) CHECK (target_type IS NULL OR target_type IN ('item','attribute')),
    target_value VARCHAR(180),
    consent_receipt_id VARCHAR(128) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    delivery_state VARCHAR(16) NOT NULL CHECK (delivery_state IN ('delivered','failed')),
    delivery_result JSONB,
    error_code VARCHAR(80),
    observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id,event_id)
);
CREATE INDEX IF NOT EXISTS ix_wardrobe_learning_owner_observed
    ON wardrobe_learning_events(owner_user_id,observed_at);
