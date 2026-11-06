# Image publication boundary — current route audit

**Scope:** repository source audit of branch feature/privacy-governance-service, 6 November 2026. This is not a live network penetration test or deployment certification.

## Default rule

No image URL is publishable merely because a product or offer passed catalog/CAL display authorization. Public media requires an asset-bound, active masking attestation for the exact asset and destination surface. Until a real provider verifies that receipt, API responses must omit image URLs. The product/offer can remain metadata-only.

## Observed enforcement points

| Surface | Current source behavior | Test evidence / limitation |
|---|---|---|
| Vision POST /v1/click-it/scan | Detector/masking runs before quality analysis, image embedding and live offer retrieval. Original decoded image is closed in finally; masked working image is closed in finally; response is no-store; result image URLs are stripped at top level and nested product. | services/vision-intelligence/tests/test_api.py includes ordering assertions and detector-failure assertions. CI mocks detector configuration and masking; this is not proof of the production model asset. |
| Vision POST /v1/search/text | Ranked offer image URLs are stripped before response, including nested product URLs. | test_api.py asserts both collections are empty. |
| Commerce GET /marketplace/offers | Response serializer emits image_urls: [] for every offer. | Route implementation is explicit. Add/retain contract tests whenever serializer changes. |
| API Gateway POST /v1/discover | Even when CAL authorizes product display, both product and offer image_urls are replaced with empty arrays until asset-bound receipts are verified. | services/api-gateway/tests/test_marketplace_discovery.py asserts both are empty for a product and offer containing deliberately unsafe fixture URLs. |
| API Gateway POST /v1/decisions | Candidate response always uses image_urls=[]; CAL authorization does not certify media privacy. | Source-level fail-closed serializer. Verify every client-facing consumer continues to use this route rather than bypassing it. |
| Privacy Governance internal publication evaluation | Calls the configured Vision privacy-attestation provider and requires exact asset and attestation IDs, active/verified status, all faces masked, zero unmasked faces, all regions processed, masking before publication, no recognition/embeddings/age estimation, and a SHA-256 model digest. Missing provider returns 503; invalid receipt returns 403. | services/privacy-governance-service/tests/test_api.py covers valid, invalid/unmasked, and missing-provider cases using a mocked provider. This is a policy gate, not yet an integration into all publish/restore/share mutations. |

## Remaining gaps — do not mark closed

1. No asset-bound provider integration: the Vision attestation endpoint is an external dependency. Current tests mock post_trusted; a configured URL/token alone does not prove the provider is live, licensed, or returning authentic signed attestations.
2. No universal publish/restore/share enforcement: the Privacy Governance evaluator exists, but the repository audit did not establish that every storage write, public profile/feed publish, merchant media publish, restore, syndication, CDN origin, and shared-link resolver invokes it before changing visibility.
3. Catalog is a trusted internal source of product image URLs: its product serializer returns stored URLs. Keep Catalog private to service-to-service traffic. Public clients must not be given direct Catalog access or direct CDN origin URLs that bypass the gateway.
4. Existing URL suppression is a safety hold, not completed media publishing: product images are intentionally unavailable until asset registry, attestation verification, and publish mutation integration are real.
5. No production pipeline proof: actual detector asset checksum, model license, provider endpoint, object-store lifecycle, CDN cache invalidation, deletion propagation, and Android client behavior remain unverified.

## Release verification plan

- Enumerate all routes that can create, publish, restore, share, syndicate, or resolve media; include API gateway, BFF, Catalog, Commerce, profile/community, wardrobe, Twin, merchant, static/CDN and background jobs.
- Route every visibility mutation through one provider-neutral publication service. Reject missing, expired, revoked, wrong-asset, wrong-purpose, wrong-destination, or invalidly signed attestations. Do not accept a client boolean or caller-supplied verified=true.
- Make the publish mutation and attestation check atomic with respect to asset version. A new binary/version invalidates the previous receipt.
- Add contract tests for each route: no receipt, stale receipt, wrong asset, wrong target surface, revoked receipt, provider timeout, invalid signature, and successful masked receipt. All failures must leave the asset private/unpublished.
- Test restore and shared-link resolution independently; unpublish/quarantine must revoke cached links and CDN copies.
- In staging, use controlled test images and a real pinned/licensed detector plus real attestation provider. Verify bytes at the public edge, not just JSON fields. Include detector outage, malformed output, low confidence, multiple faces, partial occlusion and minors.
- Keep all image URLs suppressed until every required integration and test passes.

## Human-reviewed outfit evaluation

See docs/evaluation/outfit-recommendation-evaluation.md. The harness compares ranking relevance, outfit diversity and exclusion violations against a simple baseline, and reports actual observed edits and repeated rejections separately. No labelled dataset or results exist yet.
