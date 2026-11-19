# Production release evidence

The machine-readable source of truth is [release-gates.json](release-gates.json). It contains 23 required gates and is **blocked** because there is no complete, verified production evidence package in this repository. The canonical provider-neutral deployment inventory is [infrastructure/deployment/canonical-stack.json](../../infrastructure/deployment/canonical-stack.json); it is not an executable deployment or operational proof.

The current registry has **23/23 required gates blocked** and no exact-release-commit evidence references. This is the correct state: CI success and implementation foundations do not satisfy provider approval, production infrastructure, identity, payment, privacy, operational recovery or deployed end-to-end acceptance.

## How to close a gate

A gate may be marked `passed` only when:

- its acceptance criteria have been met in the actual target environment;
- the evidence references are reviewable (for example, CI run, migration log, redacted staging report, restore drill record, signed provider report, or approved operating procedure);
- `verified_commit` is the full 40-character commit SHA tested by that evidence; and
- the evidence is reviewed by the role listed as the gate owner.

Use `in_progress` while work is underway. Keep `blocked` when a dependency, approval, provider, or evidence artifact is absent. Do not use an assumed, mocked, local-only, or stale test as release evidence.

Evidence must not contain secrets, customer data, raw identity tokens, or unredacted personal information. Store sensitive artifacts in an approved private evidence system and put only a safe reference/identifier in the registry.

## Commands

Validate the registry structure and report the current blockers:

```bash
python scripts/validate_release_gates.py
```

Fail a release check unless every required gate is passed and carries evidence for the exact commit:

```bash
python scripts/validate_release_gates.py --require-all-passed
```

The release command is intentionally stricter than normal CI: ordinary pull requests can improve the architecture while production remains blocked. The production runbook remains [marketplace-production-readiness.md](../marketplace-production-readiness.md). The expanded system gaps and acceptance criteria are in [system-readiness-and-quality-2026-11-09.md](../architecture/system-readiness-and-quality-2026-11-09.md).

## Change control

Gate definitions and acceptance criteria change through reviewed PRs. Do not delete a gate to make the validator pass. Any scope reduction requires explicit product and risk-owner approval and an ADR describing the revised launch boundary. A release record must be updated only after evidence is collected, not in anticipation of deployment.


## Rollback evidence

The operational rollback procedure is [release-rollback-procedure.md](../operations/release-rollback-procedure.md). It separates application rollback from database recovery and defines containment, immutable image restoration, schema compatibility, critical-path checks and independent approval.

A new event must be recorded using [rollback-evidence-template.json](../operations/rollback-evidence-template.json). The template is intentionally marked not_executed; it is not evidence that a rollback has happened. A passed record requires the exact service inventory, a distinct immutable SHA-256 image digest per service for both releases, an explicit database recovery strategy, schema compatibility/restore and external-event reconciliation evidence, measured RPO/RTO, and independent approval.

Validate the evidence record:

```bash
python scripts/validate_rollback_evidence.py
```

Require a complete, passed exercise for release sign-off (this must fail until a real evidence record replaces the unexecuted template):

```bash
python scripts/validate_rollback_evidence.py --require-passed
```

The current source-control reconciliation snapshot is [pr-branch-reconciliation-2026-11-19.md](pr-branch-reconciliation-2026-11-19.md). It does not replace PR review or release-gate evidence.


## Strict release-candidate check

The manual [Release candidate readiness workflow](../../.github/workflows/release-candidate-readiness.yml) assesses a supplied full commit SHA without deploying it. It checks the exact checkout, runs the source-lineage audit **without** `--allow-unreconciled`, requires all 23 gates to be passed with exact-commit evidence, and requires a real rollback exercise. It is intentionally separate from normal pull-request CI: normal architecture validation may report lineage differences during migration, but that permissive result does not pass REL-01.

Run it from GitHub Actions on `main`, supplying the exact candidate SHA. The workflow is expected to fail while source mappings, release gates or rollback evidence remain incomplete.

## Remediation sequence

See [Production release gate remediation plan](production-gate-remediation-plan-2026-11-19.md) for gate dependencies, ordered work, evidence requirements, current infrastructure findings and stop conditions. The registry remains the machine-readable source of truth; the plan does not change any gate status.
