-- Add provider-neutral provenance and publication lifecycle metadata.
-- Existing records remain unclassified and private-only until independently reviewed.
ALTER TABLE asset_objects
  ADD COLUMN IF NOT EXISTS asset_role varchar(20) NOT NULL DEFAULT 'unclassified',
  ADD COLUMN IF NOT EXISTS source_asset_id varchar(36),
  ADD COLUMN IF NOT EXISTS source_sha256 varchar(64),
  ADD COLUMN IF NOT EXISTS transformation_name varchar(80),
  ADD COLUMN IF NOT EXISTS transformation_version varchar(80),
  ADD COLUMN IF NOT EXISTS consent_receipt_id varchar(160),
  ADD COLUMN IF NOT EXISTS consent_version varchar(80),
  ADD COLUMN IF NOT EXISTS masking_attestation_id varchar(160),
  ADD COLUMN IF NOT EXISTS masking_model_sha256 varchar(64),
  ADD COLUMN IF NOT EXISTS human_privacy_review_receipt_id varchar(160),
  ADD COLUMN IF NOT EXISTS human_privacy_reviewer_ref varchar(160),
  ADD COLUMN IF NOT EXISTS human_privacy_reviewed_at timestamptz,
  ADD COLUMN IF NOT EXISTS publication_scope varchar(32) NOT NULL DEFAULT 'private_only',
  ADD COLUMN IF NOT EXISTS publication_state varchar(24) NOT NULL DEFAULT 'private_only',
  ADD COLUMN IF NOT EXISTS publication_surface varchar(32),
  ADD COLUMN IF NOT EXISTS revoked_at timestamptz;

ALTER TABLE asset_objects
  ADD CONSTRAINT ck_asset_role
    CHECK (asset_role IN ('unclassified','source','derivative','representation')),
  ADD CONSTRAINT ck_asset_publication_scope
    CHECK (publication_scope IN ('private_only','approved_public')),
  ADD CONSTRAINT ck_asset_publication_state
    CHECK (publication_state IN ('private_only','pending_review','approved','published','revoked')),
  ADD CONSTRAINT ck_asset_publication_revocation
    CHECK ((publication_state = 'revoked') = (revoked_at IS NOT NULL)),
  ADD CONSTRAINT ck_asset_publication_evidence
    CHECK (
      publication_state NOT IN ('approved','published')
      OR (
        content_type = 'image/png'
        AND publication_scope = 'approved_public'
        AND publication_surface IS NOT NULL
        AND consent_receipt_id IS NOT NULL
        AND consent_version IS NOT NULL
        AND masking_attestation_id IS NOT NULL
        AND masking_model_sha256 IS NOT NULL
        AND length(masking_model_sha256) = 64
        AND human_privacy_review_receipt_id IS NOT NULL
        AND human_privacy_reviewer_ref IS NOT NULL
        AND human_privacy_reviewed_at IS NOT NULL
      )
    ),
  ADD CONSTRAINT ck_asset_publication_surface
    CHECK (publication_surface IS NULL OR publication_surface IN ('public_profile','community_feed','marketplace','merchant_surface','shared_link'));

CREATE INDEX IF NOT EXISTS ix_asset_publication_state
  ON asset_objects(publication_scope, publication_state, status);
