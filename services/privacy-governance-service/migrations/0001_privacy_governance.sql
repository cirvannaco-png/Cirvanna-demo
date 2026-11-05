-- Apply to the approved shared PostgreSQL instance after database-owner review.
-- No image bytes, face embeddings, raw status tokens, verification references or raw IPs are stored.
CREATE TABLE IF NOT EXISTS privacy_consent_records (
  consent_id VARCHAR(36) PRIMARY KEY,
  subject_id VARCHAR(128) NOT NULL,
  resource_id VARCHAR(160),
  granted_scopes JSONB NOT NULL,
  photographed_people_status VARCHAR(24) NOT NULL,
  consent_version VARCHAR(80) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  guardian_authority_verified BOOLEAN NOT NULL DEFAULT FALSE,
  guardian_verification_digest VARCHAR(64),
  granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_privacy_consent_subject ON privacy_consent_records(subject_id);
CREATE INDEX IF NOT EXISTS ix_privacy_consent_active ON privacy_consent_records(active);

CREATE TABLE IF NOT EXISTS privacy_policy_bundles (
  bundle_id VARCHAR(36) PRIMARY KEY,
  jurisdiction VARCHAR(64) NOT NULL,
  policy_version VARCHAR(80) NOT NULL,
  effective_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  guardian_consent_required_for_minor BOOLEAN NOT NULL,
  child_product_discovery_allowed BOOLEAN NOT NULL,
  lawful_basis_approved BOOLEAN NOT NULL,
  cross_border_transfer_allowed BOOLEAN NOT NULL,
  rights_response_deadline_hours INTEGER NOT NULL CHECK (rights_response_deadline_hours BETWEEN 1 AND 8760),
  approved_by VARCHAR(160) NOT NULL,
  legal_review_reference VARCHAR(160) NOT NULL,
  payload JSONB NOT NULL,
  policy_sha256 VARCHAR(64) NOT NULL,
  signature_sha256 VARCHAR(64) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_privacy_policy_jurisdiction_version UNIQUE(jurisdiction, policy_version),
  CONSTRAINT ck_privacy_policy_validity CHECK (expires_at > effective_at)
);
CREATE INDEX IF NOT EXISTS ix_privacy_policy_current ON privacy_policy_bundles(jurisdiction, active, effective_at, expires_at);

CREATE TABLE IF NOT EXISTS privacy_image_rights_cases (
  request_id VARCHAR(36) PRIMARY KEY,
  asset_id VARCHAR(160) NOT NULL,
  asset_reference_digest VARCHAR(64) NOT NULL,
  request_type VARCHAR(12) NOT NULL CHECK (request_type IN ('report', 'removal')),
  reason_code VARCHAR(32) NOT NULL,
  requester_relationship VARCHAR(32) NOT NULL,
  jurisdiction_hint_digest VARCHAR(64),
  status VARCHAR(24) NOT NULL,
  quarantined BOOLEAN NOT NULL DEFAULT FALSE,
  status_token_digest VARCHAR(64) NOT NULL,
  resolution_code VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_privacy_rights_asset_created ON privacy_image_rights_cases(asset_id, created_at);
CREATE INDEX IF NOT EXISTS ix_privacy_rights_status_created ON privacy_image_rights_cases(status, created_at);

CREATE TABLE IF NOT EXISTS privacy_governance_audit_events (
  event_id VARCHAR(36) PRIMARY KEY,
  event_type VARCHAR(64) NOT NULL,
  object_type VARCHAR(32) NOT NULL,
  object_id VARCHAR(36) NOT NULL,
  actor_type VARCHAR(24) NOT NULL,
  metadata_safe JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_privacy_audit_event_type ON privacy_governance_audit_events(event_type);
CREATE INDEX IF NOT EXISTS ix_privacy_audit_object_id ON privacy_governance_audit_events(object_id);
