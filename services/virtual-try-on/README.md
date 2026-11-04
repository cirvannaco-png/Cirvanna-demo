# Cirvanna Virtual Try-On

**Status:** guarded API foundation only. It does not yet generate try-on images.

## Ownership

This service owns try-on orchestration and rendering/simulation contracts. It does not own product truth (catalog), body representation (Virtual Twin), fit-confidence prediction (FCI), or purchase-policy arbitration (CaTaCaCi/CAL).

## API

- `GET /health` — liveness only.
- `GET /ready` — readiness; returns 503 until a validated renderer, consent verifier, asset authorizer, and authentication are configured.
- `GET /capabilities` — reports verified capability state.
- `POST /v1/try-ons` — consent-gated orchestration request. It currently returns 503 because the production integrations are deliberately absent.

Requests use `Authorization: Bearer $VIRTUAL_TRY_ON_API_TOKEN`. Do not put the shared service token in browser code. A user-facing application needs user authentication and server-side authorization before it calls this service.

## Input and privacy boundary

The API accepts opaque internal asset IDs only, not arbitrary image URLs, file paths, or raw image uploads. A production asset authorizer must verify ownership/access for the person image, Virtual Twin, catalog product, and garment image. A renderer must resolve those IDs through a protected internal asset service.

Both `consent.image_processing` and `consent.virtual_try_on` must be true, and the current contract only accepts an `ephemeral` retention policy. These client-provided fields are not trusted evidence by themselves: before rendering, the service calls a separate server-side consent verifier and blocks rendering unless an active matching consent record is verified. Consent must be recorded and revocable in the identity/consent service before real user traffic is enabled.

The current service does not persist images or request bodies. It does not log image content or accept caller-controlled URLs.

## Model candidate

[FASHN VTON 1.5](https://huggingface.co/fashn-ai/fashn-vton-1.5) is the leading open-source candidate for the first prototype. Its official model card describes a roughly 972M-parameter PyTorch MMDiT model, Apache-2.0 licensing for the model repository, 576×864 output, and three categories: `tops`, `bottoms`, and `one-pieces`. The published model card estimates about 8 GB of VRAM for inference and around 5 seconds on an NVIDIA H100; these are upstream estimates, not Cirvanna benchmark results. The model weights are about 2 GB, and a human-parser dependency adds about 244 MB of weights. See the [official inference example](https://github.com/fashn-AI/fashn-vton-1.5/blob/main/examples/basic_inference.py) and [model card](https://huggingface.co/fashn-ai/fashn-vton-1.5).

**Decision:** prototype FASHN VTON 1.5 in an isolated GPU worker; do not load it inside the public API container. Map Cirvanna categories explicitly: `upper_body` and `outerwear` to `tops`, `lower_body` to `bottoms`, and `dress` / `full_outfit` to `one-pieces`. Unsupported category combinations must be rejected, not silently remapped.

**Before production:** pin the exact source commit and weight revision, verify the license for the full dependency stack (the model card lists a human-parser dependency whose license must be reviewed separately), validate model inputs/outputs, and benchmark representative images. The published model card itself notes imperfect body-shape preservation and possible traces of the original garment during long-to-short or bulky-to-slim swaps. These are material quality risks, not edge cases to ignore.

## Provider integration contract

Implement and independently validate three adapters satisfying the protocols in `app.main`:

1. **Consent verifier:** verify the subject's current server-side consent record, scope, purpose, and revocation state. Do not accept a boolean or arbitrary consent ID as proof.
2. **Asset authorizer:** verify subject ownership/authorization for the twin and person image, and verify the garment image belongs to the referenced catalog product. Resolve assets from trusted internal storage; reject arbitrary URLs and cross-tenant IDs.
3. **Renderer:** call a pinned model revision through a protected inference endpoint or isolated GPU worker; validate category compatibility and inputs; verify the output is a decodable image within dimensions/size limits; persist the output under an opaque asset ID; return the actual stored asset ID and model version.

A timeout, invalid image, failed consent check, unauthorized asset, or malformed model output must never return `complete`. Use bounded concurrency, rate limits, timeouts, ephemeral input handling, deletion controls, and observability without logging image payloads or secrets.

## Local development

```bash
python -m pip install -r services/virtual-try-on/requirements.txt
cd services/virtual-try-on
VIRTUAL_TRY_ON_API_TOKEN=local-test-token uvicorn app.main:app --host 127.0.0.1 --port 8080
python -m pytest tests -q
```

Build the container from the repository root:

```bash
docker build -f services/virtual-try-on/Dockerfile -t cirvanna-virtual-try-on .
```

## Validation and release gates

The dedicated `.github/workflows/virtual-try-on.yml` workflow runs API tests and a Docker image build. The tests validate authentication, explicit consent gating, server-side consent and asset authorization, rejection of external URL/path inputs, provider failure handling, and honest unavailable status. Fixture adapters are used only to test the successful response contract; they are not real models and must never be enabled outside tests.

Still required: authenticated asset-resolution integration, server-side consent integration, actual model inference, image-quality/robustness tests across body types and garment categories, privacy/security review, model/license review, latency/cost benchmarking, rendering artifact validation, deletion tests, and a real end-to-end deployment smoke test. Passing CI validates the contract and container build, not image realism or fit accuracy.

## Marketplace, Tari and optional Complementer entry points

Marketplace product cards are the intended first-class entry point for trying on a selected catalog product before purchase. The card may expose a Try-On action, but it must remain unavailable unless the BFF can authenticate the user, resolve a user-owned Twin and trusted person/product image assets, verify active server-side consent, and confirm this service's /ready and renderer capability checks.

Tari may optionally coordinate the user journey and explain the next step. Complementer may optionally provide styling context (for example, pairing or colour suggestions) when requested. Neither assistant may fabricate a rendered image, override consent/asset authorization, certify fit, or bypass the canonical FCI and CAL boundaries. A generated visual preview is not a guarantee of garment fit, fabric behavior, shade fidelity or purchase suitability.

The current implementation still returns unavailable until the real renderer and secure adapters are integrated. The marketplace must not enable the action merely because a product card or API route exists.