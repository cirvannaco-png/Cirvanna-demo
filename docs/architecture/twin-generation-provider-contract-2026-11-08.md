# Virtual Twin generation provider contract

**Date:** 8 November 2026  
**Status:** contract and unit-test layer only. No generation provider, validator, asset provider, or customer-facing generation endpoint is activated by this change.

## Why this boundary exists

The current Virtual Twin service can return an ephemeral pose skeleton. That is not a persistent full-body representation. A successful pose response, a vendor job marked complete, or a file with a mesh extension is not evidence that a safe, usable full-body Twin exists.

This contract defines the minimum information that must agree before a generated artifact may be considered for registry registration. It is deliberately provider-neutral: selecting a commercial model, signing a data-processing agreement, or approving a model license is a separate decision.

## Trust sequence

1. **Authenticated subject.** The same-origin BFF derives the subject from the verified user session. The browser must not nominate or override the subject ID.
2. **Purpose-bound consent.** The trusted consent service verifies active consent for image processing, body measurements, and persistent Twin storage. The receipt is bound to the subject, consent version, and Twin resource. Recheck it at request time and before registration.
3. **Source authorization.** The private Asset Service authorizes every source image for the same subject and Twin. Generation receives opaque asset IDs, never caller-controlled URLs or filesystem paths.
4. **Generation.** A provider adapter returns metadata for a real, privately stored full_body_mesh artifact. It must bind the result to the exact subject, Twin, source asset set, pinned model revision, provider job, artifact asset ID, and SHA-256 digest. Raw image bytes and public URLs are not valid result fields.
5. **Independent validation.** A logically separate validator resolves the stored artifact from private storage and inspects the actual bytes. The orchestrator must call a separately configured validator endpoint using a distinct service credential; it must not accept a receipt supplied only inside the generator response. The receipt must bind to the same subject, consent version, Twin, source set, model revision, artifact ID, and artifact digest. The distinct validator_id check in the schema is an additional consistency guard, not cryptographic proof of independence. A provider's self-reported validated=true is insufficient.
6. **Registry.** Only after the independent checks pass may the orchestrator submit the validated artifact and validation receipt ID to the existing owner-scoped Twin registry. The registry must repeat current consent, mesh-validation, and private-asset authorization checks; it remains the persistence authority.
7. **Read and delete.** Preview/readback must re-authorize the asset for the current owner and purpose. Consent withdrawal or Twin deletion must immediately revoke authorization and queue deletion of source and derived assets.

## Required output binding

The executable schema is in services/virtual-twin/app/generation_contract.py.

The provider result must include:

- Exact subject_id and twin_id from the trusted command.
- A full_body_mesh representation type; a pose skeleton is rejected.
- Provider and provider-job identifiers.
- An opaque private artifact_asset_id, not an arbitrary URL or path.
- The exact source image asset set supplied to the job.
- A model version containing a lowercase SHA-256 revision digest.
- The SHA-256 digest of the stored mesh bytes.

The independent validation receipt must repeat the binding above and attest all required checks:

- Artifact can be retrieved and decoded.
- Geometry contains no non-finite values.
- Topology passes the validator's declared integrity rules.
- Required body-surface coverage is present.
- Scale is within documented human-body plausibility bounds.
- Privacy scan passes.
- Source photograph pixels are not embedded in the derived artifact.

Any mismatch, missing check, non-independent validator identity, expired consent, unknown owner, or unavailable private-asset service rejects registration. It must not fall back to a pose skeleton or a sample mesh.

## Job lifecycle

The contract permits only this forward progression:

queued → generating → validating → persisting → active

A job may move to failed or revoked from any nonterminal stage. An active Twin may be revoked. Failed and revoked jobs are terminal; retrying requires a new explicitly idempotent command rather than silently reviving a failed record.

The contract rejects skipped stages such as generating → active, backwards transitions, and transitions out of terminal states.

## Commercial and privacy qualification

Before selecting or enabling a provider, record and review:

- Exact model repository, commit/revision, weight digests, preprocessing code, and every transitive model/runtime dependency.
- Written commercial-use rights for the complete stack, not only the headline model. The existing Virtual Try-On parser licensing concern is not automatically resolved by choosing a different Twin generator.
- Data-processing terms, subprocessors, retention/deletion behavior, training-use restrictions, incident notification, and permitted processing regions.
- Whether source photographs leave Cirvanna-controlled infrastructure; encryption, private storage, transport, and deletion guarantees.
- Supported body coverage, pose and occlusion limits, subgroup evaluation, known failure modes, and an independent human-reviewed quality benchmark.

A provider must not be approved solely because it has a demo, an API, a permissive top-level model-card license, or attractive sample renders.

## Implementation boundary and release gates

This contract is **not yet wired to an HTTP endpoint or provider adapter**. It does not change /capabilities; persistent generation, preview, and Try-On remain unavailable. The current API must continue to report those capabilities as false until the full provider chain is deployed and independently tested.

Remaining integration work:

1. Select and approve a commercially cleared generation model and runtime.
2. Implement an isolated provider adapter with pinned revisions, bounded timeouts/concurrency, retries, and no source-photo logging.
3. Implement the independent validator and evidence receipt store.
4. Bind both services to the existing private Asset Service and exact asset digest.
5. Orchestrate consent checks, idempotent job persistence, validation, registry registration, and compensating deletion on failure.
6. Add authenticated Twin listing/read/preview and revocation flows, with deletion propagation evidence.
7. Run representative, consented human evaluation and physical Android acceptance tests.

Passing contract unit tests proves only that the integration payloads and state transitions are rejected when inconsistent. It does not prove model quality, legal rights, privacy posture, production infrastructure, or generated Twin capability.
