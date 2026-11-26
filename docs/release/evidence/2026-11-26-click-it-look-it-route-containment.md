# Click It / Look It route-containment review — 2026-11-26

**Classification:** source and CI containment evidence only; not independent privacy certification.  
**Candidate source revision reviewed:** `bfa8ad52613f2d8e355a659fd5fb0240d5a8e475`.  
**Click It remains disabled for public use.**

## Click It

The Marketplace BFF `POST /api/vision/click-it` route currently:
- validates the signed user and consent assertions;
- closes the upload without reading or forwarding the bytes;
- returns a private, no-store 503 response while the masking and resource-bound privacy-attestation pipeline remains unreleased.

The Virtual Twin internal Click It orchestrator is private and not production-enabled. Its documented path verifies resource-bound Identity consent and current jurisdiction policy before reading the upload, then forwards only to the private Vision Click It worker. The worker requires explicit worker authorization, detects and blurs faces before embedding, rejects uncertain detector output, drops the decoded original and does not perform face recognition.

These are containment and service-boundary controls. They do not establish that the detector has acceptable false-negative rates, that the full rights/guardian pipeline is operational, or that every deployed public media route is gated.

## Look It

Look It is a separate PNELLY user-supplied outfit-reference flow:
- the BFF derives the subject from the signed Commerce session before parsing multipart data;
- it creates and verifies a short-lived, resource-bound `image_processing` + `look_it` consent bundle;
- it forwards the bounded reference to the private Vision search route;
- the request bundle is revoked after processing, and results are suppressed if cleanup fails;
- the BFF/Vision path does not create a durable source-image asset and returns only candidate counts and validated outfit-component descriptions; product/merchant/price/media details remain withheld pending CAL.

The Vision `/v1/search/image` route is distinct from Click It. It requires both consent scopes and does not write the source image to disk or persist it. It uses the pinned CLIP retrieval model; match thresholds are not treated as calibrated confidence.

## Required next evidence

1. Execute these flows against deployed staging services with real Identity and service identities, not mocks.
2. Verify request-body and decoded-image lifecycle under success, timeout, model failure, revocation and cancellation.
3. Independently validate detector artifact/dataset digest, subgroup false-negative confidence intervals, uncertain-output fail-closed behavior and absence of identity/age inference.
4. Enumerate and exercise every publish, restore, syndication, share, merchant, cache, CDN, origin, derivative and binary media delivery route.
5. Verify urgent quarantine and deletion propagation through source, derivatives, replicas, backups where applicable and caches.
6. Obtain an independent assessor report digest-bound to the exact deployed commit and immutable asset/model digests.

## Gate disposition

REL-14 (Click It privacy) and REL-18 (Look It) remain **BLOCKED**. Click It is deliberately not enabled. This report does not claim that an unmasked image can never escape in a deployed environment; only an independent end-to-end test across the complete route inventory can establish that.
