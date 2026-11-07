-- Owner-scoped, order-level financial refund snapshot.
-- A Stripe refund is not evidence of physical return or loss of garment possession.
CREATE TABLE IF NOT EXISTS wardrobe_purchase_refund_snapshots (
    owner_user_id VARCHAR(128) NOT NULL,
    order_id VARCHAR(36) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    provider_event_id VARCHAR(180) NOT NULL,
    payment_intent_id VARCHAR(180) NOT NULL,
    charge_id VARCHAR(180) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    order_total_minor INTEGER NOT NULL CHECK (order_total_minor > 0),
    amount_refunded_minor INTEGER NOT NULL
        CHECK (amount_refunded_minor > 0 AND amount_refunded_minor <= order_total_minor),
    refund_state VARCHAR(16) NOT NULL CHECK (refund_state IN ('partial_refund', 'refunded')),
    payload_hash VARCHAR(64) NOT NULL,
    refunded_at TIMESTAMPTZ NOT NULL,
    physical_return_confirmed BOOLEAN NOT NULL DEFAULT FALSE
        CHECK (physical_return_confirmed = FALSE),
    ownership_effect VARCHAR(32) NOT NULL DEFAULT 'financial_status_only'
        CHECK (ownership_effect = 'financial_status_only'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (owner_user_id, order_id),
    CONSTRAINT uq_wardrobe_purchase_refund_event UNIQUE (event_id),
    CONSTRAINT uq_wardrobe_purchase_refund_provider_event UNIQUE (provider_event_id)
);
CREATE INDEX IF NOT EXISTS ix_wardrobe_purchase_refund_event
    ON wardrobe_purchase_refund_snapshots(provider_event_id);
