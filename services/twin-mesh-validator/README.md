# Cirvanna independent Twin mesh validator

**Status:** private-byte structural preflight implemented; full mesh acceptance and Registry attestation are intentionally unavailable.

This service is a separate trust boundary from the Virtual Twin generator/orchestrator. It reads the stored GLB from the private Asset Service, re-verifies the exact SHA-256, and inspects the actual GLB 2.0 bytes. It does not accept geometry claims supplied by a generation provider.

## Request flow

```text
Trusted Virtual Twin orchestration
  -> POST /internal/v1/preflight
  -> resource-bound consent verification (image_processing, body_measurements,
     virtual_twin_storage; resource_id must equal twin_id)
  -> Asset Service GET /internal/v1/assets/{asset_id}/content
     (subject_id + purpose=twin_representation + parent_id=twin_id)
  -> SHA-256 and GLB 2.0 structural/geometry inspection
  -> metadata-only preflight report; never a Registry create request
```

## Verified during preflight

- Actual private Asset Service bytes are read; owner, purpose and Twin-parent authorization are enforced again by Asset Service.
- Resource-bound consent and the exact consent version are rechecked before the validator reads the artifact.
- GLB magic, version, declared length, chunk order/alignment and bounded JSON/BIN layout.
- Exactly one embedded GLB binary buffer; external buffer URIs and unsupported chunks are rejected.
- Triangle primitives only; bounded vertex/triangle/accessor counts.
- Float32 VEC3 positions are decoded from the binary buffer and checked for finite coordinates and conservative numeric bounds.
- Triangle indices are decoded and range-checked. Degenerate triangles and edges shared by more than two faces are rejected.
- Explicit glTF images, textures, extensions, extras, external/data URIs and common embedded image signatures are rejected.

The topology result is deliberately narrow: it detects invalid indices, degenerate triangles and non-manifold edges. It does not prove watertightness, anatomical completeness, or that the surface represents a human body.

## Explicitly not verified

The response leaves these fields `null` (not false, and not passed):

- `body_coverage_valid`: needs independently validated body-surface/landmark coverage evidence.
- `scale_within_bounds`: needs capture calibration and an independent reference measurement.
- `source_photo_not_embedded`: needs byte-level comparison against the authorized source assets, not only a glTF resource scan.
- `privacy_scan_passed`: needs a separate sensitive-data/privacy scan and approved acceptance criteria.

Therefore `/internal/v1/preflight` always returns `registry_eligible=false`, `receipt_issued=false`, and `attestation=NOT_ISSUED`. Do not translate a successful structural preflight into a `MeshValidationReceipt`, a Registry HMAC, a saved Twin, or a Try-On capability.

The validator service intentionally has **no** `TWIN_REGISTRY_VALIDATION_HMAC_SECRET` and no Registry registration client. The generation/orchestration service assembles the Registry body but must receive the HMAC from the independent validator after every acceptance gate is evidenced. Until that complete validator exists, no HMAC is issued.

## Configuration

Required server-side environment:

- `TWIN_MESH_VALIDATOR_API_TOKEN`: internal caller bearer token (at least 32 bytes).
- `CONSENT_API_URL`, `CONSENT_API_TOKEN`: private consent service base URL and internal bearer token. The verification response must include the matching `consent_version`.
- `ASSET_SERVICE_URL`, `ASSET_SERVICE_TOKEN`: private Asset Service base URL and internal bearer token.

All service URLs must use HTTPS. Internal HTTP clients disable inherited proxy environment settings and do not follow redirects. `ALLOW_INSECURE_INTERNAL_HTTP=true` is for isolated local development only and must not be set in a deployed environment. Never put these values in browser code, app bundles, model prompts or logs.

`GET /ready` verifies required configuration is present. It does not claim that remote services are reachable; a real deployment smoke test must verify both dependencies and private-network policy.

## Run checks

From this directory:

```bash
python -m pip install -r requirements.txt
python -m pip check
python -m compileall -q app tests
python -m pytest -q
docker build -t cirvanna-twin-mesh-validator:local .
```

The tests use generated non-personal synthetic GLB data. They do not prove production consent, deployment, model performance, anatomical quality, scale accuracy, or privacy compliance.

## Release blockers

1. A commercially approved, pinned generator with documented output rights, DPA, regional processing, retention/deletion and subgroup quality evidence.
2. Independent body-coverage validation with published acceptance thresholds and representative evaluation data.
3. Independent scale calibration against reference measurements; declared glTF units alone are not calibration.
4. Source-photo non-embedding verification against the exact authorized source asset set.
5. Sensitive-data/privacy inspection with documented false-negative evaluation.
6. A validator-only signing authority and a Registry verification test proving the generator cannot create an accepted attestation.
7. Private deployment, key separation/rotation, monitoring, deletion/restore drills and failure-injection tests.

Keep capture, persistent generation, Twin registration, preview and Virtual Try-On disabled until all release gates have passed.
