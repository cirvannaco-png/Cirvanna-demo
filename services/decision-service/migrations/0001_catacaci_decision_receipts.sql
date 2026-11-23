CREATE SCHEMA IF NOT EXISTS decision_private;
REVOKE ALL ON SCHEMA decision_private FROM PUBLIC;

-- Durable, append-only CaTaCaCi/CAL decision receipts.
-- Apply with a dedicated least-privileged DECISION_AUDIT_DATABASE_URL role.
CREATE TABLE IF NOT EXISTS decision_private.catacaci_decision_receipts (
    receipt_id UUID PRIMARY KEY,
    request_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('SHOW', 'BLOCK', 'REVIEW')),
    may_display BOOLEAN NOT NULL,
    eepl_policy_id TEXT NOT NULL,
    eepl_policy_version TEXT NOT NULL,
    cal_policy_id TEXT NOT NULL,
    cal_policy_version TEXT NOT NULL,
    minimum_fit_confidence DOUBLE PRECISION NOT NULL CHECK (minimum_fit_confidence BETWEEN 0 AND 1),
    maximum_fit_confidence_disagreement DOUBLE PRECISION NOT NULL CHECK (maximum_fit_confidence_disagreement BETWEEN 0 AND 1),
    arbitration_contract_version TEXT NOT NULL,
    pipeline_contract_version TEXT NOT NULL,
    candidate_snapshot_sha256 CHAR(64) NOT NULL,
    catalog_version INTEGER NULL CHECK (catalog_version IS NULL OR catalog_version > 0),
    evaluated_signals JSONB NOT NULL,
    reasons JSONB NOT NULL,
    receipt_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_catacaci_receipt_show_only CHECK (may_display = (verdict = 'SHOW')),
    CONSTRAINT uq_catacaci_receipt_request_candidate UNIQUE (request_id, candidate_id)
);
CREATE INDEX IF NOT EXISTS ix_catacaci_receipts_candidate_created
    ON decision_private.catacaci_decision_receipts (candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_catacaci_receipts_verdict_created
    ON decision_private.catacaci_decision_receipts (verdict, created_at DESC);

-- Keep the private schema inaccessible to browser-facing Supabase roles.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON SCHEMA decision_private FROM anon;
        REVOKE ALL ON ALL TABLES IN SCHEMA decision_private FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON SCHEMA decision_private FROM authenticated;
        REVOKE ALL ON ALL TABLES IN SCHEMA decision_private FROM authenticated;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='cirvanna_decision_audit') THEN
        GRANT USAGE ON SCHEMA decision_private TO cirvanna_decision_audit;
        GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA decision_private TO cirvanna_decision_audit;
    END IF;
END;
$$;
ALTER DEFAULT PRIVILEGES IN SCHEMA decision_private REVOKE ALL ON TABLES FROM PUBLIC;
