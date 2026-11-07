-- Preserve Commerce provenance for purchased wardrobe line items.
ALTER TABLE wardrobe_items
    ADD COLUMN IF NOT EXISTS commerce_order_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS commerce_order_item_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS purchase_event_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS purchase_quantity INTEGER,
    ADD COLUMN IF NOT EXISTS purchase_currency VARCHAR(3),
    ADD COLUMN IF NOT EXISTS purchase_unit_price_minor INTEGER,
    ADD COLUMN IF NOT EXISTS purchase_paid_at VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_wardrobe_owner_commerce_line
    ON wardrobe_items(owner_user_id, commerce_order_item_id);
DO $purchase_provenance$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_wardrobe_purchase_provenance_complete'
          AND conrelid = 'wardrobe_items'::regclass
    ) THEN
        ALTER TABLE wardrobe_items
            ADD CONSTRAINT ck_wardrobe_purchase_provenance_complete
            CHECK (
                (commerce_order_id IS NULL AND commerce_order_item_id IS NULL
                 AND purchase_event_id IS NULL AND purchase_quantity IS NULL
                 AND purchase_currency IS NULL AND purchase_unit_price_minor IS NULL
                 AND purchase_paid_at IS NULL)
                OR
                (commerce_order_id IS NOT NULL AND commerce_order_item_id IS NOT NULL
                 AND purchase_event_id IS NOT NULL AND purchase_quantity >= 1
                 AND purchase_currency IS NOT NULL AND purchase_unit_price_minor >= 0
                 AND purchase_paid_at IS NOT NULL)
            );
    END IF;
END
$purchase_provenance$;
