-- Extend the financial refund ledger to support full checkout captures
-- that include separate fulfilment and tax charges. Merchandise purchase lines
-- remain the ownership/provenance amount; refunds never imply physical returns.
ALTER TABLE wardrobe_purchase_refund_snapshots
    ADD COLUMN IF NOT EXISTS captured_total_minor INTEGER;

-- Existing single-currency/item-only orders had no separate charges.
UPDATE wardrobe_purchase_refund_snapshots
SET captured_total_minor = order_total_minor
WHERE captured_total_minor IS NULL;

ALTER TABLE wardrobe_purchase_refund_snapshots
    ALTER COLUMN captured_total_minor SET NOT NULL;

ALTER TABLE wardrobe_purchase_refund_snapshots
    DROP CONSTRAINT IF EXISTS ck_wardrobe_refund_amount_bounds;
ALTER TABLE wardrobe_purchase_refund_snapshots
    DROP CONSTRAINT IF EXISTS wardrobe_purchase_refund_snapshots_amount_refunded_minor_check;
ALTER TABLE wardrobe_purchase_refund_snapshots
    ADD CONSTRAINT ck_wardrobe_refund_captured_total_gte_merchandise
        CHECK (captured_total_minor >= order_total_minor);
ALTER TABLE wardrobe_purchase_refund_snapshots
    ADD CONSTRAINT ck_wardrobe_refund_amount_bounds
        CHECK (amount_refunded_minor > 0 AND amount_refunded_minor <= captured_total_minor);
