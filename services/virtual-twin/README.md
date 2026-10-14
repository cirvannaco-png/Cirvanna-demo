# Virtual Twin service

**Owner:** Avatar/body representation and measurement extraction. **Status:** scaffold only.

Separate capture, geometric reconstruction, measurement extraction, storage and model adapters. Prefer a multi-file service with typed contracts over the uploaded monolithic candidates. No body/measurement output is production-ready until accuracy, calibration, consent, deletion and failure modes are tested.

## API foundation and validation status

A guarded FastAPI scaffold now lives at `services/virtual-twin/app/main.py`. It separates liveness from readiness, requires bearer authentication for twin-generation requests, and reports inference-related capabilities as unavailable. It intentionally returns HTTP 503 for twin generation until a real model adapter is integrated; this is safer than presenting the recovered source's placeholder geometry or simulated outputs as real analysis.

The scaffold's API tests run in the dedicated Virtual Twin GitHub Actions workflow. Passing those tests validates only the API contract and fail-closed behavior; it does not validate model quality, body reconstruction, skin analysis, fit predictions, AR rendering, or production readiness.
