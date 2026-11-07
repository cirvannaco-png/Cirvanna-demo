# ADR-0011: Cirvanna backend and model-runtime selection

- Status: Accepted for implementation direction; infrastructure provisioning and commercial model clearance remain blocked
- Date: 2026-11-07

## Context

Cirvanna needs durable user-owned Twin metadata, private image assets, consent receipts, render-job state, and a GPU inference runtime. The repository already defines service boundaries for identity/consent, assets, Virtual Twin, and Virtual Try-On. The connected platform accounts were inspected before selecting infrastructure.

## Decision

1. **Do not create a parallel database merely to complete this feature.** Reuse the repository's existing managed Postgres integration where it is active and authoritative. The connected Supabase project currently reports `INACTIVE`; no schema or project mutation was performed.
2. **Neon is a candidate, not an active dependency.** The connected Neon account currently lists no projects. Neon may be selected for a new isolated backend only after project ownership, region, cost, data residency, and migration strategy are confirmed. Do not migrate existing identity, commerce, or wardrobe data by default.
3. **Private object storage is mandatory for person images, Twin source images, and try-on outputs.** Keep object keys opaque and private. Authorization must be mediated by the asset service; no browser-facing public bucket or direct user-supplied URL fetches. Neon Object Storage can be evaluated if a Neon project is approved; otherwise use the existing S3-compatible asset-service adapter and its configured provider.
4. **Hugging Face is the model artifact and optional compute provider, not the system of record.** The connected Hugging Face identity is a non-Pro personal account with no running jobs and no visible organizations. No GPU job or paid compute was launched.
5. **FASHN VTON 1.5 source is pinned to `7c0f10af3f91ad4048fe9729c470a13ef905d25a`.** The upstream VTON code/model and DWPose are tagged Apache-2.0. The required FASHN Human Parser package states that its model inherits the NVIDIA Source Code License for SegFormer. Commercial deployment is blocked until counsel or the license owner confirms the applicable terms or a compliant parser alternative is adopted.
6. **The GPU worker is not the consent authority.** The orchestrator must verify active, resource-bound consent and asset ownership before reading or sending user assets. The worker's boolean flags are defense-in-depth assertions only. Readiness must prove all model files, parser cache, CUDA and ONNX CUDA provider are available and the actual pipeline initializes offline.
7. **Persistent Twin and render orchestration must use durable records.** A render job must be created/claimed before GPU execution with owner-scoped idempotency. Deletion/revocation first blocks access, then uses a durable outbox/reconciler to delete objects and metadata with retryable, idempotent semantics.

## Consequences

- The current inactive Supabase project is not used for staging or production until restored through an approved operation.
- No Neon project, bucket, or database has been created.
- No Hugging Face GPU job has been launched; cost and hardware are not yet approved.
- Mock CI is not evidence of actual rendering quality or runtime readiness.
- A later integration PR must include resource-bound consent, authenticated subject derivation, private asset authorization, durable Twin/render records, deletion recovery, cross-user isolation tests, and a real inference evaluation before staging enablement.

## Evidence inspected

- Repository: `cirvannaco-png/Cirvanna-demo`
- Hugging Face model: `fashn-ai/fashn-vton-1.5`
- FASHN source commit: `7c0f10af3f91ad4048fe9729c470a13ef905d25a`
- Human parser license statement: NVIDIA Source Code License for SegFormer
- Connected Supabase project state: `INACTIVE`
- Connected Neon projects: none
- Connected Hugging Face account: personal non-Pro; no running jobs
