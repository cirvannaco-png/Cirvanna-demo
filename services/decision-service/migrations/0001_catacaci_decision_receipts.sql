-- Durable, append-only CaTaCaCi/CAL decision receipts.
-- Apply with a dedicated least-privileged DECISION_AUDIT_DATABASE_URL role.
CREATE TABLE IF NOT EXISTS catacaci_decision_receipts (
    receipt_id UUID PRIMARY KEY,
    request_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('SHOW', 'BLOCK', 'REVIEW')),
    may_display BOOLEAN NOT NULL,
    eepl_policy_id TEXT NOT NULL,
    eepl_policy_version TEXT NOT NULL,
    cal_policy_id TEXT NOT NULL,
    cal_policy_version TEXT NOT NULL,
    arbitration_contract_version TEXT NOT NULL,
    pipeline_contract_version TEXT NOT NULL,
    candidate_snapshot_sha256 CHAR(64) NOT NULL,
    evaluated_signals JSONB NOT NULL,
    reasons JSONB NOT NULL,
    receipt_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_catacaci_receipt_show_only CHECK (may_display = (verdict = 'SHOW')),
    CONSTRAINT uq_catacaci_receipt_request_candidate UNIQUE (request_id, candidate_id)
);
CREATE INDEX IF NOT EXISTS ix_catacaci_receipts_candidate_created
    ON catacaci_decision_receipts (candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_catacaci_receipts_verdict_created
    ON catacaci_decision_receipts (verdict, created_at DESC);
