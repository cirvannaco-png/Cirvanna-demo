# SAM 3D Body worker spike — 21 November 2026

## Decision

Implement a self-hosted, private inference spike around the upstream SAM 3D Body model as the first body-geometry candidate. Do not enable persistent Twin generation, body measurements, size recommendations or public rendering from this spike.

- Upstream code repository: `facebookresearch/sam-3d-body`
- Pinned code revision: `b5c765a0d89d789985e186d396315e7590887b94`
- Initial gated model ID: `facebook/sam-3d-body-dinov3`
- Model revision: must be a full 40-character Hugging Face commit supplied after access is approved.
- Model release digest: canonical SHA-256 over model ID, model revision, source commit and every downloaded artifact file.
- Model terms: SAM License; model access and commercial-use terms require legal review and recorded acceptance before worker readiness.

## Implemented in the spike branch

1. Internal FastAPI worker with bearer authentication.
2. Source commit, model revision, model release digest, license evidence, full artifact file hashes and CUDA/VRAM readiness gates.
3. Gated artifact provisioning script that requires a secret `HF_TOKEN`, exact model revision and explicit license evidence reference.
4. In-memory image processing only; no raw source image persistence or external inference transfer.
5. Full-body mesh serialization to GLB using the upstream estimator output and a neutral vertex material; no source-photo texture is embedded.
6. Explicit response markers: `measurement_calibrated=false` and `registry_eligible=false`.
7. Research-only GPU Dockerfile, excluded from the standard production image build matrix.
8. Contract tests for authentication, image constraints, artifact tampering, GLB serialization and non-calibrated output semantics.

## Important technical limitations

- The first worker uses one user-confirmed full-body image, no external person detector, no segmentation model and no calibrated camera/FOV provider.
- The model's default FOV and single-view reconstruction are not a physical measurement reference.
- The output mesh is not yet independently verified for anatomical coverage, body scale, fit accuracy, or population-level error.
- No Twin Registry, Asset Service, consent/revocation outbox or public renderer is called by the worker.
- The existing Virtual Twin API must continue to report generation as unavailable until the separate orchestration and validation work is complete.
- A real GPU smoke test has not been run in CI or this environment. The research Dockerfile and dependency set are not yet a production-locked SBOM.

## Release gates before integration

| Gate | Required evidence |
|---|---|
| Model access and license | Approved model-card/license record and gated-access evidence |
| Reproducibility | Exact source commit, exact HF revision, all artifact hashes and reproducible container build |
| GPU operation | Real CUDA smoke test, VRAM profile, latency and OOM behavior |
| Mesh integrity | Independent validator pass for GLB structure, topology, body coverage, scale and source-image non-embedding |
| Privacy | Consent verified before inference, revocation propagation, private asset storage, verified deletion and no public media path |
| Measurement accuracy | Pre-registered real-person cohort, manual ground truth, subgroup reporting and agreed error thresholds |
| Product integration | Only after all gates: Asset Service upload, Twin Registry registration and renderer integration |

## Explicit non-claims

This spike does not establish that Cirvanna has a production Virtual Twin, calibrated measurements, fit-grade accuracy, persistent reconstruction, or a customer-ready 3D renderer. It creates a real-model inference boundary for controlled evaluation only.
