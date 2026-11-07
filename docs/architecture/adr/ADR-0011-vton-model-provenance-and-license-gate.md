# ADR-0011: VTON model provenance and commercial license gate

- Status: Accepted
- Date: 2026-11-07
- Decision owners: Cirvanna architecture

## Context

Cirvanna's private VTON worker invokes FASHN VTON 1.5. The upstream repository is Apache-2.0, but its pipeline also loads the FASHN Human Parser. The parser's own README states that its model inherits NVIDIA's SegFormer license and directs users to review those terms. NVIDIA's SegFormer repository describes use as non-commercial research/evaluation only. The parser's Python package also auto-downloads its weights from Hugging Face unless separately staged and controlled.

An Apache-2.0 top-level model does not make the complete inference stack commercially clear. A commercial beauty-tech product must not treat a research-only dependency as cleared by association.

## Decision

1. Pin FASHN VTON source to an immutable 40-character Git commit. The current reviewed candidate is `7c0f10af3f91ad4048fe9729c470a13ef905d25a`; changing it requires a reviewed provenance update.
2. Bind the image's baked source commit to `FASHN_VTON_SOURCE_REF`. Runtime readiness fails if they differ.
3. Require `manifest.json` in the controlled model artifact directory. It must bind the same source commit and SHA-256 checksums for `model.safetensors`, `dwpose/yolox_l.onnx`, and `dwpose/dw-ll_ucoco_384.onnx`. Readiness fails on missing, mismatched, path-escaping or modified artifacts.
4. Readiness loads the actual pipeline after verifying configuration and artifacts. A directory existing is not sufficient evidence that inference can run.
5. Worker consent flags are transport-level assertions only. The trusted orchestrator remains authoritative for server-side consent receipt verification, resource ownership, revocation, and output access. The worker must not advertise itself as the consent authority.
6. Production mode remains blocked unless Cirvanna has written commercial permission for the FASHN Human Parser/SegFormer model or replaces it with a commercially cleared parser. The approval environment flag is an auditable deployment gate, not a substitute for obtaining the rights.
7. The human-parser Hugging Face model cache is not yet revision-pinned or covered by the core artifact manifest. This is an explicit unresolved release gate; a future change must stage a fixed parser revision and verify its checksum before enabling production.

## Consequences

- Mock CI can validate API contracts and checksum logic, but cannot prove GPU availability, model loading, visual quality, or commercial rights.
- No production deployment is authorized by this ADR.
- If NVIDIA does not grant suitable commercial rights, Cirvanna must replace the parser before enabling customer-facing FASHN inference.
- Consent, Twin ownership, asset persistence, idempotency, revocation and deletion remain orchestrator integration gates and are not solved by this worker hardening.

## References

- FASHN VTON 1.5 repository: https://github.com/fashn-AI/fashn-vton-1.5
- FASHN Human Parser repository: https://github.com/fashn-AI/fashn-human-parser
- NVIDIA SegFormer repository and license notice: https://github.com/NVlabs/SegFormer
