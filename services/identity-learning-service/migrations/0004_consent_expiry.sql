-- Optional, explicit consent expiry on the canonical resource-bound receipt.
-- Existing receipts remain readable with expires_at NULL for compatibility.
ALTER TABLE identity_tal_consent_receipts
  ADD COLUMN IF NOT EXISTS expires_at timestamptz;

CREATE INDEX IF NOT EXISTS ix_identity_tal_consent_expiry
  ON identity_tal_consent_receipts(expires_at)
  WHERE granted = true AND revoked_at IS NULL AND expires_at IS NOT NULL;
