SET search_path TO identity_private;

-- DSI server-issued, one-time capture challenges and short-lived verification receipts.
-- Raw images, raw nonce values, attestation certificates and user media are never stored here.
BEGIN;

CREATE TABLE IF NOT EXISTS identity_dsi_capture_challenges (
  challenge_id varchar(80) PRIMARY KEY,
  subject_id varchar(128) NOT NULL,
  consent_id varchar(128) NOT NULL,
  consent_version varchar(80) NOT NULL,
  resource_id varchar(160) NOT NULL,
  purpose varchar(64) NOT NULL
    CHECK (purpose IN (
      'cosmetic_skin_analysis',
      'facial_geometry_analysis',
      'body_tone_analysis',
      'appearance_correction'
    )),
  required_scopes jsonb NOT NULL,
  consent_receipt_ids jsonb NOT NULL,
  nonce_sha256 varchar(64) NOT NULL
    CHECK (nonce_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  verification_receipt_id varchar(80),
  CONSTRAINT ck_identity_dsi_challenge_expiry CHECK (expires_at > created_at),
  CONSTRAINT ck_identity_dsi_challenge_consumption CHECK (
    (consumed_at IS NULL AND verification_receipt_id IS NULL)
    OR
    (consumed_at IS NOT NULL AND verification_receipt_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS ix_identity_dsi_capture_challenge_subject
  ON identity_dsi_capture_challenges(subject_id, created_at);
CREATE INDEX IF NOT EXISTS ix_identity_dsi_capture_challenge_expiry
  ON identity_dsi_capture_challenges(expires_at);

CREATE TABLE IF NOT EXISTS identity_dsi_capture_verification_receipts (
  receipt_id varchar(80) PRIMARY KEY,
  challenge_id varchar(80) NOT NULL UNIQUE
    REFERENCES identity_dsi_capture_challenges(challenge_id) ON DELETE CASCADE,
  subject_id varchar(128) NOT NULL,
  consent_id varchar(128) NOT NULL,
  consent_version varchar(80) NOT NULL,
  resource_id varchar(160) NOT NULL,
  purpose varchar(64) NOT NULL
    CHECK (purpose IN (
      'cosmetic_skin_analysis',
      'facial_geometry_analysis',
      'body_tone_analysis',
      'appearance_correction'
    )),
  consent_receipt_ids jsonb NOT NULL,
  manifest_sha256 varchar(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
  image_sha256 varchar(64) NOT NULL CHECK (image_sha256 ~ '^[0-9a-f]{64}$'),
  device_pipeline_fingerprint_sha256 varchar(64) NOT NULL
    CHECK (device_pipeline_fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
  key_attestation_challenge_sha256 varchar(64) NOT NULL
    CHECK (key_attestation_challenge_sha256 ~ '^[0-9a-f]{64}$'),
  play_integrity_request_hash varchar(64) NOT NULL
    CHECK (play_integrity_request_hash ~ '^[0-9a-f]{64}$'),
  package_name varchar(200) NOT NULL,
  package_certificate_sha256 varchar(64) NOT NULL
    CHECK (package_certificate_sha256 ~ '^[0-9a-f]{64}$'),
  app_version varchar(80) NOT NULL,
  sdk_version varchar(80) NOT NULL,
  verifier_policy_version varchar(80) NOT NULL,
  key_security_level varchar(32) NOT NULL,
  verified_boot_state varchar(32) NOT NULL,
  app_recognition_verdict varchar(40) NOT NULL,
  account_licensing_verdict varchar(40) NOT NULL,
  device_integrity_verdicts jsonb NOT NULL,
  issued_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  CONSTRAINT ck_identity_dsi_capture_receipt_expiry CHECK (expires_at > issued_at)
);

CREATE INDEX IF NOT EXISTS ix_identity_dsi_capture_receipt_subject
  ON identity_dsi_capture_verification_receipts(subject_id, issued_at);
CREATE INDEX IF NOT EXISTS ix_identity_dsi_capture_receipt_expiry
  ON identity_dsi_capture_verification_receipts(expires_at);

COMMIT;
