# Production release evidence

The machine-readable source of truth is [release-gates.json](release-gates.json). It contains 16 required gates and is **blocked** because there is no complete, verified production evidence package in this repository. The canonical provider-neutral deployment inventory is [infrastructure/deployment/canonical-stack.json](../../infrastructure/deployment/canonical-stack.json); it is not an executable deployment or operational proof.

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
