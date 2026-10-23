# Xari service

**Status:** authenticated route-planning API scaffold implemented; downstream execution is not enabled.

Xari is the single canonical assistant/orchestration name. Tari and Xyra are legacy source generations under integration staging and must not be deployed as duplicate orchestrators.

The API exposes liveness, readiness, capability status, and authenticated `POST /v1/route`. The route planner uses fixed server-side environment names for chat, skin analysis, marketplace search, Virtual Twin, wardrobe, Click It and Virtual Try-On. It enforces explicit consent for image processing, body measurements, wardrobe access, Click It and try-on; rejects unknown intents/consent keys and untrusted upstream URL forms.

**Important limitation:** route planning is not execution. It does not forward user payloads or claim that chat, search, analysis, fit evaluation, or rendering happened. Execution adapters still need per-service authentication, typed requests/responses, timeout/retry policies, correlation IDs, redaction, rate limits, failure handling and end-to-end tests.

## Environment

- `XARI_API_TOKEN`: high-entropy internal bearer token (at least 32 UTF-8 bytes).
- Optional trusted HTTPS base URLs: `XARI_CHAT_API_URL`, `DERMALSIGHT_API_URL`, `MARKETPLACE_BFF_URL`, `VIRTUAL_TRY_ON_API_URL`, `VIRTUAL_TWIN_API_URL`, `WARDROBE_API_URL`.

## Local verification

From `services/xari`:

    python -m pip install -r requirements.txt
    python -m pytest -q

Production promotion requires validated downstream adapters and end-to-end consent propagation. Do not expose this internal routing API directly to unauthenticated clients.
