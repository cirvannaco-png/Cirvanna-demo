# Virtual Twin service

**Owner:** Avatar/body representation and measurement extraction. **Status:** scaffold only.

Separate capture, geometric reconstruction, measurement extraction, storage and model adapters. Prefer a multi-file service with typed contracts over the uploaded monolithic candidates. No body/measurement output is production-ready until accuracy, calibration, consent, deletion and failure modes are tested.

## API foundation and validation status

A guarded FastAPI scaffold now lives at `services/virtual-twin/app/main.py`. It separates liveness from readiness, requires bearer authentication for twin-generation requests, and reports inference-related capabilities as unavailable. It intentionally returns HTTP 503 for twin generation until a real model adapter is integrated; this is safer than presenting the recovered source's placeholder geometry or simulated outputs as real analysis.

The API contract tests run in the dedicated Virtual Twin GitHub Actions workflow. They validate the API boundary and fail-closed behavior only; they do not establish body reconstruction, fit prediction, rendering quality, skin-model accuracy, or overall production readiness.

Skin-analysis ownership is separate: `services/dermalsight` contains an authenticated API and a hash-verified ONNX `SkinAnalysisEngine` with a signed validation-report gate. The authenticated `POST /skin-analysis` route proxies only consented JPEG/PNG/WebP uploads to `DERMALSIGHT_API_URL` using the service-to-service bearer token in `DERMALSIGHT_API_TOKEN`; it limits skin-analysis payloads to 5 MiB, avoids persistence, limits upstream timeouts, and sanitizes upstream errors. `GET /capabilities` reports skin analysis as available only when DermalSight's `/ready` returns an affirmative ready response. Configure a base URL and the matching shared service token in the deployment secrets; keep the internal model and signed validation report in secure mounted storage on the DermalSight deployment.

No approved trained model artifact, representative evaluation dataset, or signed validation report is currently checked into the repository. The synthetic ONNX CI graph proves runtime wiring only. Until a licensed model is evaluated across diverse skin tones, devices and lighting—and the actual deployment is tested—the endpoint must remain unavailable, and this service must not be represented as a production-ready skin-analysis product.
