# Twin mesh validation boundary — 18 November 2026

**Status:** structural preflight is implemented as a separate private service. Full body validation and Registry attestation remain blocked.

## Decision

The generation/orchestration service must not hold the Registry validation HMAC secret. A generator can return an artifact and provenance, but it must not be able to sign its own validation claim. Twin Registry continues to verify the HMAC and independently recheck consent and private Asset Service ownership.

\`\`\`text
Generator/orchestrator
  -> upload GLB to private Asset Service
  -> independent validator reads exact private bytes
  -> validator checks artifact digest + GLB geometry + privacy profile
  -> validator completes body-coverage, scale and privacy evidence
  -> validator alone issues HMAC over the canonical Registry fields
  -> Twin Registry verifies HMAC, current consent and owner/purpose/Twin asset binding
\`\`\`

Only the first structural-preflight stage is implemented here. The new service performs resource-bound consent/version verification, retrieves the actual GLB bytes through Asset Service, verifies the digest, parses GLB 2.0, inspects triangle geometry and rejects malformed, degenerate or non-manifold content. It rejects explicit images, textures, extension/extra payloads and common image signatures.

## Important limits

The preflight does not prove full human-body surface coverage, anatomical correspondence, real-world scale, fit accuracy, identity fidelity or absence of all sensitive data. It does not fetch source photos for byte comparison. Those results are returned as \`null\` / unverified, not \`true\`.

The service therefore always sets \`registry_eligible=false\`, issues no \`MeshValidationReceipt\`, and produces no HMAC. It has no Registry registration client and no Registry signing secret. This is intentional fail-closed behavior, not a temporary UI flag.

## Contract change

\`registry_registration_payload(...)\` in the Virtual Twin generation contract now accepts a 64-character \`validation_attestation_hmac\` produced by the independent validator. It validates the generation bundle and creates the canonical Registry body, but never computes a signature or receives the shared signing secret. Twin Registry remains the signature verifier.

The validator must eventually hash the exact canonical receipt and sign the canonical Registry body expected by \`services/twin-registry/app/main.py\`. Its secret must be unavailable to the generator, browser and provider. A future signer must not be added until body-coverage, scale, exact-source non-embedding and sensitive-data privacy tests are independently evidenced.

## Remaining acceptance work

- Qualify and contract a commercial body/avatar generator. No current candidate is selected or approved.
- Implement representative, independently assessed body-surface coverage and landmark validation.
- Calibrate scale against independent capture references; a glTF unit declaration is not a measurement.
- Compare the full source asset set to the GLB payload and test non-embedding.
- Run a privacy leakage scan with documented test corpus and false-negative rates.
- Add validator-only HMAC issuance; test that a generator/orchestrator cannot mint a valid attestation.
- Deploy behind private HTTPS, separate and rotate keys, test timeouts/revocation/deletion and restore.

Until then, persistent Twin registration, preview and Virtual Try-On remain unavailable. Keep the Blue Flame as the pre-Twin state.
