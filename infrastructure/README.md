# Infrastructure and canonical deployment

**Status: deployment inventory established; production deployment remains blocked.**

The single source of truth for the intended Cirvanna service/dependency graph is [deployment/canonical-stack.json](deployment/canonical-stack.json). It inventories canonical service owners, build contexts, exposure boundaries, data stores, provider dependencies and release gates. Provider-specific overlays must derive from this inventory; do not create competing service lists in individual deployment files.

The manifest is intentionally a provider-neutral inventory, not an executable deployment, Docker Compose stack, Kubernetes release, or proof that any service is running. It currently records no selected production platform, release commit, service IDs, database provisioning, secret bindings, live provider configuration, monitoring, recovery owner, or verified backup/restore. Its release state must remain blocked until those facts are independently evidenced.

## Deployment rules

1. The Marketplace BFF is the only public browser ingress. Catalog, Commerce, identity, decision, privacy, image, recommendation, and model services remain private.
2. Each service's owning README and Dockerfile define its build requirements. A Dockerfile's presence is not proof of a working build; `build_context_verified_by_ci` identifies only contexts covered by existing repository workflows.
3. Every durable store has one canonical owning service. Do not collapse Catalog, Commerce, identity-learning, privacy-governance, NPL, or Cultural Identity ownership into an unreviewed shared schema.
4. Provider readiness must be checked by authenticated operation-specific probes and real staging transactions. An HTTP `/ready` success alone is availability evidence, not successful operation.
5. Production credentials must be injected from the approved secret manager. Never commit credentials, customer data, model weights, or generated datasets.
6. The canonical release record must bind the exact Git commit, image digests, migration revisions, provider versions, database IDs, recovery objectives, alert owners, and rollback procedure.
7. Do not mark a release gate passed from CI output, mocks, an inventory row, or a provider's self-reported configuration.

## Current infrastructure blockers

- No single production deployment environment or canonical deployment commit is verified.
- Catalog, Commerce, identity-learning, privacy-governance and other required durable stores still need approved provisioning and restore drills.
- The identity provider and Stripe staging lifecycle need real browser/session and payment/webhook verification.
- FX, tax, fulfilment, safety, FCI, jurisdiction, content lifecycle, masking-attestation, guardian and image-rights providers need configuration and operation-level verification before their dependent features are enabled.
- Central logs, traces, metrics, alert routing, incident ownership, on-call, SLOs, rate limits, secret rotation, rollback and failure drills are not yet operationally evidenced.

## Validation

Run:

```bash
python scripts/validate_canonical_stack.py
python -m unittest discover -s tests/architecture -v
```

The validator checks inventory integrity, dependency references, service DAGs, build paths and the one-public-ingress invariant. It does not certify build output, production provisioning, network policy, provider readiness, database recovery, or a live deployment.
