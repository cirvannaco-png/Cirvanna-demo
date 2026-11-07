-- Preserve Commerce provenance for purchased wardrobe line items.
ALTER TABLE wardrobe_items
    ADD COLUMN IF NOT EXISTS commerce_order_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS commerce_order_item_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS purchase_event_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS purchase_quantity INTEGER;
CREATE UNIQUE INDEX IF NOT EXISTS uq_wardrobe_owner_commerce_line
    ON wardrobe_items(owner_user_id, commerce_order_item_id);
ALTER TABLE wardrobe_items
    ADD CONSTRAINT ck_wardrobe_purchase_provenance_complete
    CHECK (
        (commerce_order_id IS NULL AND commerce_order_item_id IS NULL
         AND purchase_event_id IS NULL AND purchase_quantity IS NULL)
        OR
        (commerce_order_id IS NOT NULL AND commerce_order_item_id IS NOT NULL
         AND purchase_event_id IS NOT NULL AND purchase_quantity >= 1)
    );
