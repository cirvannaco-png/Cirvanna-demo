CREATE SCHEMA IF NOT EXISTS decision_private;
REVOKE ALL ON SCHEMA decision_private FROM PUBLIC;

-- Durable CaTaCaCi governance state: CAM replay audit, privacy-budgeted CIL, and VSL approvals.
CREATE TABLE IF NOT EXISTS decision_private.catacaci_cam_audits (
    audit_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    observed_verdict TEXT NOT NULL CHECK (observed_verdict IN ('show','block','review')),
    simulated_verdict TEXT NOT NULL CHECK (simulated_verdict IN ('show','block','review')),
    changed_signal_ids JSONB NOT NULL,
    changed_signal_overrides JSONB NOT NULL,
    simulated_signal_snapshot_sha256 CHAR(64) NOT NULL,
    policy_version TEXT NOT NULL,
    replay_version TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    interpretation TEXT NOT NULL CHECK (interpretation='counterfactual_scenario_not_observed_causality'),
    audit_sha256 CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_catacaci_cam_candidate ON decision_private.catacaci_cam_audits(candidate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS decision_private.catacaci_cil_contributions (
    event_id TEXT PRIMARY KEY,
    cohort_key TEXT NOT NULL,
    period_start DATE NOT NULL,
    contributor_hash CHAR(64) NOT NULL,
    outcome_success BOOLEAN NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    UNIQUE(cohort_key, period_start, contributor_hash)
);
CREATE INDEX IF NOT EXISTS ix_catacaci_cil_cohort_period ON decision_private.catacaci_cil_contributions(cohort_key, period_start);

CREATE TABLE IF NOT EXISTS decision_private.catacaci_cil_privacy_budget (
    cohort_key TEXT NOT NULL,
    period_start DATE NOT NULL,
    epsilon_spent DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (epsilon_spent >= 0),
    epsilon_limit DOUBLE PRECISION NOT NULL CHECK (epsilon_limit > 0),
    PRIMARY KEY(cohort_key, period_start),
    CHECK (epsilon_spent <= epsilon_limit + 0.000000001)
);

CREATE TABLE IF NOT EXISTS decision_private.catacaci_cil_aggregates (
    aggregate_id UUID PRIMARY KEY,
    cohort_key TEXT NOT NULL,
    period_start DATE NOT NULL,
    suppressed BOOLEAN NOT NULL,
    noisy_contributor_count INTEGER NULL CHECK (noisy_contributor_count IS NULL OR noisy_contributor_count >= 0),
    noisy_success_rate DOUBLE PRECISION NULL CHECK (noisy_success_rate IS NULL OR noisy_success_rate BETWEEN 0 AND 1),
    epsilon DOUBLE PRECISION NOT NULL CHECK (epsilon > 0),
    mechanism TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(cohort_key, period_start),
    CHECK (
      (suppressed AND noisy_contributor_count IS NULL AND noisy_success_rate IS NULL)
      OR
      (NOT suppressed AND noisy_contributor_count IS NOT NULL AND noisy_success_rate IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS decision_private.catacaci_vsl_profiles (
    singleton_id SMALLINT PRIMARY KEY CHECK (singleton_id=1),
    version TEXT NOT NULL,
    priority_order JSONB NOT NULL,
    approved_by TEXT NOT NULL,
    approval_event_id TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
INSERT INTO decision_private.catacaci_vsl_profiles
(singleton_id, version, priority_order, approved_by, approval_event_id, updated_at)
VALUES (
  1, 'bootstrap-v1',
  '["safety","legal_eligibility","user_hard_constraint","npl_hard_negative","cultural_requirement","context_eligibility","identity_alignment","fit_confidence","other"]'::jsonb,
  'bootstrap', 'bootstrap-v1', now()
) ON CONFLICT (singleton_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS decision_private.catacaci_vsl_proposals (
    proposal_id TEXT PRIMARY KEY,
    base_version TEXT NOT NULL,
    proposed_version TEXT NOT NULL UNIQUE,
    proposed_order JSONB NOT NULL,
    rationale TEXT NOT NULL,
    proposer_id TEXT NOT NULL,
    proposal_sha256 CHAR(64) NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('proposed','approved','rejected','stale')),
    approver_id TEXT NULL,
    approval_event_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    decided_at TIMESTAMPTZ NULL,
    CHECK (approver_id IS NULL OR approver_id <> proposer_id)
);

CREATE TABLE IF NOT EXISTS decision_private.catacaci_vsl_events (
    event_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES catacaci_vsl_proposals(proposal_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('proposed','approved','rejected','stale')),
    actor_id TEXT NOT NULL,
    base_version TEXT NOT NULL,
    resulting_version TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE OR REPLACE FUNCTION decision_private.catacaci_reject_append_only_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'CaTaCaCi append-only governance record cannot be changed';
END;
$$;

DROP TRIGGER IF EXISTS trg_catacaci_receipts_append_only ON decision_private.catacaci_decision_receipts;
CREATE TRIGGER trg_catacaci_receipts_append_only
BEFORE UPDATE OR DELETE ON decision_private.catacaci_decision_receipts
FOR EACH ROW EXECUTE FUNCTION decision_private.catacaci_reject_append_only_mutation();

DROP TRIGGER IF EXISTS trg_catacaci_cam_append_only ON decision_private.catacaci_cam_audits;
CREATE TRIGGER trg_catacaci_cam_append_only
BEFORE UPDATE OR DELETE ON decision_private.catacaci_cam_audits
FOR EACH ROW EXECUTE FUNCTION decision_private.catacaci_reject_append_only_mutation();

DROP TRIGGER IF EXISTS trg_catacaci_cil_aggregates_append_only ON decision_private.catacaci_cil_aggregates;
CREATE TRIGGER trg_catacaci_cil_aggregates_append_only
BEFORE UPDATE OR DELETE ON decision_private.catacaci_cil_aggregates
FOR EACH ROW EXECUTE FUNCTION decision_private.catacaci_reject_append_only_mutation();

DROP TRIGGER IF EXISTS trg_catacaci_vsl_events_append_only ON decision_private.catacaci_vsl_events;
CREATE TRIGGER trg_catacaci_vsl_events_append_only
BEFORE UPDATE OR DELETE ON decision_private.catacaci_vsl_events
FOR EACH ROW EXECUTE FUNCTION decision_private.catacaci_reject_append_only_mutation();

-- Keep the private schema inaccessible to browser-facing Supabase roles.
REVOKE ALL ON ALL TABLES IN SCHEMA decision_private FROM PUBLIC;
DO $
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
        GRANT SELECT, INSERT ON decision_private.catacaci_decision_receipts,
            decision_private.catacaci_cam_audits,
            decision_private.catacaci_cil_contributions,
            decision_private.catacaci_cil_aggregates,
            decision_private.catacaci_vsl_events TO cirvanna_decision_audit;
        GRANT SELECT, INSERT, UPDATE ON decision_private.catacaci_cil_privacy_budget,
            decision_private.catacaci_vsl_profiles,
            decision_private.catacaci_vsl_proposals TO cirvanna_decision_audit;
    END IF;
END;
$$;
ALTER DEFAULT PRIVILEGES IN SCHEMA decision_private REVOKE ALL ON TABLES FROM PUBLIC;
