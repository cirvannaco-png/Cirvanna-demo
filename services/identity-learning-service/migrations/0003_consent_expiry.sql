-- Bound one-request image discovery consent to a server-enforced lifetime.
-- Apply after 0002_consent_bundles.sql. Existing long-lived Twin grants remain non-expiring.
ALTER TABLE identity_consent_bundles
  ADD COLUMN IF NOT EXISTS expires_at timestamptz;
CREATE INDEX IF NOT EXISTS ix_identity_consent_expiry_active
  ON identity_consent_bundles(expires_at)
  WHERE revoked_at IS NULL AND expires_at IS NOT NULL;
