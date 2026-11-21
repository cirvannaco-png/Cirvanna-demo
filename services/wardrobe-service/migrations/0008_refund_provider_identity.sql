-- Support verified Stripe refund-object events that precede charge.refunded.
-- Keep the exact provider object identity; do not mislabel a refund ID as a charge ID.
ALTER TABLE wardrobe_purchase_refund_snapshots
    ALTER COLUMN charge_id DROP NOT NULL;
ALTER TABLE wardrobe_purchase_refund_snapshots
    ADD COLUMN IF NOT EXISTS refund_id VARCHAR(180);
