SET search_path TO identity_private;

-- Cover the consent-receipt foreign keys used by deletion and context lookups.
CREATE INDEX IF NOT EXISTS ix_identity_tal_events_consent_receipt
  ON identity_tal_events(consent_receipt_id);
CREATE INDEX IF NOT EXISTS ix_identity_pnelly_conversation_consent_receipt
  ON identity_pnelly_conversations(consent_receipt_id);
