-- NPL schema version 2: non-identifying receipts for completed user-data deletion.
CREATE TABLE IF NOT EXISTS npl_deletion_receipts (
    receipt_id VARCHAR(36) PRIMARY KEY,
    subject_digest CHAR(64) NOT NULL,
    deleted_preference_count INTEGER NOT NULL DEFAULT 0 CHECK (deleted_preference_count >= 0),
    deleted_rejection_count INTEGER NOT NULL DEFAULT 0 CHECK (deleted_rejection_count >= 0),
    deleted_correction_count INTEGER NOT NULL DEFAULT 0 CHECK (deleted_correction_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_npl_deletion_receipts_subject_digest
    ON npl_deletion_receipts(subject_digest);
